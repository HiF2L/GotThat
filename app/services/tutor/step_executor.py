import asyncio
import logging
from typing import Dict, Any, Optional, List, AsyncGenerator
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.ontology import Concept, AssessmentItem, Track
from app.models.session import DeepLearningSession, DeepSessionStep
from app.models.mastery import UserMasteryState, User
from app.schemas.tutor import (
    DeepStepPayload,
    VisualArtifactSchema,
    VerificationChallengeSchema,
    DeepStepAnswerSubmission,
    DeepStepAnswerResult,
    DAGNodeSchema,
    PlannedDAGSchema,
)
from app.schemas.feed import QuizOption
from app.config import settings
from app.services.ai.client import ai_clients
from app.services.ai.visualizer import visualizer
from app.services.ai.fact_checker import fact_checker
from app.services.ai.image_finder import image_finder
from app.services.cognitive.bkt_engine import bkt_engine

logger = logging.getLogger(__name__)


class StepExecutor:
    """
    Implements Phase 3 (TEACH) from the reference video:
    - Enforces deep, rigorous, first-principles pedagogy across all human disciplines.
    - Uses chosen AI model with generous 100s timeout for deep pedagogical mastery.
    - Speculative background pre-generation: starts generating the next lesson as soon as the student views the current one.
    - Concurrent in-flight deduplication preventing duplicate simultaneous LLM generation cascades.
    - Concurrent Subagents: SVG vector visualizer & Real Internet Image Finder.
    - Verification quiz locking + Dynamic Remediation upon cognitive error.
    """

    SYSTEM_TEACH_PROMPT = (
        "You are an inspiring, world-class professor and master practitioner across all sciences and disciplines (combining Richard Feynman's vivid intuitive storytelling with uncompromising first-principles domain rigor).\n"
        "Your mission is to make this concept EXHAUSTIVELY INFORMATIVE, intellectually captivating, deeply intuitive, and universally rigorous for ANY subject (Rocket Science, Molecular Biology, Advanced Mathematics, World History, Economics, Computer Science, Quantum Physics, Medicine, Philosophy, etc.).\n\n"
        "UNIVERSAL PEDAGOGICAL & FIRST-PRINCIPLES FRAMEWORK:\n"
        "1. THE HOOK & SPECIFIC ATOMIC DILEMMA:\n"
        "   - For Step 1 (the opening lesson): Start with the foundational real-world crisis, paradox, or historical tension that made this discipline necessary. Show why naive approaches broke down.\n"
        "   - For Step 2 and beyond: STRICTLY FORBIDDEN to repeat the broad historical crisis, author biography, or general subject introduction from Step 1. Instead, hook the student with the SPECIFIC bottleneck, technical puzzle, or conceptual conflict unique to THIS atomic concept (how the prior step's solution falls short and demands this new mechanism).\n"
        "2. THE 'AHA!' INTUITION & MENTAL MODEL (Feynman Technique): Introduce a vivid, physical or relatable mental model before formalisms, making the fundamental mechanism self-evident.\n"
        "3. DEEP FIRST-PRINCIPLES DECONSTRUCTION (ADAPTED POLYMORPHICALLY TO THE DISCIPLINE):\n"
        "   - For Exact & Natural Sciences / Engineering / Physics / Rocketry / Chemistry / Math:\n"
        "     • Exact mathematical/physical laws in LaTeX ($...$, $$...$$) with all variables and physical units defined.\n"
        "     • Step-by-step algebraic/calculus derivation and concrete numerical calculations (e.g. specific impulse Delta-v, thermal flux, reaction kinetics, or tensor memory calculations).\n"
        "     • Physical/Hardware mechanisms (aerodynamics, combustion chambers, structural loads, materials, or silicon/memory architecture).\n"
        "   - For Computer Science & Software Engineering:\n"
        "     • Architectural pipelines, protocols, memory layout, time/space complexity, and clean idiomatic code examples with line-by-line mechanics.\n"
        "   - For Biology, Genetics, Neuroscience & Medicine:\n"
        "     • Biochemical pathways, molecular cascades, cellular receptors, physiological feedback loops, and clinical/experimental evidence.\n"
        "   - For Design, UI/UX, Product, Frontend, Visual Arts & Ergonomics:\n"
        "     • ZERO CODE & ZERO RAW ALGEBRAIC FORMULAS: NEVER output Python/JS code, integral signs, or raw regression coefficients ($T = a + b \\log_2(D/W)$). Explain laws purely through spatial geometry, touch target ergonomics, screen edges/corners (infinite target width), and mental models.\n"
        "     • Visual & spatial hierarchy, typographic scale, whitespace balance, Gestalt principles (proximity, similarity, continuity, closure).\n"
        "     • Touch target ergonomics (thumb zone, 44x44pt / 48x48dp target sizing), affordances & signifiers, progressive disclosure, cognitive load reduction.\n"
        "     • Concrete UI teardowns and screen wireframes (e.g. iOS Control Center thumb zone, Spotify bottom navigation, Airbnb progressive search disclosure, Amazon 1-click checkout vs multi-step forms).\n"
        "     • UX/Cognitive Laws (Fitts, Hick, Jakob, Miller): Explain them as INTUITIVE DESIGN HEURISTICS & ERGONOMIC RULES with concrete screen layouts and user flow comparisons.\n"
        "   - For Philosophy, Ethics, History, Law, Politics, Sociology, Psychology, Linguistics, Humanities & Qualitative/Non-Mathematical Disciplines:\n"
        "     • ZERO ARTIFICIAL PSEUDO-ALGEBRAIC FORMULAS: NEVER invent fake pseudo-mathematical equations or artificial algebraic variables (e.g. NEVER output $P = J(E) \\times I$, $Trust = Reliability \\times Intimacy$, or $Virtue = Reason \\times Will$). Formal mathematical/logical notation should ONLY be used when genuinely analyzing actual formal symbolic logic (e.g. Propositional Logic, Syllogisms $P \\implies Q, \\neg Q \\vdash \\neg P$, Predicate Calculus) or empirical statistical methodology.\n"
        "     • Focus on rigorous dialectical arguments, causal mechanisms, ontological structures, authentic conceptual etymology (e.g. Greek/Latin roots like $path\\bar{e}$, $horm\\bar{e}$, $prosoch\\bar{e}$), primary historical thought experiments, and systemic qualitative tensions.\n"
        "   - For Music, Audio Engineering & Sound Design:\n"
        "     • Frequency spectrum, harmonic series, psychoacoustics, rhythm meters, dynamic range, arrangement structure.\n"
        "4. CONCRETE WORKED CASE STUDY / EVIDENCE: Walk through a real tangible scenario, calculation, primary experiment, or code implementation showing the concept in action.\n"
        "5. FRONTIER & MODERN STATE-OF-THE-ART: Explain how leading scientists, engineers, or top researchers push this frontier today.\n"
        "6. 'WHERE 90% STUMBLE' (Subtle Traps & Fallacies): Point out counter-intuitive misconceptions, subtle edge cases, or common fallacies that trap amateurs.\n"
        "7. HIGH INFORMATIONAL DENSITY: Deliver a comprehensive, deeply explanatory narrative (typically 700 to 1400 words of rich content). Never produce shallow or brief summaries.\n"
        "8. REAL-WORLD IMAGES: Set `needs_real_image: true` ONLY when an authentic real diagram, historical photo, micrograph, or official tech logo genuinely exists and clarifies the concept (e.g. 'Saturn V rocket F-1 engine', 'CRISPR Cas9 molecular complex', 'FastAPI framework logo'). Set `real_image_search_query` in English. If the topic is conceptual/theoretical and better illustrated by a vector schematic, set `needs_real_image: false`.\n"
        "9. CRITICAL LANGUAGE MANDATE: All explanations, annotations, questions, and options MUST strictly be in the SAME LANGUAGE as the Concept Title (if in Russian, natural, expressive, academic Russian; if in English, English).\n"
        "10. CONSTITUTIONAL SAFETY & ACADEMIC INTEGRITY:\n"
        "    - STRICTLY FORBIDDEN: Any actionable instructions for manufacturing weapons, explosives, synthesizing illegal drugs, developing malware/exploits, carrying out fraud, promoting contemporary political propaganda/militarism, or engaging in immoral/unethical behavior.\n"
        "    - If explaining cybersecurity or dual-use science, focus 100% on DEFENSIVE mitigations, secure design, and formal theory.\n"
        "11. PROGRESSIVE CURRICULAR CONTINUITY & ANTI-REPETITION MANDATE:\n"
        "    - The student is progressing step-by-step through a course. They have ALREADY read and mastered all previous lessons!\n"
        "    - NEVER repeat foundational metaphors or thought experiments (e.g. if an introductory analogy like 'white swans' or 'detective' was used earlier, DO NOT use it again).\n"
        "    - NEVER re-introduce the overall subject, author, or field from scratch. Jump directly into the distinct, advanced mechanics and nuanced reality of THIS atomic concept.\n\n"
        "Output JSON matching this structure:\n"
        "{\n"
        '  "explanation_markdown": "Exhaustive, storytelling-driven, first-principles tutorial text tailored to the domain with complete mechanics, formulas/sources/code, and real-world depth",\n'
        '  "needs_visual_diagram": true,\n'
        '  "visual_focus_description": "Substantive architectural schematic or circuit flow illustrating internal mechanisms and states (never a trivial 3-box arrow)",\n'
        '  "needs_real_image": false,\n'
        '  "real_image_search_query": "Precise English entity query for Wikipedia/Wikimedia or Tech Logo if applicable",\n'
        '  "verification_question": {\n'
        '     "prompt": "Thought-provoking, practical question testing true first-principles understanding of this step",\n'
        '     "options": [\n'
        '        {"id": "a", "text": "...", "is_correct": true, "explanation": "Why correct"},\n'
        '        {"id": "b", "text": "...", "is_correct": false, "explanation": "Why incorrect"},\n'
        '        {"id": "c", "text": "...", "is_correct": false, "explanation": "Why incorrect"},\n'
        '        {"id": "d", "text": "...", "is_correct": false, "explanation": "Why incorrect"}\n'
        '     ]\n'
        '  }\n'
        "}"
    )

    def _build_step_payload_from_db(
        self,
        step: DeepSessionStep,
        concept: Concept,
        deep_session: DeepLearningSession,
        step_sequence: Optional[int] = None,
    ) -> DeepStepPayload:
        effective_sequence = step_sequence or step.step_sequence or 1
        visual_artifact = None
        if step.visual_type and step.visual_payload:
            visual_artifact = VisualArtifactSchema(
                type=step.visual_type,
                payload=step.visual_payload,
                alt_text=step.visual_alt or f"Visual Representation of {concept.title}",
            )

        v_challenge = None
        if step.verification_challenge:
            v_data = step.verification_challenge
            opts = [
                QuizOption(
                    id=o.get("id", "a"),
                    text=o.get("text", ""),
                    is_correct=o.get("is_correct", False),
                    explanation=o.get("explanation", ""),
                )
                for o in v_data.get("options", [])
            ]
            v_challenge = VerificationChallengeSchema(
                item_id=v_data.get("item_id", f"lock_{step.concept_id}_{effective_sequence}"),
                prompt_markdown=v_data.get("prompt_markdown", f"Verify your mastery of **{concept.title}**:"),
                options=opts,
                allow_voice=v_data.get("allow_voice", True),
            )

        from app.core.slug import generate_slug
        c_slug = concept.slug or generate_slug(concept.title)

        from app.services.ai.client import sanitize_markdown_text
        exp_md = sanitize_markdown_text(step.explanation_markdown or "")

        return DeepStepPayload(
            session_id=deep_session.id,
            concept_id=concept.id,
            concept_title=concept.title,
            concept_slug=c_slug,
            track_id=concept.track_id,
            step_sequence=effective_sequence,
            step_type=step.step_type or "explanation",
            explanation_markdown=exp_md,
            visual_artifact=visual_artifact,
            verification_challenge=v_challenge,
            is_session_completed=False,
            dag_state=None,
            qa_history=step.qa_history or [],
        )

    def __init__(self):
        self._in_flight_tasks: Dict[str, asyncio.Task] = {}
        self._task_lock = asyncio.Lock()

    def trigger_background_prefetch(
        self,
        user_id: str,
        session_id: str,
        concept_id: str,
        step_sequence: int,
        user_notes: str = "",
    ):
        """
        Non-blocking trigger to pre-generate the next lessons in background.
        Delegates to the rolling 2-lesson ahead text & audio pipeline.
        """
        self.trigger_background_prefetch_pipeline(
            user_id=user_id,
            session_id=session_id,
            current_concept_id=concept_id,
            current_sequence=step_sequence,
        )

    def trigger_background_prefetch_pipeline(
        self,
        user_id: str,
        session_id: str,
        current_concept_id: str,
        current_sequence: int,
    ):
        """
        Non-blocking trigger to pre-generate the next 2 lessons (both text and TTS audio).
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self.prefetch_pipeline(
                    user_id=user_id,
                    session_id=session_id,
                    current_concept_id=current_concept_id,
                    current_sequence=current_sequence,
                )
            )
        except Exception as e:
            logger.warning(f"Could not schedule rolling prefetch pipeline: {e}")

    async def prefetch_pipeline(
        self,
        user_id: str,
        session_id: str,
        current_concept_id: str,
        current_sequence: int,
    ):
        """
        Rolling 2-Lesson Ahead Pipeline:
        Proactively pre-generates full text AND TTS audio for the next 2 subsequent lessons (N+1 and N+2).
        Runs in detached background tasks so closing the tab or reloading never aborts generation.
        """
        from app.core.database import async_session_maker
        from app.services.ai.tts_service import tts_service

        task_key = f"pipeline:{session_id}:{current_concept_id}"
        async with self._task_lock:
            if task_key in self._in_flight_tasks and not self._in_flight_tasks[task_key].done():
                return

        async def _pipeline_worker():
            try:
                async with async_session_maker() as db:
                    s_res = await db.execute(
                        select(DeepLearningSession).where(DeepLearningSession.id == session_id)
                    )
                    deep_sess = s_res.scalars().first()
                    if not deep_sess or not deep_sess.planned_dag:
                        return

                    nodes = deep_sess.planned_dag.get("nodes", [])
                    if not nodes:
                        return

                    # Find current node index
                    curr_idx = -1
                    for idx, n in enumerate(nodes):
                        if n.get("id") == current_concept_id or n.get("concept_id") == current_concept_id:
                            curr_idx = idx
                            break
                    if curr_idx == -1:
                        curr_idx = max(0, current_sequence - 1)

                    # Next 2 upcoming nodes
                    upcoming = nodes[curr_idx + 1 : curr_idx + 3]
                    for offset, target_node in enumerate(upcoming):
                        target_cid = target_node.get("id") or target_node.get("concept_id")
                        target_seq = curr_idx + 1 + offset + 1
                        if not target_cid:
                            continue

                        st = None
                        step_res = await db.execute(
                            select(DeepSessionStep)
                            .where(
                                and_(
                                    DeepSessionStep.session_id == session_id,
                                    DeepSessionStep.concept_id == target_cid,
                                    DeepSessionStep.explanation_markdown.isnot(None),
                                )
                            )
                            .order_by(DeepSessionStep.created_at.desc())
                        )
                        for s in step_res.scalars().all():
                            if s.explanation_markdown and len(s.explanation_markdown.strip()) > 50:
                                st = s
                                break

                        # Check global cache if not in session
                        if not st:
                            gst_res = await db.execute(
                                select(DeepSessionStep)
                                .where(
                                    and_(
                                        DeepSessionStep.concept_id == target_cid,
                                        DeepSessionStep.explanation_markdown.isnot(None),
                                    )
                                )
                                .order_by(DeepSessionStep.created_at.desc())
                            )
                            for s in gst_res.scalars().all():
                                if s.explanation_markdown and len(s.explanation_markdown.strip()) > 50:
                                    st = DeepSessionStep(
                                        session_id=session_id,
                                        concept_id=target_cid,
                                        step_sequence=target_seq,
                                        step_type=s.step_type or "explanation",
                                        explanation_markdown=s.explanation_markdown,
                                        visual_type=s.visual_type,
                                        visual_payload=s.visual_payload,
                                        visual_alt=s.visual_alt,
                                        verification_challenge=s.verification_challenge,
                                        verification_passed=False,
                                    )
                                    db.add(st)
                                    await db.commit()
                                    await db.refresh(st)
                                    break

                        if not st or not st.explanation_markdown or len(st.explanation_markdown.strip()) <= 50:
                            # Generate text in background
                            c_res = await db.execute(select(Concept).where(Concept.id == target_cid))
                            target_c = c_res.scalars().first()
                            if target_c:
                                logger.info(f"[Pipeline] Proactively pre-generating text for '{target_c.title}' (step {target_seq})...")
                                p = await self.execute_atomic_step(
                                    session=db,
                                    deep_session=deep_sess,
                                    concept=target_c,
                                    step_sequence=target_seq,
                                )
                                if p and p.explanation_markdown:
                                    logger.info(f"[Pipeline] Text ready for '{target_c.title}'. Pre-generating TTS audio...")
                                    await tts_service.prefetch_audio(p.explanation_markdown)
                        else:
                            # Step text already exists in DB! Ensure TTS audio is synthesized and cached on disk!
                            logger.info(f"[Pipeline] Step text already cached for node {target_cid}. Pre-generating TTS audio...")
                            await tts_service.prefetch_audio(st.explanation_markdown)

            except Exception as e:
                logger.warning(f"Error in prefetch_pipeline: {e}")
            finally:
                async with self._task_lock:
                    self._in_flight_tasks.pop(task_key, None)

        try:
            loop = asyncio.get_running_loop()
            t = loop.create_task(_pipeline_worker())
            async with self._task_lock:
                self._in_flight_tasks[task_key] = t
        except Exception as e:
            logger.warning(f"Could not launch pipeline worker: {e}")

    async def execute_atomic_step(
        self,
        session: AsyncSession,
        deep_session: DeepLearningSession,
        concept: Concept,
        step_sequence: int,
        user_notes: str = "",
        force_regenerate: bool = False,
    ) -> DeepStepPayload:
        # 0. Check if this exact step was ALREADY generated and persisted in SQLite
        if not force_regenerate:
            existing_step = None
            existing_step_res = await session.execute(
                select(DeepSessionStep)
                .where(
                    and_(
                        DeepSessionStep.session_id == deep_session.id,
                        DeepSessionStep.concept_id == concept.id,
                        DeepSessionStep.explanation_markdown.isnot(None),
                    )
                )
                .order_by(DeepSessionStep.created_at.desc())
            )
            for s in existing_step_res.scalars().all():
                if s.explanation_markdown and len(s.explanation_markdown.strip()) > 50:
                    existing_step = s
                    break

            if not existing_step:
                global_step_res = await session.execute(
                    select(DeepSessionStep)
                    .where(
                        and_(
                            DeepSessionStep.concept_id == concept.id,
                            DeepSessionStep.explanation_markdown.isnot(None),
                        )
                    )
                    .order_by(DeepSessionStep.created_at.desc())
                )
                for s in global_step_res.scalars().all():
                    if s.explanation_markdown and len(s.explanation_markdown.strip()) > 50:
                        existing_step = s
                        break

            if existing_step and existing_step.explanation_markdown and len(existing_step.explanation_markdown.strip()) > 50:
                logger.info(f"Restoring cached Step {step_sequence} for '{concept.title}' from DB with 0ms latency.")
                if existing_step.session_id != deep_session.id:
                    # Persist a row for the current session so evaluate_step_answer and progress tracking find it
                    cloned_step = DeepSessionStep(
                        session_id=deep_session.id,
                        concept_id=concept.id,
                        step_sequence=step_sequence,
                        step_type=existing_step.step_type or "explanation",
                        explanation_markdown=existing_step.explanation_markdown,
                        visual_type=existing_step.visual_type,
                        visual_payload=existing_step.visual_payload,
                        visual_alt=existing_step.visual_alt,
                        verification_challenge=existing_step.verification_challenge,
                    )
                    session.add(cloned_step)
                    await session.commit()
                    existing_step = cloned_step
                payload = self._build_step_payload_from_db(existing_step, concept, deep_session, step_sequence)
                from app.services.ai.tts_service import tts_service
                asyncio.create_task(tts_service.prefetch_audio(payload.explanation_markdown))
                self.trigger_background_prefetch_pipeline(
                    user_id=deep_session.user_id,
                    session_id=deep_session.id,
                    current_concept_id=concept.id,
                    current_sequence=step_sequence,
                )
                return payload

        # 1. Check if an in-flight generation task is already running for this exact session & concept
        task_key = f"{deep_session.id}:{concept.id}"
        in_flight_task = None

        async with self._task_lock:
            if not force_regenerate and task_key in self._in_flight_tasks and not self._in_flight_tasks[task_key].done():
                in_flight_task = self._in_flight_tasks[task_key]
            elif not force_regenerate:
                # Leader creates a Future for concurrent followers to wait on
                future = asyncio.get_running_loop().create_future()
                self._in_flight_tasks[task_key] = future

        if in_flight_task:
            logger.info(f"Joining in-flight generation task for '{concept.title}' ({task_key})")
            try:
                result = await in_flight_task
                if isinstance(result, DeepStepPayload):
                    return result
            except Exception as e:
                logger.warning(f"In-flight task raised: {e}, falling back to direct execution")

            # Check DB again after in-flight task completed
            existing_step_res = await session.execute(
                select(DeepSessionStep)
                .where(
                    and_(
                        DeepSessionStep.session_id == deep_session.id,
                        DeepSessionStep.concept_id == concept.id,
                    )
                )
                .order_by(DeepSessionStep.step_sequence.desc())
            )
            existing_step = existing_step_res.scalars().first()
            if existing_step and existing_step.explanation_markdown:
                return self._build_step_payload_from_db(existing_step, concept, deep_session, step_sequence)

        # 2. Leader executes generation and broadcasts result to followers
        try:
            payload = await self._do_execute_atomic_step(
                session=session,
                deep_session=deep_session,
                concept=concept,
                step_sequence=step_sequence,
                user_notes=user_notes,
            )
            async with self._task_lock:
                fut = self._in_flight_tasks.get(task_key)
                if fut and isinstance(fut, asyncio.Future) and not fut.done():
                    fut.set_result(payload)
            return payload
        except Exception as e:
            async with self._task_lock:
                fut = self._in_flight_tasks.get(task_key)
                if fut and isinstance(fut, asyncio.Future) and not fut.done():
                    fut.set_exception(e)
            raise
        finally:
            async with self._task_lock:
                self._in_flight_tasks.pop(task_key, None)

    async def _do_execute_atomic_step(
        self,
        session: AsyncSession,
        deep_session: DeepLearningSession,
        concept: Concept,
        step_sequence: int,
        user_notes: str = "",
    ) -> DeepStepPayload:
        # 0. Check cache once more under direct session
        existing_step = None
        existing_step_res = await session.execute(
            select(DeepSessionStep)
            .where(
                and_(
                    DeepSessionStep.session_id == deep_session.id,
                    DeepSessionStep.concept_id == concept.id,
                    DeepSessionStep.explanation_markdown.isnot(None),
                )
            )
            .order_by(DeepSessionStep.created_at.desc())
        )
        for s in existing_step_res.scalars().all():
            if s.explanation_markdown and len(s.explanation_markdown.strip()) > 50:
                existing_step = s
                break

        if not existing_step:
            global_step_res = await session.execute(
                select(DeepSessionStep)
                .where(
                    and_(
                        DeepSessionStep.concept_id == concept.id,
                        DeepSessionStep.explanation_markdown.isnot(None),
                    )
                )
                .order_by(DeepSessionStep.created_at.desc())
            )
            for s in global_step_res.scalars().all():
                if s.explanation_markdown and len(s.explanation_markdown.strip()) > 50:
                    cloned = DeepSessionStep(
                        session_id=deep_session.id,
                        concept_id=concept.id,
                        step_sequence=step_sequence,
                        step_type=s.step_type or "explanation",
                        explanation_markdown=s.explanation_markdown,
                        visual_type=s.visual_type,
                        visual_payload=s.visual_payload,
                        visual_alt=s.visual_alt,
                        verification_challenge=s.verification_challenge,
                        verification_passed=False,
                    )
                    session.add(cloned)
                    await session.commit()
                    await session.refresh(cloned)
                    existing_step = cloned
                    break

        if existing_step and existing_step.explanation_markdown and len(existing_step.explanation_markdown.strip()) > 50:
            payload = self._build_step_payload_from_db(existing_step, concept, deep_session, step_sequence)
            from app.services.ai.tts_service import tts_service
            asyncio.create_task(tts_service.prefetch_audio(payload.explanation_markdown))
            return payload

        # 1. Gather rich course progression context
        track_title = "Курс"
        track_wishes = None
        if concept and concept.track_id:
            try:
                t_res = await session.execute(select(Track).where(Track.id == concept.track_id))
                t_obj = t_res.scalars().first()
                if t_obj:
                    if t_obj.title:
                        track_title = t_obj.title
                    if t_obj.user_wishes:
                        track_wishes = t_obj.user_wishes
            except Exception:
                pass

        planned_nodes = (deep_session.planned_dag or {}).get("nodes", [])
        total_steps = len(planned_nodes) or 1
        prior_steps_overview = []
        for i, pn in enumerate(planned_nodes[:max(0, step_sequence - 1)]):
            prior_steps_overview.append(f"• Урок {i+1} [{pn.get('code', '')}]: {pn.get('title', '')}")
        prior_lessons_str = "\n".join(prior_steps_overview) if prior_steps_overview else "Это самый первый урок курса."

        upcoming_nodes = planned_nodes[step_sequence:step_sequence + 3]
        upcoming_str = ", ".join([f"[{un.get('code', '')}] {un.get('title', '')}" for un in upcoming_nodes]) if upcoming_nodes else "Завершающие разделы курса."

        student_notes_prompt = ""
        if user_notes and user_notes.strip():
            student_notes_prompt = (
                f"\nSTUDENT'S EXPLICIT REASONING / WISHES FOR THIS STEP:\n"
                f"\"{user_notes.strip()}\"\n"
                f"PEDAGOGICAL DIRECTIVE: Proactively weave this student reflection, interest, or specific angle into the explanation and examples where natural and illuminating!\n"
            )

        wishes_context = f"Student Course Wishes / Pedagogical Preferences: {track_wishes}\n" if track_wishes else ""

        anti_repetition_mandate = (
            f"PROGRESSIVE COURSE CONTEXT:\n"
            f"• Course: «{track_title}»\n"
            f"• Current Position: Lesson Step {step_sequence} of {total_steps}\n"
            f"• Already Mastered Lessons in this Course:\n{prior_lessons_str}\n"
            f"• Upcoming Lessons (DO NOT ENCROACH ON THESE):\n{upcoming_str}\n\n"
            f"CRITICAL ANTI-REPETITION & PROGRESSION MANDATE:\n"
            f"- The student has ALREADY finished all earlier lessons listed above. DO NOT re-introduce the overall subject, the author's biography, or foundational background that was already covered in Lesson 1.\n"
            f"- NEVER REUSE earlier analogies, metaphors, or thought experiments (e.g. if 'white swans', generic detectives, or basic definitions were used, DO NOT mention them again!).\n"
            f"- Jump DIRECTLY and EXCLUSIVELY into the specific, advanced, and unique mechanics of THIS concept: '{concept.title}' ({concept.code}). Every paragraph must provide FRESH, non-redundant insight.\n"
        )

        target_lang = getattr(deep_session, "language", None) or "ru"
        is_russian = (target_lang == "ru") or any('\u0400' <= char <= '\u04FF' for char in (concept.title or ""))
        if target_lang == "en":
            is_russian = False

        lang_mandate = (
            "CRITICAL LANGUAGE MANDATE: You MUST write the ENTIRE explanation, headings, code explanations, verification questions, and options in RUSSIAN (Русский язык). "
            "Even if the topic or code uses English keywords (like FastAPI, Depends, APIRouter, Middleware), ALL pedagogical prose and explanations MUST strictly be in Russian. NEVER switch to English."
            if is_russian
            else "CRITICAL LANGUAGE MANDATE: You MUST write the ENTIRE explanation, headings, questions, and options in ENGLISH."
        )

        # Resolve active model: User preference from DB takes strict priority over .env default
        active_model = settings.DEEP_MODEL
        if deep_session and deep_session.user_id:
            try:
                user_res = await session.execute(
                    select(User.preferred_model).where(User.id == deep_session.user_id)
                )
                pref = user_res.scalars().first()
                if pref and pref.strip():
                    active_model = pref.strip()
            except Exception as e:
                logger.warning(f"Could not query User.preferred_model: {e}")

        # 2. Call teaching LLM with deep pedagogy prompt
        messages = [
            {"role": "system", "content": self.SYSTEM_TEACH_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{anti_repetition_mandate}\n"
                    f"CURRENT ATOMIC CONCEPT TO TEACH: {concept.title} ({concept.code})\n"
                    f"Concept Summary: {concept.summary}\n"
                    f"{wishes_context}"
                    f"{student_notes_prompt}"
                    f"Target Language: {'Russian (Русский язык)' if is_russian else 'English'}\n"
                    f"{lang_mandate}\n\n"
                    "Generate a deep, storytelling-driven, intuitive atomic tutorial and verification challenge."
                ),
            },
        ]

        llm_response = await ai_clients.generate_json(
            messages=messages,
            model=active_model,
            temperature=0.25,
            timeout_seconds=120.0,
            task_type="step_teaching",
        )

        explanation = ""
        if isinstance(llm_response, dict):
            if isinstance(llm_response.get("explanation_markdown"), str) and len(llm_response["explanation_markdown"].strip()) > 100:
                explanation = llm_response["explanation_markdown"].strip()
            elif isinstance(llm_response.get("explanation"), str) and len(llm_response["explanation"].strip()) > 100:
                explanation = llm_response["explanation"].strip()
            else:
                parts = []
                # Title
                title = llm_response.get("title")
                if title and str(title).strip() != concept.title:
                    parts.append(f"# {str(title).strip()}\n")

                # 1. Hook / Problem / Dilemma
                hook = (
                    llm_response.get("hook_and_dilemma")
                    or llm_response.get("hook")
                    or llm_response.get("story")
                    or llm_response.get("problem")
                    or llm_response.get("dilemma")
                )
                if hook:
                    parts.append(f"{str(hook).strip()}\n")
                
                # 2. Intuition / Mental Model
                intuition = (
                    llm_response.get("aha_intuition")
                    or llm_response.get("mental_model")
                    or llm_response.get("intuition")
                    or llm_response.get("metaphor")
                )
                if intuition:
                    parts.append(f"### 💡 Интуиция и ментальная модель\n{str(intuition).strip()}\n")

                # 3. Deep First-Principles Mechanics / Mathematical / Structural Rigor
                mechanics = (
                    llm_response.get("first_principles_deconstruction")
                    or llm_response.get("deep_mechanics")
                    or llm_response.get("mathematical_rigor")
                    or llm_response.get("technical_deconstruction")
                    or llm_response.get("mechanics")
                    or llm_response.get("laws_and_formulas")
                    or llm_response.get("pathways")
                )
                if mechanics:
                    if isinstance(mechanics, dict):
                        m_parts = ["### 📐 Первопринципный и фундаментальный разбор"]
                        if mechanics.get("formula") or mechanics.get("equation"):
                            m_parts.append(f"$$\n{mechanics.get('formula') or mechanics.get('equation')}\n$$")
                        if mechanics.get("tensor_dimensions") or mechanics.get("variables_definition") or mechanics.get("variables"):
                            vars_dict = mechanics.get("tensor_dimensions") or mechanics.get("variables_definition") or mechanics.get("variables")
                            if isinstance(vars_dict, dict):
                                vars_str = "\n".join([f"• **{k}**: `${v}$`" for k, v in vars_dict.items()])
                                m_parts.append(f"**Определения и размерности параметров:**\n{vars_str}")
                            else:
                                m_parts.append(f"**Параметры:** {vars_dict}")
                        if mechanics.get("complexity_analysis") or mechanics.get("quantitative_analysis"):
                            qa = mechanics.get("complexity_analysis") or mechanics.get("quantitative_analysis")
                            if isinstance(qa, dict):
                                for qk, qv in qa.items():
                                    m_parts.append(f"• **{qk.replace('_', ' ').capitalize()}:** `{qv}`")
                            elif isinstance(qa, str):
                                m_parts.append(f"\n> **Количественный / системный расчет:** {qa}")
                        parts.append("\n".join(m_parts) + "\n")
                    elif isinstance(mechanics, str):
                        parts.append(f"### 📐 Первопринципный и фундаментальный разбор\n{mechanics.strip()}\n")

                # 4. Systems / Physical / Biochemical / Causal Breakdown
                systems = (
                    llm_response.get("systems_breakdown")
                    or llm_response.get("hardware_breakdown")
                    or llm_response.get("biochemical_pathway")
                    or llm_response.get("causal_analysis")
                )
                if systems:
                    if isinstance(systems, dict):
                        s_parts = ["### ⚙️ Механизм действия и подсистемы"]
                        for sk, sv in systems.items():
                            s_parts.append(f"• **{sk.replace('_', ' ').capitalize()}:** {sv}")
                        parts.append("\n".join(s_parts) + "\n")
                    elif isinstance(systems, str):
                        parts.append(f"### ⚙️ Механизм действия и подсистемы\n{systems.strip()}\n")

                # 5. Concrete Worked Case Study / Code / Evidence
                case = (
                    llm_response.get("case_study")
                    or llm_response.get("worked_case_study")
                    or llm_response.get("code_example")
                    or llm_response.get("experiment")
                    or llm_response.get("example")
                )
                if case:
                    if isinstance(case, dict):
                        c_parts = ["### 🔬 Прикладной разбор и доказательства"]
                        if case.get("description") or case.get("context"):
                            c_parts.append(str(case.get("description") or case.get("context")))
                        snippet = case.get("snippet") or case.get("code") or case.get("proof") or ""
                        lang = case.get("language") or "python"
                        if snippet:
                            snip_str = str(snippet).strip()
                            if not snip_str.startswith("```"):
                                c_parts.append(f"```{lang}\n{snip_str}\n```")
                            else:
                                c_parts.append(snip_str)
                        parts.append("\n".join(c_parts) + "\n")
                    elif isinstance(case, str):
                        case_str = case.strip()
                        if not case_str.startswith("```") and "```" not in case_str and len(case_str) > 30:
                            parts.append(f"### 🔬 Прикладной разбор\n{case_str}\n")
                        else:
                            parts.append(f"### 🔬 Практическая реализация\n{case_str}\n")
                    elif isinstance(case, list):
                        parts.append("### 🔬 Прикладные примеры и доказательства\n" + "\n".join([f"• {c}" for c in case]) + "\n")

                # 6. Modern Frontier / State of the Art / Breakthroughs
                solutions = (
                    llm_response.get("frontier_and_state_of_art")
                    or llm_response.get("frontier_and_state_of_the_art")
                    or llm_response.get("frontier_state_of_the_art")
                    or llm_response.get("modern_frontier")
                    or llm_response.get("modern_solutions")
                    or llm_response.get("solutions")
                    or llm_response.get("modern_developments")
                )
                if solutions:
                    sol_parts = ["### 🚀 Передний край науки и современные прорывы (State of the Art)"]
                    if isinstance(solutions, list):
                        for s in solutions:
                            if isinstance(s, dict):
                                name = s.get("name") or s.get("title") or "Направление"
                                desc = s.get("description") or s.get("details") or ""
                                sol_parts.append(f"• **{name}**: {desc}")
                            else:
                                sol_parts.append(f"• {s}")
                    elif isinstance(solutions, str):
                        sol_parts.append(solutions.strip())
                    parts.append("\n".join(sol_parts) + "\n")

                # 7. Pro-Tips / Traps / Where 90% Stumble
                tips = (
                    llm_response.get("common_traps")
                    or llm_response.get("pro_tips")
                    or llm_response.get("gotchas")
                    or llm_response.get("pitfalls")
                    or llm_response.get("subtle_misconceptions")
                )
                if tips:
                    if isinstance(tips, list):
                        tips_text = "\n".join([f"• {t}" for t in tips])
                        parts.append(f"### ⚠️ Где спотыкаются 90% & Экспертные нюансы\n{tips_text}\n")
                    else:
                        parts.append(f"### ⚠️ Где спотыкаются 90% & Экспертные нюансы\n{str(tips).strip()}\n")

                if parts:
                    explanation = "\n".join(parts)

        if not explanation or len(explanation.strip()) < 50:
            raw_chat_resp = await ai_clients.generate_chat(
                messages=[
                    {
                        "role": "system",
                        "content": self.SYSTEM_TEACH_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Current Concept to Teach: {concept.title} ({concept.code})\n"
                            f"Concept Summary: {concept.summary}\n"
                            f"Step Sequence: {step_sequence}\n"
                            f"Target Language: {'Russian (Русский язык)' if is_russian else 'English'}\n"
                            f"{lang_mandate}\n"
                            "Generate an exhaustive, deeply intuitive, storytelling-driven atomic tutorial tailored strictly to this specific discipline (DO NOT include code for non-programming topics!)."
                        ),
                    },
                ],
                model=settings.FAST_MODEL,
                temperature=0.3,
                max_tokens=6144,
                timeout_seconds=15.0,
            )
            from app.services.ai.client import extract_json_or_fallback
            parsed_chat = extract_json_or_fallback(raw_chat_resp)
            if parsed_chat and isinstance(parsed_chat, dict):
                llm_response = parsed_chat
                if parsed_chat.get("explanation_markdown"):
                    explanation = str(parsed_chat["explanation_markdown"]).strip()
                elif parsed_chat.get("explanation"):
                    explanation = str(parsed_chat["explanation"]).strip()
                else:
                    explanation = raw_chat_resp.strip()
            else:
                explanation = raw_chat_resp.strip()

        # Bulletproof check: Guarantee explanation is never a raw JSON dump
        from app.services.ai.client import sanitize_markdown_text
        explanation = sanitize_markdown_text(explanation or "").strip()
        clean_exp = explanation
        if (clean_exp.startswith("{") and '"explanation' in clean_exp) or (clean_exp.startswith("```json") and '"explanation' in clean_exp):
            from app.services.ai.client import extract_json_or_fallback
            extracted_obj = extract_json_or_fallback(clean_exp)
            if extracted_obj and isinstance(extracted_obj, dict):
                if extracted_obj.get("explanation_markdown"):
                    explanation = str(extracted_obj["explanation_markdown"]).strip()
                elif extracted_obj.get("explanation"):
                    explanation = str(extracted_obj["explanation"]).strip()
                if not llm_response or not isinstance(llm_response, dict) or not llm_response.get("verification_question"):
                    llm_response = extracted_obj

        if not explanation:
            explanation = f"### {concept.title}\n\n{concept.summary}"

        needs_visual = llm_response.get("needs_visual_diagram", True) if isinstance(llm_response, dict) else True
        visual_desc = llm_response.get("visual_focus_description", concept.title) if isinstance(llm_response, dict) else concept.title
        needs_image = llm_response.get("needs_real_image", False) if isinstance(llm_response, dict) else False
        image_query = llm_response.get("real_image_search_query") if isinstance(llm_response, dict) else None

        v_quiz_data = (
            llm_response.get("verification_question")
            or llm_response.get("verification_challenge")
            or llm_response.get("quiz")
            or {}
        ) if isinstance(llm_response, dict) else {}

        # 3, 4 & 5. Run Subagents in Parallel: Fact-Check, SVG Visualizer, and Real Internet Image Finder
        # 3 & 4. Primary Visual Pipeline: Check authentic images first (0 API tokens, fast <0.5s HTTP lookup)
        img_result = None
        effective_query = image_query or concept.title
        if effective_query and len(effective_query.strip()) >= 2:
            try:
                img_result = await asyncio.wait_for(
                    image_finder.find_educational_image(
                        query=effective_query,
                        concept_title=concept.title,
                    ),
                    timeout=5.0,
                )
            except Exception as e:
                logger.warning(f"Image search timed out or failed: {e}")

        # If no authentic image was found and a diagram is requested, generate an SVG schematic
        svg_result = None
        has_real_image = isinstance(img_result, dict) and bool(img_result.get("url"))
        if not has_real_image and needs_visual:
            try:
                svg_result = await asyncio.wait_for(
                    visualizer.generate_visualization(
                        concept_title=concept.title,
                        explanation_context=explanation,
                        target_aspect=visual_desc,
                    ),
                    timeout=35.0,
                )
            except Exception as e:
                logger.warning(f"SVG visualizer timed out or failed: {e}")

        visual_artifact = None

        def insert_in_between_markdown(text: str, embed_block: str) -> str:
            # Look for ideal editorial split headers near Section 1/2
            split_headers = [
                "### 1.",
                "#### 1.",
                "## 1.",
                "1. Закон",
                "1. ",
                "### 💡 Интуиция",
                "### 2.",
                "#### 2.",
                "## 2.",
                "2. ",
                "### ⚙️ Механизм",
                "### 🔬",
                "### Анатомия",
            ]
            for h in split_headers:
                if h in text:
                    parts = text.split(h, 1)
                    return f"{parts[0].rstrip()}\n\n{embed_block}\n\n{h}{parts[1]}"
            
            # Fallback: insert after 1st or 2nd paragraph
            paras = text.split("\n\n")
            if len(paras) >= 2:
                return f"{paras[0]}\n\n{embed_block}\n\n" + "\n\n".join(paras[1:])
            return f"{embed_block}\n\n{text}"

        # 1. Single Primary Visual Policy: If a verified authentic educational image is found, embed it
        if isinstance(img_result, dict) and img_result.get("url"):
            img_url = img_result["url"]
            img_caption = img_result.get("caption", concept.title)
            # Embed image in markdown seamlessly in-between paragraphs if not already present
            if img_url not in explanation:
                image_md = f"![{img_caption}]({img_url})"
                explanation = insert_in_between_markdown(explanation, image_md)
            visual_artifact = VisualArtifactSchema(
                type="image",
                payload=img_url,
                alt_text=img_caption,
            )
        # 2. If no real image was found, use the high-density SVG schematic
        elif isinstance(svg_result, VisualArtifactSchema) and svg_result.payload:
            visual_artifact = svg_result
        elif isinstance(svg_result, dict) and svg_result.get("payload"):
            visual_artifact = VisualArtifactSchema(
                type="svg",
                payload=svg_result["payload"],
                alt_text=svg_result.get("alt_text", f"Circuit Diagram for {concept.title}"),
            )

        # 5. Construct Verification Challenge Lock
        opts = []
        raw_opts = v_quiz_data.get("options", [])
        correct_ans = str(v_quiz_data.get("correct_answer") or "").strip()
        option_letters = ["a", "b", "c", "d", "e"]
        for idx, opt in enumerate(raw_opts):
            if isinstance(opt, dict):
                opts.append(
                    QuizOption(
                        id=opt.get("id") or option_letters[idx % len(option_letters)],
                        text=opt.get("text") or str(opt.get("option", "")),
                        is_correct=opt.get("is_correct", False) or (bool(correct_ans) and correct_ans in str(opt.get("text", ""))),
                        explanation=opt.get("explanation", ""),
                    )
                )
            elif isinstance(opt, str):
                is_corr = (bool(correct_ans) and correct_ans in opt) or (idx == 0 and not correct_ans)
                opts.append(
                    QuizOption(
                        id=option_letters[idx % len(option_letters)],
                        text=opt,
                        is_correct=is_corr,
                        explanation=v_quiz_data.get("explanation", ""),
                    )
                )

        is_russian = any('\u0400' <= char <= '\u04FF' for char in (concept.title or ""))
        v_prompt = (
            v_quiz_data.get("prompt")
            or v_quiz_data.get("question")
            or v_quiz_data.get("prompt_markdown")
        )

        if not opts or len(opts) < 2:
            try:
                q_res = await ai_clients.generate_json(
                    messages=[
                        {
                            "role": "system",
                            "content": "Generate 1 conceptual multiple-choice question testing understanding. Output JSON: {\"prompt\": \"...\", \"options\": [{\"id\": \"a\", \"text\": \"...\", \"is_correct\": true, \"explanation\": \"...\"}, {\"id\": \"b\", \"text\": \"...\", \"is_correct\": false, \"explanation\": \"...\"}]}",
                        },
                        {"role": "user", "content": f"Topic: {concept.title}\nContext: {explanation[:1000]}"},
                    ],
                    model=settings.FAST_MODEL,
                    temperature=0.2,
                    task_type="step_quiz_fallback",
                )
                if q_res and q_res.get("options"):
                    opts = [
                        QuizOption(
                            id=o.get("id", "a"),
                            text=o.get("text", ""),
                            is_correct=o.get("is_correct", False),
                            explanation=o.get("explanation", ""),
                        )
                        for o in q_res.get("options", [])
                    ]
                    v_prompt = q_res.get("prompt", v_prompt)
            except Exception as e:
                logger.warning(f"Fallback verification challenge generation failed: {e}")

        v_challenge = VerificationChallengeSchema(
            item_id=f"lock_{concept.id}_{step_sequence}",
            prompt_markdown=v_prompt or (f"Проверьте понимание темы **{concept.title}**:" if is_russian else f"Verify your mastery of **{concept.title}**:"),
            options=opts,
            allow_voice=True,
        )

        # 6. Persist Step in DB
        db_step = DeepSessionStep(
            session_id=deep_session.id,
            concept_id=concept.id,
            step_sequence=step_sequence,
            step_type="explanation",
            explanation_markdown=explanation,
            visual_type=visual_artifact.type if visual_artifact else None,
            visual_payload=visual_artifact.payload if visual_artifact else None,
            visual_alt=visual_artifact.alt_text if visual_artifact else None,
            verification_challenge=v_challenge.model_dump(),
        )
        session.add(db_step)
        await session.commit()

        from app.services.ai.tts_service import tts_service
        asyncio.create_task(tts_service.prefetch_audio(explanation))

        from app.core.slug import generate_slug
        c_slug = concept.slug or generate_slug(concept.title)

        track_slug = None
        if concept.track_id:
            t_res = await session.execute(select(Track.slug).where(Track.id == concept.track_id))
            track_slug = t_res.scalars().first()

        return DeepStepPayload(
            session_id=deep_session.id,
            concept_id=concept.id,
            concept_title=concept.title,
            concept_slug=c_slug,
            track_id=concept.track_id,
            track_slug=track_slug,
            step_sequence=step_sequence,
            step_type="explanation",
            explanation_markdown=explanation,
            visual_artifact=visual_artifact,
            verification_challenge=v_challenge,
            is_session_completed=False,
        )

    async def evaluate_step_answer(
        self,
        session: AsyncSession,
        deep_session: DeepLearningSession,
        submission: DeepStepAnswerSubmission,
    ) -> DeepStepAnswerResult:
        """
        Evaluates step verification answer. If incorrect, triggers Remediation Branching.
        """
        step = None

        # 1. Primary lookup: by session_id and step_sequence
        step_res = await session.execute(
            select(DeepSessionStep).where(
                and_(
                    DeepSessionStep.session_id == deep_session.id,
                    DeepSessionStep.step_sequence == submission.step_sequence,
                )
            )
        )
        step = step_res.scalars().first()

        # 2. Secondary lookup: by concept_id if passed or session's current concept
        target_cid = getattr(submission, "concept_id", None) or deep_session.current_concept_id
        if not step and target_cid:
            step_res = await session.execute(
                select(DeepSessionStep).where(
                    and_(
                        DeepSessionStep.session_id == deep_session.id,
                        DeepSessionStep.concept_id == target_cid,
                    )
                ).order_by(DeepSessionStep.created_at.desc())
            )
            step = step_res.scalars().first()

        # 3. Tertiary lookup: from planned_dag node at index step_sequence - 1
        if not step and deep_session.planned_dag:
            nodes = deep_session.planned_dag.get("nodes", [])
            idx = submission.step_sequence - 1
            if 0 <= idx < len(nodes):
                dag_cid = nodes[idx].get("id")
                if dag_cid:
                    step_res = await session.execute(
                        select(DeepSessionStep).where(
                            and_(
                                DeepSessionStep.session_id == deep_session.id,
                                DeepSessionStep.concept_id == dag_cid,
                            )
                        ).order_by(DeepSessionStep.created_at.desc())
                    )
                    step = step_res.scalars().first()
                    if not target_cid:
                        target_cid = dag_cid

        # 4. Global cache fallback: step was generated in another session, clone for current session
        if not step and target_cid:
            global_step_res = await session.execute(
                select(DeepSessionStep).where(
                    DeepSessionStep.concept_id == target_cid
                ).order_by(DeepSessionStep.created_at.desc())
            )
            global_step = global_step_res.scalars().first()
            if global_step:
                logger.info(
                    f"Adopting cached global step for concept {target_cid} into session {deep_session.id} (sequence {submission.step_sequence})"
                )
                step = DeepSessionStep(
                    session_id=deep_session.id,
                    concept_id=target_cid,
                    step_sequence=submission.step_sequence,
                    step_type=global_step.step_type or "explanation",
                    explanation_markdown=global_step.explanation_markdown,
                    visual_artifact=global_step.visual_artifact,
                    verification_challenge=global_step.verification_challenge,
                )
                session.add(step)
                await session.flush()

        # 5. Last-resort fallback: any recent step in this session
        if not step:
            any_step_res = await session.execute(
                select(DeepSessionStep).where(
                    DeepSessionStep.session_id == deep_session.id
                ).order_by(DeepSessionStep.created_at.desc())
            )
            step = any_step_res.scalars().first()

        if not step:
            logger.error(
                f"Step not found: session={deep_session.id}, sequence={submission.step_sequence}, cid={target_cid}"
            )
            raise ValueError("Шаг урока не найден в сессии. Пожалуйста, обновите страницу курса.")

        challenge_data = step.verification_challenge or {}
        options = challenge_data.get("options", [])
        correct_opts = [o["id"] for o in options if o.get("is_correct")]
        explanation = next((o.get("explanation", "") for o in options if o.get("is_correct")), "Explanation")

        # If question has no correct_opts defined, accept submission as correct
        if not correct_opts:
            is_correct = True
            explanation = "Ответ принят."
        else:
            is_correct = set(submission.selected_option_ids) == set(correct_opts)

        step.verification_passed = is_correct
        step.user_response = submission.model_dump()

        # Update Bayesian Mastery for this concept
        concept_res = await session.execute(select(Concept).where(Concept.id == step.concept_id))
        concept = concept_res.scalars().first()

        mastery_res = await session.execute(
            select(UserMasteryState).where(
                and_(
                    UserMasteryState.user_id == deep_session.user_id,
                    UserMasteryState.concept_id == step.concept_id,
                )
            )
        )
        mastery = mastery_res.scalars().first()
        if not mastery:
            mastery = UserMasteryState(
                user_id=deep_session.user_id,
                concept_id=step.concept_id,
                mastery_prob=0.95 if is_correct else 0.2,
                uncertainty=0.10 if is_correct else 0.5,
            )
            session.add(mastery)
        else:
            if is_correct:
                # Passing the full atomic lesson and verification challenge establishes genuine mastery
                mastery.mastery_prob = 0.95
                mastery.uncertainty = 0.10
            else:
                post_m, post_u = bkt_engine.update_mastery(
                    prior_mastery=mastery.mastery_prob,
                    prior_uncertainty=mastery.uncertainty,
                    is_correct=False,
                )
                mastery.mastery_prob = post_m
                mastery.uncertainty = post_u

        remediation_required = not is_correct
        remediation_node = None

        if remediation_required and concept:
            # Dynamic Remediation Branching: create auxiliary sub-node
            remediation_node = DAGNodeSchema(
                id=f"rem_{concept.id}",
                code=f"REM_{concept.code}",
                title=f"Intuition Bridge: {concept.title}",
                status="remediation",
                mastery_prob=0.1,
            )

        await session.commit()

        return DeepStepAnswerResult(
            session_id=deep_session.id,
            step_sequence=submission.step_sequence,
            is_correct=is_correct,
            explanation=explanation,
            remediation_required=remediation_required,
            remediation_node_inserted=remediation_node,
            next_step_ready=is_correct,
        )

    async def stream_step(
        self,
        session: AsyncSession,
        deep_session: DeepLearningSession,
        concept: Concept,
        step_sequence: int,
        user_notes: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Live-streaming step generator using Server-Sent Events.
        Tokens stream in real time (first tokens in 1-2s), completely preventing HTTP timeouts.
        Captures final usage metrics into AICostTracker.
        """
        # 1. Immediate SQLite Cache Check
        existing_step = None
        existing_step_res = await session.execute(
            select(DeepSessionStep)
            .where(
                and_(
                    DeepSessionStep.session_id == deep_session.id,
                    DeepSessionStep.concept_id == concept.id,
                    DeepSessionStep.explanation_markdown.isnot(None),
                )
            )
            .order_by(DeepSessionStep.created_at.desc())
        )
        for s in existing_step_res.scalars().all():
            if s.explanation_markdown and len(s.explanation_markdown.strip()) > 50:
                existing_step = s
                break

        # 1b. Global Concept Cache Check across all sessions
        if not existing_step:
            global_step_res = await session.execute(
                select(DeepSessionStep)
                .where(
                    and_(
                        DeepSessionStep.concept_id == concept.id,
                        DeepSessionStep.explanation_markdown.isnot(None),
                    )
                )
                .order_by(DeepSessionStep.created_at.desc())
            )
            for s in global_step_res.scalars().all():
                if s.explanation_markdown and len(s.explanation_markdown.strip()) > 50:
                    cloned = DeepSessionStep(
                        session_id=deep_session.id,
                        concept_id=concept.id,
                        step_sequence=step_sequence,
                        step_type=s.step_type or "explanation",
                        explanation_markdown=s.explanation_markdown,
                        visual_type=s.visual_type,
                        visual_payload=s.visual_payload,
                        visual_alt=s.visual_alt,
                        verification_challenge=s.verification_challenge,
                        verification_passed=False,
                    )
                    session.add(cloned)
                    await session.commit()
                    await session.refresh(cloned)
                    existing_step = cloned
                    break

        if existing_step and existing_step.explanation_markdown and len(existing_step.explanation_markdown.strip()) > 50:
            payload = self._build_step_payload_from_db(existing_step, concept, deep_session, step_sequence)
            from app.services.ai.tts_service import tts_service
            asyncio.create_task(tts_service.prefetch_audio(payload.explanation_markdown))
            self.trigger_background_prefetch_pipeline(
                user_id=deep_session.user_id,
                session_id=deep_session.id,
                current_concept_id=concept.id,
                current_sequence=step_sequence,
            )
            yield {"type": "ready", "step": payload.model_dump()}
            return

        yield {"type": "status", "message": f"Синтез урока: {concept.title}..."}

        # 2. Gather progression context
        track_title = "Курс"
        track_wishes = None
        if concept and concept.track_id:
            try:
                t_res = await session.execute(select(Track).where(Track.id == concept.track_id))
                t_obj = t_res.scalars().first()
                if t_obj:
                    if t_obj.title:
                        track_title = t_obj.title
                    if t_obj.user_wishes:
                        track_wishes = t_obj.user_wishes
            except Exception:
                pass

        planned_nodes = (deep_session.planned_dag or {}).get("nodes", [])
        total_steps = len(planned_nodes) or 1
        prior_steps_overview = []
        for i, pn in enumerate(planned_nodes[:max(0, step_sequence - 1)]):
            prior_steps_overview.append(f"• Урок {i+1} [{pn.get('code', '')}]: {pn.get('title', '')}")
        prior_lessons_str = "\n".join(prior_steps_overview) if prior_steps_overview else "Это самый первый урок курса."

        upcoming_nodes = planned_nodes[step_sequence:step_sequence + 3]
        upcoming_str = ", ".join([f"[{un.get('code', '')}] {un.get('title', '')}" for un in upcoming_nodes]) if upcoming_nodes else "Завершающие разделы курса."

        student_notes_prompt = ""
        if user_notes and user_notes.strip():
            student_notes_prompt = (
                f"\nSTUDENT'S EXPLICIT REASONING / WISHES FOR THIS STEP:\n"
                f"\"{user_notes.strip()}\"\n"
                f"PEDAGOGICAL DIRECTIVE: Weave this student reflection into the explanation and examples where natural!\n"
            )

        wishes_context = f"Student Course Wishes: {track_wishes}\n" if track_wishes else ""

        anti_repetition_mandate = (
            f"PROGRESSIVE COURSE CONTEXT:\n"
            f"• Course: «{track_title}»\n"
            f"• Current Position: Lesson Step {step_sequence} of {total_steps}\n"
            f"• Already Mastered Lessons in this Course:\n{prior_lessons_str}\n"
            f"• Upcoming Lessons: {upcoming_str}\n\n"
            f"CRITICAL DIRECTIVES:\n"
            f"- Jump DIRECTLY and EXCLUSIVELY into the specific mechanics and insights of '{concept.title}' ({concept.code}).\n"
            f"- Never repeat basic background or field introductions already covered earlier.\n"
        )

        target_lang = getattr(deep_session, "language", None) or "ru"
        is_russian = (target_lang == "ru") or any('\u0400' <= char <= '\u04FF' for char in (concept.title or ""))
        if target_lang == "en":
            is_russian = False

        lang_mandate = (
            "CRITICAL LANGUAGE MANDATE: You MUST write the ENTIRE explanation, headings, equations, and questions in RUSSIAN (Русский язык)."
            if is_russian
            else "CRITICAL LANGUAGE MANDATE: You MUST write the ENTIRE explanation, headings, and questions in ENGLISH."
        )

        active_model = settings.DEEP_MODEL
        if deep_session and deep_session.user_id:
            try:
                user_res = await session.execute(
                    select(User.preferred_model).where(User.id == deep_session.user_id)
                )
                pref = user_res.scalars().first()
                if pref and pref.strip():
                    active_model = pref.strip()
            except Exception as e:
                logger.warning(f"Could not query User.preferred_model: {e}")

        system_prompt = (
            "You are an elite, world-class personal mentor and master educator.\n"
            "Generate an exhaustive, deeply intuitive, storytelling-driven atomic tutorial.\n"
            "Format the entire tutorial directly in clean, rich Markdown (headings, bold, lists, LaTeX $$ formulas, code blocks).\n\n"
            "At the very end of your response, after the entire tutorial text, output:\n"
            "---QUIZ_JSON---\n"
            "followed by a single JSON object testing comprehension:\n"
            "{\"prompt\": \"...\", \"options\": [{\"id\": \"a\", \"text\": \"...\", \"is_correct\": true, \"explanation\": \"...\"}, {\"id\": \"b\", \"text\": \"...\", \"is_correct\": false, \"explanation\": \"...\"}]}\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"{anti_repetition_mandate}\n"
                    f"CURRENT ATOMIC CONCEPT TO TEACH: {concept.title} ({concept.code})\n"
                    f"Concept Summary: {concept.summary}\n"
                    f"{wishes_context}"
                    f"{student_notes_prompt}"
                    f"{lang_mandate}\n\n"
                    "Generate the live tutorial in Markdown."
                ),
            },
        ]

        full_prose_parts: List[str] = []
        quiz_buffer_parts: List[str] = []
        in_quiz_section = False

        async for chunk in ai_clients.generate_chat_stream(
            messages=messages,
            model=active_model,
            temperature=0.25,
            task_type="step_stream",
        ):
            if "---QUIZ_JSON---" in chunk or "---QUIZ" in chunk:
                in_quiz_section = True
                split_parts = chunk.split("---QUIZ", 1)
                if split_parts[0]:
                    full_prose_parts.append(split_parts[0])
                    yield {"type": "token", "token": split_parts[0]}
                if len(split_parts) > 1:
                    quiz_buffer_parts.append(split_parts[1])
                continue

            if in_quiz_section:
                quiz_buffer_parts.append(chunk)
            else:
                full_prose_parts.append(chunk)
                yield {"type": "token", "token": chunk}

        explanation = "".join(full_prose_parts).strip()
        from app.services.ai.client import sanitize_markdown_text, extract_json_or_fallback
        explanation = sanitize_markdown_text(explanation)
        if not explanation:
            explanation = f"### {concept.title}\n\n{concept.summary}"

        # Parse Quiz
        quiz_raw = "".join(quiz_buffer_parts).strip()
        quiz_obj = extract_json_or_fallback(quiz_raw)
        opts = []
        if quiz_obj and isinstance(quiz_obj, dict):
            raw_opts = quiz_obj.get("options") or []
            for o in raw_opts:
                if isinstance(o, dict):
                    opts.append(
                        QuizOption(
                            id=str(o.get("id", "a")),
                            text=str(o.get("text", "")),
                            is_correct=bool(o.get("is_correct", False)),
                            explanation=str(o.get("explanation", "")),
                        )
                    )

        if not opts or len(opts) < 2:
            prompt_text = f"Какое главное следствие вытекает из концепции «{concept.title}»?"
            opts = [
                QuizOption(id="a", text=f"Глубокое понимание фундаментальных принципов «{concept.title}»", is_correct=True, explanation="Верно"),
                QuizOption(id="b", text="Полное отсутствие практической применимости", is_correct=False, explanation="Неверно"),
            ]
        else:
            prompt_text = quiz_obj.get("prompt") or f"Проверка понимания: {concept.title}"

        v_challenge = VerificationChallengeSchema(
            item_id=f"lock_{concept.id}_{step_sequence}",
            prompt_markdown=prompt_text,
            options=opts,
            allow_voice=True,
        )

        # Save to DB
        new_step = DeepSessionStep(
            session_id=deep_session.id,
            concept_id=concept.id,
            step_sequence=step_sequence,
            step_type="explanation",
            explanation_markdown=explanation,
            visual_type=None,
            visual_payload=None,
            visual_alt=None,
            verification_challenge=v_challenge.model_dump(),
            verification_passed=False,
        )
        session.add(new_step)
        await session.commit()
        await session.refresh(new_step)


        payload = self._build_step_payload_from_db(new_step, concept, deep_session, step_sequence)
        from app.services.ai.tts_service import tts_service
        asyncio.create_task(tts_service.prefetch_audio(payload.explanation_markdown))
        self.trigger_background_prefetch_pipeline(
            user_id=deep_session.user_id,
            session_id=deep_session.id,
            current_concept_id=concept.id,
            current_sequence=step_sequence,
        )
        yield {"type": "ready", "step": payload.model_dump()}


step_executor = StepExecutor()
