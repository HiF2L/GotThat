import logging
import copy
from typing import Dict, Any, Optional, List, Tuple, Set
from datetime import datetime
from sqlalchemy import select, and_, or_
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.session import DeepLearningSession
from app.models.ontology import Concept, Track
from app.models.mastery import User, UserMasteryState
from app.services.cognitive.bkt_engine import bkt_engine
from app.schemas.tutor import (
    StartDeepSessionRequest,
    PlannedDAGSchema,
    DeepStepPayload,
    DeepStepAnswerSubmission,
    DeepStepAnswerResult,
    DAGNodeSchema,
    DAGEdgeSchema,
)
from app.services.tutor.probe_phase import probe_manager
from app.services.tutor.plan_phase import plan_manager
from app.services.tutor.step_executor import step_executor
from app.services.graph.knowledge_graph import knowledge_graph_service, deterministic_topological_sort
from app.models.ontology import Concept, Track, ConceptDependency

logger = logging.getLogger(__name__)


def is_concept_mastered(m: Optional[UserMasteryState]) -> bool:
    if not m:
        return False
    return (m.mastery_prob >= 0.85) or (m.mastery_prob >= 0.80 and getattr(m, 'uncertainty', 1.0) <= 0.40)


def build_mermaid_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> str:
    lines = ["graph TD"]
    for n in nodes:
        clean_title = (n.get("title") or "Concept").replace('"', "'")
        code = n.get("code") or n.get("id")
        status = n.get("status", "pending")
        if status == "completed":
            lines.append(f'    {code}["✔ {clean_title}"]:::completed')
        elif status == "active":
            lines.append(f'    {code}["▶ {clean_title}"]:::active')
        else:
            lines.append(f'    {code}["{clean_title}"]:::pending')

    for e in edges:
        src = e.get("source_code") or e.get("source")
        tgt = e.get("target_code") or e.get("target")
        if src and tgt:
            lines.append(f"    {src} --> {tgt}")

    lines.append("    classDef completed fill:#10B981,stroke:#059669,stroke-width:2px,color:#fff;")
    lines.append("    classDef active fill:#6366F1,stroke:#4F46E5,stroke-width:3px,color:#fff;")
    lines.append("    classDef pending fill:#1E293B,stroke:#475569,stroke-width:1px,color:#94A3B8;")
    return "\n".join(lines)


class TutorStateMachine:
    """
    Master Orchestrator managing the lifecycle of a Deep Learning Session:
    1. PROBING: Fast, non-hallucinating batch diagnostic assessment suite.
    2. PLANNING: Synthesizes a brand new, tailored 20-35+ concept Zero-to-Mastery Course DAG.
    3. TEACHING: Step-by-step unconstrained pedagogy with live interactive LaTeX & SVG visualizer.
    4. VERIFICATION & NAVIGATION: Updates DAG live with color-coded nodes, skipping already-mastered concepts, and resuming sessions.
    """

    async def reconcile_dag_with_mastery(
        self,
        session: AsyncSession,
        user_id: str,
        dag_data: Dict[str, Any],
        requested_concept_id: Optional[str] = None,
        current_index: Optional[int] = None,
        is_advancing: bool = False,
    ) -> Tuple[Dict[str, Any], int, Optional[str], bool]:
        """
        Dynamically reconciles DAG node statuses, completed_nodes count, and Mermaid schema
        with the single source of truth: UserMasteryState in the database.
        Ensures canonical deterministic topological ordering across all nodes.
        """
        dag_copy = copy.deepcopy(dag_data)
        raw_nodes = list(dag_copy.get("nodes", []))
        edges = list(dag_copy.get("edges", []))
        if not raw_nodes:
            return dag_copy, 0, None, False

        node_ids = [n["id"] for n in raw_nodes if "id" in n]

        # 1. Fetch Concept objects from DB to enrich node metadata and collect dependencies
        concepts_res = await session.execute(
            select(Concept).where(Concept.id.in_(node_ids))
        )
        concepts_db_map = {c.id: c for c in concepts_res.scalars().all()}

        for n in raw_nodes:
            c = concepts_db_map.get(n.get("id"))
            if c:
                if not n.get("slug") and c.slug:
                    n["slug"] = c.slug
                if not n.get("code") and c.code:
                    n["code"] = c.code
                if not n.get("title") and c.title:
                    n["title"] = c.title

        # Query database dependencies between these concepts
        deps_res = await session.execute(
            select(ConceptDependency).where(
                and_(
                    ConceptDependency.source_concept_id.in_(node_ids),
                    ConceptDependency.target_concept_id.in_(node_ids),
                )
            )
        )
        subgraph_deps = [(d.source_concept_id, d.target_concept_id) for d in deps_res.scalars().all()]
        if not subgraph_deps and edges:
            subgraph_deps = [
                (e.get("source") or e.get("source_id"), e.get("target") or e.get("target_id"))
                for e in edges
                if (e.get("source") or e.get("source_id")) and (e.get("target") or e.get("target_id"))
            ]

        # Deterministically sort nodes in canonical pedagogical topological order
        nodes = deterministic_topological_sort(raw_nodes, subgraph_deps)

        mastery_res = await session.execute(
            select(UserMasteryState).where(
                and_(
                    UserMasteryState.user_id == user_id,
                    UserMasteryState.concept_id.in_(node_ids),
                )
            )
        )
        mastery_map = {m.concept_id: m for m in mastery_res.scalars().all()}

        # 2. Check which nodes are mastered
        completed_indices = set()
        for idx, node in enumerate(nodes):
            nid = node.get("id")
            m = mastery_map.get(nid)
            m_prob = m.mastery_prob if m else 0.0
            node["mastery_prob"] = m_prob
            if is_concept_mastered(m):
                completed_indices.add(idx)

        # 3. Determine target active index
        active_idx = None

        # A. If a specific concept was requested
        if requested_concept_id:
            # Check direct match in sorted nodes
            for idx, node in enumerate(nodes):
                if (
                    node.get("id") == requested_concept_id
                    or node.get("slug") == requested_concept_id
                    or node.get("code") == requested_concept_id
                ):
                    active_idx = idx
                    break

            # If not matched directly, resolve against Concept table in DB
            if active_idx is None:
                c_lookup_res = await session.execute(
                    select(Concept).where(
                        or_(
                            Concept.id == requested_concept_id,
                            Concept.slug == requested_concept_id,
                            Concept.code == requested_concept_id,
                        )
                    )
                )
                resolved_c = c_lookup_res.scalars().first()
                if resolved_c:
                    for idx, node in enumerate(nodes):
                        if (
                            node.get("id") == resolved_c.id
                            or node.get("slug") == resolved_c.slug
                            or node.get("code") == resolved_c.code
                        ):
                            active_idx = idx
                            break

        # B. If advancing after completing a step at current_index
        if active_idx is None and is_advancing and current_index is not None:
            # 1. Forward scan: check concepts from current_index + 1 to the end
            scan_idx = current_index + 1
            while scan_idx < len(nodes) and scan_idx in completed_indices:
                scan_idx += 1
            if scan_idx < len(nodes):
                active_idx = scan_idx
            else:
                # 2. Cyclic wrap-around scan: search from the beginning (0 .. current_index) for any unmastered concept
                wrap_idx = 0
                while wrap_idx <= current_index and wrap_idx < len(nodes):
                    if wrap_idx not in completed_indices:
                        active_idx = wrap_idx
                        break
                    wrap_idx += 1

                # 3. If every single node across the entire course is mastered, mark all completed
                if active_idx is None:
                    active_idx = len(nodes)


        # C. If a current_index is already set and not advancing, RESPECT the current index
        if active_idx is None and not is_advancing and current_index is not None and 0 <= current_index < len(nodes):
            active_idx = current_index

        # D. Otherwise (starting track from scratch with no index set), find the first unmastered node
        if active_idx is None:
            for idx in range(len(nodes)):
                if idx not in completed_indices:
                    active_idx = idx
                    break
            if active_idx is None and len(nodes) > 0:
                active_idx = 0

        # 4. Check completion and mark node statuses
        if active_idx is not None and 0 <= active_idx < len(nodes):
            for idx, node in enumerate(nodes):
                if idx == active_idx:
                    node["status"] = "active"
                elif idx in completed_indices:
                    node["status"] = "completed"
                else:
                    node["status"] = "pending"
            active_concept_id = nodes[active_idx]["id"]
            is_all_completed = False
        else:
            for idx, node in enumerate(nodes):
                node["status"] = "completed"
            active_idx = len(nodes)
            active_concept_id = None
            is_all_completed = True

        # Re-render updated Mermaid diagram
        updated_mermaid = build_mermaid_graph(nodes, edges)
        dag_copy["nodes"] = nodes
        dag_copy["edges"] = edges
        dag_copy["mermaid_code"] = updated_mermaid
        dag_copy["total_nodes"] = len(nodes)
        dag_copy["completed_nodes"] = len(completed_indices)

        return dag_copy, (len(nodes) if is_all_completed else active_idx), active_concept_id, is_all_completed

    async def start_session(
        self,
        session: AsyncSession,
        request: StartDeepSessionRequest,
    ) -> DeepLearningSession:
        # 1. Resolve user ID
        user_res = await session.execute(select(User).where(User.id == request.user_id))
        user = user_res.scalars().first()
        if not user:
            user_res = await session.execute(select(User).limit(1))
            user = user_res.scalars().first()
            if not user:
                user = User(username="hitori_learner", email="learner@gotit.local")
                session.add(user)
                await session.flush()
        user_id = user.id

        # 2. Resolve target concept & track
        target_concept = None
        is_track_level_request = False
        specific_concept_id = None

        if request.target_concept_id:
            # Check FIRST if request.target_concept_id matches a Track (ID or Slug)
            t_res = await session.execute(
                select(Track).where(
                    or_(
                        Track.id == request.target_concept_id,
                        Track.slug == request.target_concept_id,
                    )
                )
            )
            track_match = t_res.scalars().first()
            if track_match:
                is_track_level_request = True
                tc_res = await session.execute(
                    select(Concept).where(Concept.track_id == track_match.id)
                )
                track_concepts = tc_res.scalars().all()
                if track_concepts:
                    target_concept = track_concepts[-1]
            else:
                # Check if it matches a specific Concept
                c_res = await session.execute(
                    select(Concept).where(
                        or_(
                            Concept.id == request.target_concept_id,
                            Concept.slug == request.target_concept_id,
                            Concept.code == request.target_concept_id,
                        )
                    )
                )
                target_concept = c_res.scalars().first()
                if target_concept:
                    specific_concept_id = target_concept.id

        if not target_concept:
            c_res = await session.execute(select(Concept).limit(1))
            target_concept = c_res.scalars().first()
            if not target_concept:
                raise ValueError("No concepts available in ontology")
            is_track_level_request = True

        target_concept_id = target_concept.id
        track_id = target_concept.track_id

        # 3. Check for an EXISTING ACTIVE SESSION on this track/concept to resume without repeating diagnostics!
        track_concepts_res = await session.execute(select(Concept).where(Concept.track_id == track_id))
        track_concept_ids = [c.id for c in track_concepts_res.scalars().all()]

        existing_session_res = await session.execute(
            select(DeepLearningSession).where(
                and_(
                    DeepLearningSession.user_id == user_id,
                    or_(
                        DeepLearningSession.target_concept_id == target_concept_id,
                        DeepLearningSession.target_concept_id.in_(track_concept_ids),
                    ),
                )
            ).order_by(DeepLearningSession.created_at.desc())
        )
        existing_session = existing_session_res.scalars().first()

        session_lang = request.language or "ru"
        track_depth = "high"
        if target_concept and target_concept.track_id:
            track_res = await session.execute(select(Track).where(Track.id == target_concept.track_id))
            track_obj = track_res.scalars().first()
            if track_obj and track_obj.depth_level:
                track_depth = track_obj.depth_level
        session_depth = (request.depth_level if request.depth_level else None) or track_depth or "high"

        # 3a. If user already has a planned DAG session, resume it
        if existing_session and existing_session.planned_dag:
            if request.language:
                existing_session.language = request.language
            if request.depth_level:
                existing_session.depth_level = request.depth_level
            elif track_depth:
                existing_session.depth_level = track_depth

            # Reconcile DAG with DB mastery states
            reconciled_dag, active_idx, active_cid, is_all_completed = await self.reconcile_dag_with_mastery(
                session=session,
                user_id=user_id,
                dag_data=existing_session.planned_dag,
                requested_concept_id=specific_concept_id if not is_track_level_request else None,
                current_index=existing_session.current_concept_index if (not is_track_level_request and specific_concept_id is None) else None,
            )
            existing_session.planned_dag = reconciled_dag
            flag_modified(existing_session, "planned_dag")
            existing_session.mermaid_diagram = reconciled_dag.get("mermaid_code", "")
            existing_session.current_concept_index = active_idx
            existing_session.current_concept_id = active_cid

            if is_all_completed:
                existing_session.status = "completed"
                if not existing_session.completed_at:
                    existing_session.completed_at = datetime.utcnow()
            else:
                existing_session.status = "teaching"

            await session.commit()
            return existing_session

        # 3b. Resuming an ongoing diagnostic probing session on page reload (F5) without losing questions/answers
        if existing_session and existing_session.status == "probing" and not getattr(request, "skip_probing", False):
            if request.language:
                existing_session.language = request.language
            if request.depth_level:
                existing_session.depth_level = request.depth_level
            elif track_depth:
                existing_session.depth_level = track_depth
            await session.commit()
            return existing_session

        # 4. Check if this track ALREADY has compiled curriculum concepts (>= 4 concepts)
        if len(track_concept_ids) >= 4:
            # Build the DAG directly and start teaching without re-probing
            dag_plan = await knowledge_graph_service.plan_curriculum_dag(
                session=session,
                user_id=user_id,
                target_concept_id=target_concept_id,
            )

            # Reconcile DAG with actual user mastery states
            reconciled_dag, active_idx, active_cid, is_all_completed = await self.reconcile_dag_with_mastery(
                session=session,
                user_id=user_id,
                dag_data=dag_plan.model_dump(),
                requested_concept_id=specific_concept_id if not is_track_level_request else None,
                current_index=None,
            )

            deep_session = DeepLearningSession(
                user_id=user_id,
                target_concept_id=target_concept_id,
                status="completed" if is_all_completed else "teaching",
                language=session_lang,
                depth_level=session_depth,
                current_concept_index=active_idx,
                current_concept_id=active_cid or (dag_plan.nodes[0].id if dag_plan.nodes else target_concept.id),
                planned_dag=reconciled_dag,
                mermaid_diagram=reconciled_dag.get("mermaid_code", ""),
                completed_at=datetime.utcnow() if is_all_completed else None,
                probing_state={"probed_nodes": [], "answers": {}, "transcript": [], "suite": []},
            )
            session.add(deep_session)
            await session.commit()
            return deep_session

        # 5. Direct Start (User chose "Сразу к первому уроку без теста"): synthesize tailored course DAG immediately
        if getattr(request, "skip_probing", False):
            target_track_obj = None
            if target_concept and target_concept.track_id:
                t_res = await session.execute(select(Track).where(Track.id == target_concept.track_id))
                target_track_obj = t_res.scalars().first()

            track_wishes = target_track_obj.user_wishes if target_track_obj else None
            combined_notes_parts = []
            if track_wishes:
                combined_notes_parts.append(f"Student Course Wishes / Focus: {track_wishes}")
            if request.initial_user_context and request.initial_user_context.strip():
                combined_notes_parts.append(f"Student Context: {request.initial_user_context.strip()}")
            effective_context_notes = "\n".join(combined_notes_parts)

            planned_dag = await plan_manager.generate_and_verify_plan(
                session=session,
                user_id=user_id,
                target_concept_id=target_concept_id,
                user_context_notes=effective_context_notes,
                probing_transcript=None,  # Clean start without probe skips
                language=session_lang,
                depth_level=session_depth,
            )

            reconciled_dag, active_idx, active_cid, is_all_completed = await self.reconcile_dag_with_mastery(
                session=session,
                user_id=user_id,
                dag_data=planned_dag.model_dump(),
                requested_concept_id=specific_concept_id if not is_track_level_request else None,
                current_index=None,
            )

            deep_session = existing_session or DeepLearningSession(
                user_id=user_id,
                target_concept_id=target_concept_id,
            )
            deep_session.status = "completed" if is_all_completed else "teaching"
            deep_session.language = session_lang
            deep_session.depth_level = session_depth
            deep_session.planned_dag = reconciled_dag
            flag_modified(deep_session, "planned_dag")
            deep_session.mermaid_diagram = reconciled_dag.get("mermaid_code", "")
            deep_session.current_concept_index = active_idx
            deep_session.current_concept_id = active_cid or (reconciled_dag["nodes"][0]["id"] if reconciled_dag.get("nodes") else target_concept_id)
            deep_session.probing_state = {"probed_nodes": [], "answers": {}, "transcript": [], "suite": []}
            if is_all_completed and not deep_session.completed_at:
                deep_session.completed_at = datetime.utcnow()

            if not existing_session:
                session.add(deep_session)

            await session.commit()
            return deep_session

        # 6. If track is brand new and uncompiled (<= 1 concept) and user wants diagnostic test:
        deep_session = DeepLearningSession(
            user_id=user_id,
            target_concept_id=target_concept_id,
            status="probing",
            language=session_lang,
            depth_level=session_depth,
            probing_state={"probed_nodes": [], "answers": {}, "transcript": [], "suite": []},
        )
        session.add(deep_session)

        # Update user preferred language
        user_res = await session.execute(select(User).where(User.id == user_id))
        user = user_res.scalars().first()
        if user and request.language:
            user.preferred_language = request.language

        await session.commit()
        await session.refresh(deep_session)

        # Pre-initialize diagnostic suite
        await probe_manager.initialize_suite_if_needed(session, deep_session)
        return deep_session


    async def record_probe_answer(
        self,
        session: AsyncSession,
        deep_session_id: str,
        concept_id: str,
        option_id: str,
        user_notes: str = "",
    ) -> Dict[str, Any]:
        session_res = await session.execute(
            select(DeepLearningSession).where(DeepLearningSession.id == deep_session_id)
        )
        deep_session = session_res.scalars().first()
        if not deep_session:
            raise ValueError("Session not found")

        probing_state = dict(deep_session.probing_state or {})
        probed_nodes = list(probing_state.get("probed_nodes", []))
        transcript = list(probing_state.get("transcript", []))

        # Always record each answered question into probed_nodes
        effective_qid = concept_id or f"q_{len(probed_nodes) + 1}"
        if effective_qid not in probed_nodes:
            probed_nodes.append(effective_qid)
        else:
            probed_nodes.append(f"{effective_qid}_{len(probed_nodes) + 1}")

        is_known = (option_id in ["yes", "mastered", "a", "b"]) and (option_id not in ["idk", "new", "no", "vague"])
        transcript.append({
            "concept_id": effective_qid,
            "selected_option": option_id,
            "student_reasoning_and_notes": user_notes.strip() if user_notes else "",
            "evaluated_as_mastered": is_known,
        })

        probing_state["probed_nodes"] = probed_nodes
        probing_state["transcript"] = transcript
        deep_session.probing_state = probing_state
        flag_modified(deep_session, "probing_state")

        # Update Bayesian Mastery ONLY for real database concepts (probe suite questions are tracked in transcript)
        if concept_id and not concept_id.startswith("probe_") and not concept_id.startswith("dyn_"):
            c_check = await session.execute(select(Concept.id).where(Concept.id == concept_id))
            if c_check.scalars().first():
                mastery_res = await session.execute(
                    select(UserMasteryState).where(
                        and_(
                            UserMasteryState.user_id == deep_session.user_id,
                            UserMasteryState.concept_id == concept_id,
                        )
                    )
                )
                mastery = mastery_res.scalars().first()
                if not mastery:
                    mastery = UserMasteryState(
                        user_id=deep_session.user_id,
                        concept_id=concept_id,
                        mastery_prob=0.85 if is_known else 0.1,
                        uncertainty=0.2 if is_known else 0.3,
                    )
                    session.add(mastery)
                else:
                    post_m, post_u = bkt_engine.update_mastery(
                        prior_mastery=mastery.mastery_prob,
                        prior_uncertainty=mastery.uncertainty,
                        is_correct=is_known,
                    )
                    mastery.mastery_prob = post_m
                    mastery.uncertainty = post_u

        suite = probing_state.get("suite", [])
        suite_length = len(suite) if suite else probe_manager.TARGET_DIAGNOSTIC_DEPTH

        # Check if user requested immediate plan synthesis or if all diagnostic questions are completed
        if option_id == "generate_plan_now" or len(probed_nodes) >= suite_length:
            deep_session.status = "planning"
        else:
            next_probe = await probe_manager.get_next_probe_question(
                session=session,
                user_id=deep_session.user_id,
                target_concept_id=deep_session.target_concept_id,
                probed_concept_ids=probed_nodes,
                deep_session=deep_session,
            )
            if not next_probe:
                deep_session.status = "planning"

        await session.commit()
        return await self.get_next_action(session, deep_session_id)

    async def get_next_action(
        self,
        session: AsyncSession,
        deep_session_id: str,
        user_notes: str = "",
    ) -> Dict[str, Any]:
        session_res = await session.execute(
            select(DeepLearningSession).where(DeepLearningSession.id == deep_session_id)
        )
        deep_session = session_res.scalars().first()
        if not deep_session:
            raise ValueError("Session not found")

        # 1. State: PROBING (Instantly serve next question from pre-generated batch suite)
        if deep_session.status == "probing":
            probing_state = deep_session.probing_state or {}
            probed_nodes = probing_state.get("probed_nodes", [])

            next_probe = await probe_manager.get_next_probe_question(
                session=session,
                user_id=deep_session.user_id,
                target_concept_id=deep_session.target_concept_id,
                probed_concept_ids=probed_nodes,
                deep_session=deep_session,
            )
            if next_probe:
                return {
                    "phase": "probing",
                    "probe_question": next_probe,
                    "session_id": deep_session.id,
                }

            deep_session.status = "planning"
            await session.commit()

        # 2. State: PLANNING (Synthesizes Full Tailored Course DAG + Step 1)
        if deep_session.status == "planning":
            # Fetch track wishes if present
            concept_res = await session.execute(
                select(Concept).where(Concept.id == deep_session.target_concept_id)
            )
            target_c = concept_res.scalars().first()
            track_wishes = None
            if target_c and target_c.track_id:
                t_res = await session.execute(select(Track).where(Track.id == target_c.track_id))
                t_obj = t_res.scalars().first()
                if t_obj and t_obj.user_wishes:
                    track_wishes = t_obj.user_wishes

            combined_notes_parts = []
            if track_wishes:
                combined_notes_parts.append(f"Student Course Wishes / Focus: {track_wishes}")
            if user_notes and user_notes.strip():
                combined_notes_parts.append(f"Student Notes: {user_notes.strip()}")
            effective_context_notes = "\n".join(combined_notes_parts)

            planned_dag = await plan_manager.generate_and_verify_plan(
                session=session,
                user_id=deep_session.user_id,
                target_concept_id=deep_session.target_concept_id,
                user_context_notes=effective_context_notes,
                probing_transcript=deep_session.probing_state,
                language=getattr(deep_session, "language", None) or "ru",
                depth_level=getattr(deep_session, "depth_level", "high") or "high",
            )

            # Reconcile DAG with actual user mastery
            reconciled_dag, active_idx, active_cid, is_all_completed = await self.reconcile_dag_with_mastery(
                session=session,
                user_id=deep_session.user_id,
                dag_data=planned_dag.model_dump(),
                requested_concept_id=None,
                current_index=None,
            )

            deep_session.planned_dag = reconciled_dag
            flag_modified(deep_session, "planned_dag")
            deep_session.mermaid_diagram = reconciled_dag.get("mermaid_code", "")
            deep_session.current_concept_index = active_idx
            deep_session.current_concept_id = active_cid
            deep_session.status = "completed" if is_all_completed else "teaching"
            if is_all_completed and not deep_session.completed_at:
                deep_session.completed_at = datetime.utcnow()
            await session.commit()

            nodes = reconciled_dag.get("nodes", [])
            edges = reconciled_dag.get("edges", [])
            planned_dag_schema = PlannedDAGSchema(
                mermaid_code=reconciled_dag.get("mermaid_code", ""),
                nodes=[DAGNodeSchema(**n) for n in nodes],
                edges=[DAGEdgeSchema(**e) for e in edges],
                total_nodes=len(nodes),
                completed_nodes=reconciled_dag.get("completed_nodes", 0),
            )

            if is_all_completed or active_idx >= len(nodes):
                return {
                    "phase": "completed",
                    "session_id": deep_session.id,
                    "dag": planned_dag_schema,
                    "message": "All concepts in this track are already mastered!",
                }

            # Immediately execute atomic step for the active node
            active_node = nodes[active_idx]
            concept_res = await session.execute(
                select(Concept).where(Concept.id == active_node["id"])
            )
            concept = concept_res.scalars().first()
            if concept:
                try:
                    step_payload = await step_executor.execute_atomic_step(
                        session=session,
                        deep_session=deep_session,
                        concept=concept,
                        step_sequence=active_idx + 1,
                        user_notes=user_notes,
                    )
                    # Speculatively pre-generate next lesson in background while user reads this one
                    if active_idx + 1 < len(nodes):
                        next_node = nodes[active_idx + 1]
                        step_executor.trigger_background_prefetch(
                            user_id=deep_session.user_id,
                            session_id=deep_session.id,
                            concept_id=next_node["id"],
                            step_sequence=active_idx + 2,
                            user_notes=user_notes,
                        )
                    return {
                        "phase": "step_ready",
                        "step": step_payload,
                        "dag": planned_dag_schema,
                        "mermaid_diagram": planned_dag_schema.mermaid_code,
                        "session_id": deep_session.id,
                    }
                except Exception as e:
                    logger.error(f"Failed to execute initial step on plan generation: {e}", exc_info=True)

            return {
                "phase": "plan_ready",
                "dag": planned_dag_schema,
                "mermaid_diagram": planned_dag_schema.mermaid_code,
                "session_id": deep_session.id,
            }

        # 3. State: TEACHING
        if deep_session.status == "teaching":
            # Always dynamically reconcile DAG state against UserMasteryState
            reconciled_dag, active_idx, active_cid, is_all_completed = await self.reconcile_dag_with_mastery(
                session=session,
                user_id=deep_session.user_id,
                dag_data=deep_session.planned_dag or {},
                requested_concept_id=None,
                current_index=deep_session.current_concept_index,
            )
            deep_session.planned_dag = reconciled_dag
            flag_modified(deep_session, "planned_dag")
            deep_session.mermaid_diagram = reconciled_dag.get("mermaid_code", "")
            deep_session.current_concept_index = active_idx
            deep_session.current_concept_id = active_cid

            nodes = reconciled_dag.get("nodes", [])
            edges = reconciled_dag.get("edges", [])

            planned_dag_schema = PlannedDAGSchema(
                mermaid_code=reconciled_dag.get("mermaid_code", ""),
                nodes=[DAGNodeSchema(**n) for n in nodes],
                edges=[DAGEdgeSchema(**e) for e in edges],
                total_nodes=len(nodes),
                completed_nodes=reconciled_dag.get("completed_nodes", 0),
            )

            if is_all_completed or active_idx >= len(nodes):
                deep_session.status = "completed"
                if not deep_session.completed_at:
                    deep_session.completed_at = datetime.utcnow()
                await session.commit()

                # In review mode, load the selected/active concept's lesson directly from DB
                review_idx = min(max(0, deep_session.current_concept_index), len(nodes) - 1) if nodes else 0
                step_payload = None
                if nodes:
                    review_node = nodes[review_idx]
                    concept_res = await session.execute(
                        select(Concept).where(Concept.id == review_node["id"])
                    )
                    concept = concept_res.scalars().first()
                    if concept:
                        try:
                            step_payload = await step_executor.execute_atomic_step(
                                session=session,
                                deep_session=deep_session,
                                concept=concept,
                                step_sequence=review_idx + 1,
                                user_notes=user_notes,
                            )
                            step_payload.is_session_completed = True
                        except Exception as e:
                            logger.error(f"Failed to load completed step from DB: {e}")

                return {
                    "phase": "completed",
                    "session_id": deep_session.id,
                    "step": step_payload,
                    "dag": planned_dag_schema,
                    "is_course_completed": True,
                    "message": "Курс полностью освоен! Вы можете изучать любые уроки в режиме повторения.",
                }

            current_node = nodes[active_idx]
            concept_res = await session.execute(
                select(Concept).where(Concept.id == current_node["id"])
            )
            concept = concept_res.scalars().first()

            if not concept:
                raise ValueError("Concept not found in DAG")

            step_payload = await step_executor.execute_atomic_step(
                session=session,
                deep_session=deep_session,
                concept=concept,
                step_sequence=active_idx + 1,
                user_notes=user_notes,
            )

            # Speculatively pre-generate next lesson in background while user reads this one
            if active_idx + 1 < len(nodes):
                next_node = nodes[active_idx + 1]
                step_executor.trigger_background_prefetch(
                    user_id=deep_session.user_id,
                    session_id=deep_session.id,
                    concept_id=next_node["id"],
                    step_sequence=active_idx + 2,
                    user_notes=user_notes,
                )

            await session.commit()

            return {
                "phase": "step_ready",
                "step": step_payload,
                "dag": planned_dag_schema,
            }

        # 4. State: COMPLETED (Review Mode)
        if deep_session.status == "completed":
            reconciled_dag, active_idx, active_cid, _ = await self.reconcile_dag_with_mastery(
                session=session,
                user_id=deep_session.user_id,
                dag_data=deep_session.planned_dag or {},
                requested_concept_id=None,
                current_index=deep_session.current_concept_index,
            )
            nodes = reconciled_dag.get("nodes", [])
            edges = reconciled_dag.get("edges", [])
            planned_dag_schema = PlannedDAGSchema(
                mermaid_code=reconciled_dag.get("mermaid_code", ""),
                nodes=[DAGNodeSchema(**n) for n in nodes],
                edges=[DAGEdgeSchema(**e) for e in edges],
                total_nodes=len(nodes),
                completed_nodes=len(nodes),
            )

            review_idx = min(max(0, deep_session.current_concept_index), len(nodes) - 1) if nodes else 0
            step_payload = None
            if nodes:
                review_node = nodes[review_idx]
                concept_res = await session.execute(
                    select(Concept).where(Concept.id == review_node["id"])
                )
                concept = concept_res.scalars().first()
                if concept:
                    try:
                        step_payload = await step_executor.execute_atomic_step(
                            session=session,
                            deep_session=deep_session,
                            concept=concept,
                            step_sequence=review_idx + 1,
                            user_notes=user_notes,
                        )
                        step_payload.is_session_completed = True
                    except Exception as e:
                        logger.error(f"Failed to load review step from DB: {e}")

            return {
                "phase": "completed",
                "session_id": deep_session.id,
                "step": step_payload,
                "dag": planned_dag_schema,
                "is_course_completed": True,
                "message": "Курс полностью освоен! Вы можете изучать любые уроки в режиме повторения.",
            }

        return {
            "phase": deep_session.status,
            "session_id": deep_session.id,
        }

    async def advance_to_next_node(
        self,
        session: AsyncSession,
        deep_session_id: str,
    ):
        """
        Advances the DAG index to the next concept after successful step verification.
        Dynamically reconciles mastery states, skips mastered concepts, and regenerates Mermaid highlights.
        """
        session_res = await session.execute(
            select(DeepLearningSession).where(DeepLearningSession.id == deep_session_id)
        )
        deep_session = session_res.scalars().first()
        if not deep_session:
            return

        reconciled_dag, next_idx, active_cid, is_all_completed = await self.reconcile_dag_with_mastery(
            session=session,
            user_id=deep_session.user_id,
            dag_data=deep_session.planned_dag or {},
            requested_concept_id=None,
            current_index=deep_session.current_concept_index,
            is_advancing=True,
        )

        deep_session.planned_dag = reconciled_dag
        flag_modified(deep_session, "planned_dag")
        deep_session.mermaid_diagram = reconciled_dag.get("mermaid_code", "")
        deep_session.current_concept_index = next_idx
        deep_session.current_concept_id = active_cid

        if is_all_completed:
            deep_session.status = "completed"
            if not deep_session.completed_at:
                deep_session.completed_at = datetime.utcnow()

        await session.commit()

    async def switch_concept_step(
        self,
        session: AsyncSession,
        deep_session_id: str,
        concept_id: str,
        user_notes: str = "",
    ) -> Dict[str, Any]:
        """
        Directly jumps to a specific concept within an active deep session DAG,
        reconciling mastery state and returning the step payload without re-initializing sessions.
        """
        session_res = await session.execute(
            select(DeepLearningSession).where(DeepLearningSession.id == deep_session_id)
        )
        deep_session = session_res.scalars().first()
        if not deep_session:
            raise ValueError("Session not found")

        reconciled_dag, active_idx, active_cid, is_all_completed = await self.reconcile_dag_with_mastery(
            session=session,
            user_id=deep_session.user_id,
            dag_data=deep_session.planned_dag or {},
            requested_concept_id=concept_id,
            current_index=None,
        )
        deep_session.planned_dag = reconciled_dag
        flag_modified(deep_session, "planned_dag")
        deep_session.mermaid_diagram = reconciled_dag.get("mermaid_code", "")
        deep_session.current_concept_index = active_idx
        deep_session.current_concept_id = active_cid

        await session.commit()
        return await self.get_next_action(session, deep_session.id, user_notes)


tutor_state_machine = TutorStateMachine()
