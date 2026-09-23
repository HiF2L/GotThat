import logging
import uuid
from typing import Dict, Any, List, Optional
from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.ontology import Concept, ConceptDependency, Track, DependencyType
from app.models.session import DeepLearningSession
from app.models.mastery import UserMasteryState, User
from app.services.graph.knowledge_graph import knowledge_graph_service
from app.services.ai.fact_checker import fact_checker
from app.services.ai.client import ai_clients
from app.schemas.tutor import PlannedDAGSchema
from app.config import settings

logger = logging.getLogger(__name__)


class PlanPhaseManager:
    """
    Implements Phase 2 (PLAN):
    - Synthesizes a completely new, comprehensive, custom-tailored Zero-to-Mastery Course DAG (18-35+ steps)
      specifically constructed based on the learner's diagnostic profile and identified gaps.
    - Bridges the exact knowledge frontier, acknowledging mastered foundations and detailing every subsequent quantum.
    - Safely replaces stub ontology with tailored concepts without breaking active session foreign keys.
    """

    TAILORED_CURRICULUM_PROMPT = (
        "You are an elite academic curriculum architect, pedagogue, and mentor.\n"
        "Construct a complete, comprehensive, personalized Zero-to-Mastery Course DAG in valid JSON.\n\n"
        "CORE PEDAGOGICAL & ARCHITECTURAL PRINCIPLES:\n"
        "1. PARETO 20/80 & TOP-DOWN SEQUENCING (СНАЧАЛА ОБЩАЯ КАРТИНА):\n"
        "   - The curriculum MUST begin with the big-picture mental model and end-to-end holistic view (the 20% core that unlocks 80% of intuition).\n"
        "   - Never plunge the student into isolated obscure minutiae or micro-details in the early lessons.\n"
        "   - Stage 1: The Bird's-Eye View (How all parts of the system interact end-to-end).\n"
        "   - Stage 2: Core Practical Daily Toolkit & Standard Patterns (80% of real-world use).\n"
        "   - Stage 3: Granular Subsystems, Internals, Optimization, Concurrency & Edge Cases.\n"
        "2. UNLIMITED DEPTH & GRANULARITY: Deconstruct the subject into as many granular, atomic concept nodes as needed for complete mastery. Every distinct micro-skill, core principle, and practical edge-case should have its own dedicated atomic node.\n"
        "3. STRICT CONCEPT DISTINCTNESS & ZERO REDUNDANCY (NO SYNONYMOUS LESSONS):\n"
        "   - Every concept node in the DAG MUST be strictly unique, mutually exclusive, and address a completely distinct mechanism, angle, or practical application.\n"
        "   - NEVER generate duplicate or near-duplicate lessons covering the same thesis under slightly different titles (e.g., 'Критерий фальсифицируемости', 'Фальсификация: механизм', 'Суть фальсификационизма').\n"
        "   - Each subsequent lesson must genuinely move the frontier forward into new territory (e.g., contrasting theories, historical precursors, demarcation dilemmas, degree of corroboration, evolutionary epistemology, methodological criticisms, sociological extensions).\n"
        "4. INTELLECTUALLY ENGAGING TITLES: Formulate concept titles and pedagogical previews with clarity and narrative purpose.\n"
        "5. DIAGNOSTIC GAPS & MISCONCEPTIONS: Integrate solutions to student doubts identified during diagnostics.\n"
        "6. Provide for each concept: code (e.g. 'M1.01'), title, summary (concise pedagogical preview), and bloom_level.\n"
        "7. Define all prerequisite dependency pairs [source_code, target_code]. Must form a valid acyclic DAG.\n"
        "8. CRITICAL LANGUAGE MANDATE: All titles and summaries MUST strictly be in the SAME LANGUAGE as the subject (Russian if Russian, English if English).\n"
        "9. CONSTITUTIONAL SAFETY & ETHICS MANDATE:\n"
        "   - STRICTLY FORBIDDEN: Any concepts promoting weapons, explosives, illegal drug synthesis, malware creation, unauthorized cyberattacks, fraud, contemporary partisan politics, real-world military warfare/combat tactics, self-harm, or immoral/unethical behavior.\n"
        "   - For dual-use domains (e.g. cybersecurity, pharmacology, law), frame all concepts strictly around DEFENSIVE mechanisms, hardening, ethical auditing, and foundational scientific principles.\n\n"
        "Return valid JSON matching this exact structure:\n"
        "{\n"
        '  "concepts": [\n'
        '    {"code": "NODE.01", "title": "Concept Title", "summary": "Preview", "bloom_level": "understand", "is_already_mastered": true},\n'
        '    {"code": "NODE.02", "title": "Concept Title 2", "summary": "Preview", "bloom_level": "apply", "is_already_mastered": false}\n'
        '  ],\n'
        '  "dependencies": [\n'
        '    ["NODE.01", "NODE.02"]\n'
        '  ]\n'
        "}"
    )

    async def generate_and_verify_plan(
        self,
        session: AsyncSession,
        user_id: str,
        target_concept_id: str,
        user_context_notes: str = "",
        probing_transcript: Optional[Dict[str, Any]] = None,
        language: str = "ru",
        depth_level: str = "high",
    ) -> PlannedDAGSchema:
        # Fetch target concept & track context
        concept_res = await session.execute(select(Concept).where(Concept.id == target_concept_id))
        target_concept = concept_res.scalars().first()
        topic_title = target_concept.title if target_concept else "Subject Mastery"
        track_id = target_concept.track_id if target_concept else None

        is_russian = (language == "ru") or any('\u0400' <= char <= '\u04FF' for char in (topic_title or ""))
        if language == "en":
            is_russian = False

        lang_mandate = (
            "LANGUAGE MANDATE: You MUST write ALL concept titles and concept summaries in RUSSIAN (Русский язык). "
            "Even if the subject is an English technical library/framework, all titles and summaries MUST be written in natural, fluent Russian."
            if is_russian
            else "LANGUAGE MANDATE: You MUST write ALL concept titles and summaries in ENGLISH."
        )

        if depth_level == "low":
            depth_instruction = (
                "CURRICULUM IMMERSION LEVEL: LOW / CONCISE OVERVIEW (STRICTLY 5 TO 7 ATOMIC CONCEPTS).\n"
                "STRICT QUANTITY MANDATE: The user explicitly selected LOW level (± 6 lessons). Generate exactly 5 to 7 concepts covering the universal top-down 20/80 mental model and fundamental pillars for a fast, high-level understanding."
            )
        elif depth_level == "medium":
            depth_instruction = (
                "CURRICULUM IMMERSION LEVEL: MEDIUM / PRACTICAL MASTERY (STRICTLY 15 TO 25 ATOMIC CONCEPTS).\n"
                "STRICT QUANTITY MANDATE: The user explicitly selected MEDIUM level (15-25 lessons). DO NOT generate 40+ concepts. Generate between 15 and 25 concepts in total.\n"
                "Follow universal Pareto 20/80 Top-Down sequencing across 4 to 5 progressive tiers (3 to 5 concepts each):\n"
                "  • Module 1: The Big Picture, Holistic Architecture & Master Mental Model (3-4 concepts)\n"
                "  • Module 2: Core Primitives, Laws & Fundamental Building Blocks (4-5 concepts)\n"
                "  • Module 3: Key Mechanisms, Workflows & Dynamic Interactions (4-5 concepts)\n"
                "  • Module 4: Real-world Applications, Synthesis & Best Practices (4-5 concepts)\n\n"
                "TOTAL NODES COUNT MUST BE STRICTLY BETWEEN 15 AND 25 CONCEPTS."
            )
        else: # "high" / "expert"
            depth_instruction = (
                "CURRICULUM IMMERSION LEVEL: HIGH / MAXIMUM ZERO-TO-EXPERT DEEP MASTERY (AT LEAST 40 TO 65+ DISCRETE ATOMIC CONCEPTS).\n"
                "STRICT QUANTITY MANDATE: The user explicitly selected EXPERT level and expects an exhaustive, micro-granular breakdown. DO NOT stop at 10, 15, or 20 concepts.\n"
                "Follow universal PARETO 20/80 TOP-DOWN SEQUENCING across 7 to 9 comprehensive progressive tiers tailored to the subject (5-8 atomic concepts each):\n"
                "  • Module 1: Панорамный обзор и целостная карта дисциплины (The Bird's-Eye View: как устроена вся система от первого лица, ключевая ментальная модель, 20% сути для 80% понимания) (5-7 concepts)\n"
                "  • Module 2: Фундаментальные первокирпичики, базовые законы/формулы, структуры и примитивы (5-7 concepts)\n"
                "  • Module 3: Ключевые механизмы действия, типовые динамические процессы и жизненный цикл (5-7 concepts)\n"
                "  • Module 4: Продвинутые механизмы, подсистемы, составные процессы и глубинное устройство (5-7 concepts)\n"
                "  • Module 5: Поведение в критических режимах, оптимизация, динамика под нагрузкой и масштабирование (5-7 concepts)\n"
                "  • Module 6: Граничные условия (edge cases), скрытые парадоксы, сбои, антипаттерны и их нейтрализация (5-7 concepts)\n"
                "  • Module 7: Прикладной синтез, реальная эксплуатация, безопасность, экосистема и инструментарий (5-7 concepts)\n"
                "  • Module 8: Экспертная диагностика, решение сложнейших нестандартных кейсов и передний край науки/инженерии (5-7 concepts)\n\n"
                "Every single concept node must be an individual atomic step targeting one clear pedagogical quantum that can be verified."
            )

        # 1. Ask Kimi K3 to synthesize a comprehensive, custom-tailored Course DAG
        try:
            transcript_summary = str(probing_transcript or "Diagnostic assessment completed.")
            messages = [
                {"role": "system", "content": self.TAILORED_CURRICULUM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Subject: {topic_title}\n"
                        f"Target Language: {'Russian (Русский язык)' if is_russian else 'English'}\n"
                        f"{lang_mandate}\n"
                        f"{depth_instruction}\n"
                        f"Diagnostic Transcript & Student Gaps: {transcript_summary}\n"
                        f"Student Voice Notes: {user_context_notes or 'None'}\n\n"
                        "Synthesize the full comprehensive personalized Zero-to-Mastery Course DAG."
                    ),
                },
            ]

            # Resolve plan model
            active_plan_model = getattr(settings, "PLAN_MODEL", settings.DEEP_MODEL)
            if user_id:
                try:
                    u_res = await session.execute(select(User.preferred_model).where(User.id == user_id))
                    u_pref = u_res.scalars().first()
                    if u_pref and u_pref.strip():
                        active_plan_model = u_pref.strip()
                except Exception as e:
                    logger.warning(f"Could not query User.preferred_model in plan_phase: {e}")

            plan_data = await ai_clients.generate_json(
                messages=messages,
                model=active_plan_model,
                temperature=0.25,
                max_tokens=14000,
                timeout_seconds=55.0,
            )

            raw_concepts = plan_data.get("concepts", [])
            raw_deps = plan_data.get("dependencies", [])

            if raw_concepts and track_id:
                # 1. First, create and persist all new tailored concepts
                from app.core.slug import generate_slug
                code_to_concept: Dict[str, Concept] = {}
                new_concepts: List[Concept] = []
                used_c_slugs = set()
                for idx, c_data in enumerate(raw_concepts):
                    c_code = c_data.get("code", f"STEP.{idx+1}")
                    c_title = c_data.get("title", f"Step {idx+1}")
                    base_c_slug = generate_slug(c_title)
                    c_slug = base_c_slug
                    cnt = 2
                    while c_slug in used_c_slugs:
                        c_slug = f"{base_c_slug}-{cnt}"
                        cnt += 1
                    used_c_slugs.add(c_slug)

                    new_concept = Concept(
                        id=str(uuid.uuid4()),
                        track_id=track_id,
                        slug=c_slug,
                        code=c_code,
                        title=c_title,
                        summary=c_data.get("summary", ""),
                        bloom_level=c_data.get("bloom_level", "understand"),
                    )
                    session.add(new_concept)
                    new_concepts.append(new_concept)
                    code_to_concept[c_code] = new_concept

                    # Record mastery state for already known foundations
                    if c_data.get("is_already_mastered"):
                        mastery = UserMasteryState(
                            user_id=user_id,
                            concept_id=new_concept.id,
                            mastery_prob=0.95,
                            uncertainty=0.1,
                        )
                        session.add(mastery)

                await session.flush()

                # 2. Safe Foreign Key Reassignment: Reassign target_concept_id in all active sessions
                new_terminal_concept = new_concepts[-1]
                target_concept_id = new_terminal_concept.id

                old_concepts_res = await session.execute(
                    select(Concept).where(
                        and_(
                            Concept.track_id == track_id,
                            Concept.id.not_in([c.id for c in new_concepts]),
                        )
                    )
                )
                old_concepts = old_concepts_res.scalars().all()
                old_ids = [c.id for c in old_concepts]

                if old_ids:
                    # Safely redirect any sessions to the new terminal concept before deleting old concepts
                    sessions_to_update_res = await session.execute(
                        select(DeepLearningSession).where(
                            DeepLearningSession.target_concept_id.in_(old_ids)
                        )
                    )
                    for s in sessions_to_update_res.scalars().all():
                        s.target_concept_id = new_terminal_concept.id
                    await session.flush()

                    # Now safely delete old dependencies and unused stub concepts
                    await session.execute(
                        delete(ConceptDependency).where(
                            or_(
                                ConceptDependency.source_concept_id.in_(old_ids),
                                ConceptDependency.target_concept_id.in_(old_ids),
                            )
                        )
                    )
                    await session.execute(
                        delete(Concept).where(Concept.id.in_(old_ids))
                    )

                # 3. Persist new dependencies
                for dep_pair in raw_deps:
                    if len(dep_pair) == 2:
                        src_c = code_to_concept.get(dep_pair[0])
                        tgt_c = code_to_concept.get(dep_pair[1])
                        if src_c and tgt_c:
                            dep = ConceptDependency(
                                source_concept_id=src_c.id,
                                target_concept_id=tgt_c.id,
                                relation_type=DependencyType.STRICT_PREREQUISITE,
                            )
                            session.add(dep)

                # Update track depth level
                track_res = await session.execute(select(Track).where(Track.id == track_id))
                track_obj = track_res.scalars().first()
                if track_obj:
                    track_obj.depth_level = depth_level or "high"

                await session.commit()
        except Exception as e:
            logger.error(f"Failed to synthesize tailored dynamic curriculum: {e}")

        # 2. Build graph from persisted knowledge base & student mastery states
        dag_plan = await knowledge_graph_service.plan_curriculum_dag(
            session=session,
            user_id=user_id,
            target_concept_id=target_concept_id,
        )

        return dag_plan

    EXPAND_CURRICULUM_PROMPT = (
        "You are an elite academic curriculum architect, pedagogue, and mentor.\n"
        "Your goal is to EXPAND and DEEPEN an existing course curriculum to a higher level of detail.\n\n"
        "CORE PEDAGOGICAL & ARCHITECTURAL PRINCIPLES:\n"
        "1. PRESERVE FOUNDATIONAL KNOWLEDGE & MASTERED CONCEPTS:\n"
        "   - The student has already studied and mastered specific concepts in this subject.\n"
        "   - You MUST retain these core concepts in the expanded curriculum and mark them with `is_already_mastered: true`.\n"
        "2. UNLIMITED DEPTH & GRANULARITY:\n"
        "   - Deconstruct the subject into granular, atomic concept nodes according to the requested target depth level.\n"
        "   - Expand the curriculum with intermediate bridges, advanced sub-mechanisms, practical edge cases, optimization techniques, and expert synthesis.\n"
        "3. PARETO 20/80 & TOP-DOWN PROGRESSION:\n"
        "   - Keep a clean, structured multi-module progression from big-picture to expert depths.\n"
        "4. Provide for each concept: code (e.g. 'M1.01'), title, summary (concise pedagogical preview), bloom_level, and is_already_mastered (boolean).\n"
        "5. Define all prerequisite dependency pairs [source_code, target_code]. Must form a valid acyclic DAG.\n"
        "6. CRITICAL LANGUAGE MANDATE: All titles and summaries MUST strictly match the target language.\n"
        "7. CONSTITUTIONAL SAFETY & ETHICS MANDATE:\n"
        "   - STRICTLY FORBIDDEN: Any concepts detailing weapons, explosive fabrication, illegal drug synthesis, offensive malware, phishing, scams, contemporary political agitation, military combat operations, self-harm, or immoral/unethical conduct.\n"
        "   - Reframe dual-use concepts solely around defense, security auditing, and constructive academic mastery.\n\n"
        "Return valid JSON matching this exact structure:\n"
        "{\n"
        '  "concepts": [\n'
        '    {"code": "NODE.01", "title": "Concept Title", "summary": "Preview", "bloom_level": "understand", "is_already_mastered": true},\n'
        '    {"code": "NODE.02", "title": "Concept Title 2", "summary": "Preview", "bloom_level": "apply", "is_already_mastered": false}\n'
        '  ],\n'
        '  "dependencies": [\n'
        '    ["NODE.01", "NODE.02"]\n'
        '  ]\n'
        "}"
    )

    async def expand_track_curriculum(
        self,
        session: AsyncSession,
        user_id: str,
        track_id: str,
        target_depth_level: str = "high",
        user_notes: str = "",
        language: Optional[str] = None,
    ) -> PlannedDAGSchema:
        """
        Dynamically expands an existing track's volume with 3 detail levels (low, medium, high),
        preserving already mastered student concepts and updating active sessions cleanly.
        """
        track_res = await session.execute(
            select(Track).where(or_(Track.id == track_id, Track.slug == track_id))
        )
        track = track_res.scalars().first()
        if not track:
            raise ValueError(f"Track '{track_id}' not found")

        real_track_id = track.id
        topic_title = track.title

        # Determine language
        if not language:
            user_res = await session.execute(select(User).where(User.id == user_id))
            user = user_res.scalars().first()
            language = user.preferred_language if user and user.preferred_language else "ru"

        is_russian = (language == "ru") or any('\u0400' <= char <= '\u04FF' for char in (topic_title or ""))
        if language == "en":
            is_russian = False

        lang_mandate = (
            "LANGUAGE MANDATE: You MUST write ALL concept titles and concept summaries in RUSSIAN (Русский язык). "
            "Even if the subject is an English technical library/framework, all titles and summaries MUST be written in natural, fluent Russian."
            if is_russian
            else "LANGUAGE MANDATE: You MUST write ALL concept titles and summaries in ENGLISH."
        )

        # Retrieve existing concepts & user mastery
        existing_c_res = await session.execute(
            select(Concept).where(Concept.track_id == real_track_id)
        )
        existing_concepts = list(existing_c_res.scalars().all())
        existing_ids = [c.id for c in existing_concepts]

        mastery_map = {}
        if existing_ids:
            mastery_res = await session.execute(
                select(UserMasteryState).where(
                    and_(
                        UserMasteryState.user_id == user_id,
                        UserMasteryState.concept_id.in_(existing_ids),
                    )
                )
            )
            mastery_map = {m.concept_id: m for m in mastery_res.scalars().all()}

        mastered_titles: List[str] = []
        all_existing_summary: List[str] = []
        for c in existing_concepts:
            m = mastery_map.get(c.id)
            is_m = (m.mastery_prob >= 0.85) or (m.mastery_prob >= 0.80 and getattr(m, 'uncertainty', 1.0) <= 0.40) if m else False
            if is_m:
                mastered_titles.append(c.title)
            all_existing_summary.append(f"- {c.title} ({'✔ Mastered' if is_m else 'Pending'})")

        if target_depth_level == "low":
            depth_instruction = (
                "CURRICULUM IMMERSION LEVEL: LOW / CONCISE OVERVIEW (STRICTLY 5 TO 7 ATOMIC CONCEPTS).\n"
                "STRICT QUANTITY MANDATE: The user selected LOW level (± 6 lessons). Generate exactly 5 to 7 concepts covering the universal top-down 20/80 mental model and fundamental pillars for a fast, high-level understanding."
            )
        elif target_depth_level == "medium":
            depth_instruction = (
                "CURRICULUM IMMERSION LEVEL: MEDIUM / PRACTICAL MASTERY (STRICTLY 15 TO 25 ATOMIC CONCEPTS).\n"
                "STRICT QUANTITY MANDATE: The user selected MEDIUM level (15-25 lessons). DO NOT generate 40+ concepts. Generate between 15 and 25 concepts in total.\n"
                "Follow universal Pareto 20/80 Top-Down sequencing across 4 to 5 progressive tiers (3 to 5 concepts each):\n"
                "  • Module 1: The Big Picture, Holistic Architecture & Master Mental Model (3-4 concepts)\n"
                "  • Module 2: Core Primitives, Laws & Fundamental Building Blocks (4-5 concepts)\n"
                "  • Module 3: Key Mechanisms, Workflows & Dynamic Interactions (4-5 concepts)\n"
                "  • Module 4: Real-world Applications, Synthesis & Best Practices (4-5 concepts)\n\n"
                "TOTAL NODES COUNT MUST BE STRICTLY BETWEEN 15 AND 25 CONCEPTS."
            )
        else: # "high" / "expert"
            depth_instruction = (
                "CURRICULUM IMMERSION LEVEL: HIGH / MAXIMUM ZERO-TO-EXPERT DEEP MASTERY (AT LEAST 40 TO 65+ DISCRETE ATOMIC CONCEPTS).\n"
                "STRICT QUANTITY MANDATE: The user selected EXPERT level and expects an exhaustive, micro-granular breakdown. DO NOT stop at 10, 15, or 20 concepts.\n"
                "Follow universal PARETO 20/80 TOP-DOWN SEQUENCING across 7 to 9 comprehensive progressive tiers tailored to the subject (5-8 atomic concepts each):\n"
                "  • Module 1: Панорамный обзор и целостная карта дисциплины (The Bird's-Eye View) (5-7 concepts)\n"
                "  • Module 2: Фундаментальные первокирпичики, базовые законы/формулы, структуры и примитивы (5-7 concepts)\n"
                "  • Module 3: Ключевые механизмы действия, типовые динамические процессы и жизненный цикл (5-7 concepts)\n"
                "  • Module 4: Продвинутые механизмы, подсистемы, составные процессы и глубинное устройство (5-7 concepts)\n"
                "  • Module 5: Поведение в критических режимах, оптимизация, динамика под нагрузкой и масштабирование (5-7 concepts)\n"
                "  • Module 6: Граничные условия (edge cases), скрытые парадоксы, сбои, антипаттерны и их нейтрализация (5-7 concepts)\n"
                "  • Module 7: Прикладной синтез, реальная эксплуатация, безопасность, экосистема и инструментарий (5-7 concepts)\n"
                "  • Module 8: Экспертная диагностика, решение сложнейших нестандартных кейсов и передний край науки/инженерии (5-7 concepts)\n\n"
                "Every single concept node must be an individual atomic step targeting one clear pedagogical quantum that can be verified."
            )

        try:
            mastered_context_str = ", ".join(mastered_titles) if mastered_titles else "None yet"
            existing_inventory_str = "\n".join(all_existing_summary) if all_existing_summary else "No prior lessons"
            messages = [
                {"role": "system", "content": self.EXPAND_CURRICULUM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Subject: {topic_title}\n"
                        f"Target Language: {'Russian (Русский язык)' if is_russian else 'English'}\n"
                        f"{lang_mandate}\n"
                        f"{depth_instruction}\n"
                        f"Already Mastered Topics by Student (must preserve and mark is_already_mastered: true): {mastered_context_str}\n"
                        f"Current Lesson Inventory:\n{existing_inventory_str}\n"
                        f"Student Context / Notes: {user_notes or 'None'}\n\n"
                        "Expand and synthesize the full comprehensive Course DAG with the requested detail level."
                    ),
                },
            ]

            plan_data = await ai_clients.generate_json(
                messages=messages,
                model=getattr(settings, "PLAN_MODEL", settings.DEEP_MODEL),
                temperature=0.25,
                max_tokens=14000,
            )

            raw_concepts = plan_data.get("concepts", [])
            raw_deps = plan_data.get("dependencies", [])

            if raw_concepts:
                from app.core.slug import generate_slug
                code_to_concept: Dict[str, Concept] = {}
                new_concepts: List[Concept] = []
                used_c_slugs = set()

                for idx, c_data in enumerate(raw_concepts):
                    c_code = c_data.get("code", f"STEP.{idx+1}")
                    c_title = c_data.get("title", f"Step {idx+1}")
                    base_c_slug = generate_slug(c_title)
                    c_slug = base_c_slug
                    cnt = 2
                    while c_slug in used_c_slugs:
                        c_slug = f"{base_c_slug}-{cnt}"
                        cnt += 1
                    used_c_slugs.add(c_slug)

                    new_concept = Concept(
                        id=str(uuid.uuid4()),
                        track_id=real_track_id,
                        slug=c_slug,
                        code=c_code,
                        title=c_title,
                        summary=c_data.get("summary", ""),
                        bloom_level=c_data.get("bloom_level", "understand"),
                    )
                    session.add(new_concept)
                    new_concepts.append(new_concept)
                    code_to_concept[c_code] = new_concept

                    # Check if marked mastered or matches previously mastered title
                    is_mastered = c_data.get("is_already_mastered") or any(
                        m_t.strip().lower() == c_title.strip().lower() or m_t.strip().lower() in c_title.strip().lower()
                        for m_t in mastered_titles
                    )
                    if is_mastered:
                        mastery = UserMasteryState(
                            user_id=user_id,
                            concept_id=new_concept.id,
                            mastery_prob=0.95,
                            uncertainty=0.1,
                        )
                        session.add(mastery)

                await session.flush()

                new_terminal_concept = new_concepts[-1]
                target_concept_id = new_terminal_concept.id

                # Reassign foreign keys for active sessions before deleting old concepts
                if existing_ids:
                    sessions_to_update_res = await session.execute(
                        select(DeepLearningSession).where(
                            DeepLearningSession.target_concept_id.in_(existing_ids)
                        )
                    )
                    for s in sessions_to_update_res.scalars().all():
                        s.target_concept_id = new_terminal_concept.id
                    await session.flush()

                    await session.execute(
                        delete(ConceptDependency).where(
                            or_(
                                ConceptDependency.source_concept_id.in_(existing_ids),
                                ConceptDependency.target_concept_id.in_(existing_ids),
                            )
                        )
                    )
                    await session.execute(
                        delete(Concept).where(Concept.id.in_(existing_ids))
                    )

                # Persist new dependencies
                for dep_pair in raw_deps:
                    if len(dep_pair) == 2:
                        src_c = code_to_concept.get(dep_pair[0])
                        tgt_c = code_to_concept.get(dep_pair[1])
                        if src_c and tgt_c:
                            dep = ConceptDependency(
                                source_concept_id=src_c.id,
                                target_concept_id=tgt_c.id,
                                relation_type=DependencyType.STRICT_PREREQUISITE,
                            )
                            session.add(dep)

                # Update track depth level
                track.depth_level = target_depth_level
                await session.flush()

                # Update any active user session DAGs
                from app.services.tutor.tutor_state_machine import tutor_state_machine
                new_concept_ids = [c.id for c in new_concepts]
                user_sessions_res = await session.execute(
                    select(DeepLearningSession).where(
                        and_(
                            DeepLearningSession.user_id == user_id,
                            or_(
                                DeepLearningSession.target_concept_id == new_terminal_concept.id,
                                DeepLearningSession.target_concept_id.in_(new_concept_ids),
                                DeepLearningSession.target_concept_id.in_(existing_ids) if existing_ids else False,
                            ),
                        )
                    )
                )
                for u_sess in user_sessions_res.scalars().all():
                    u_sess.target_concept_id = new_terminal_concept.id
                    u_sess.depth_level = target_depth_level
                    temp_dag = await knowledge_graph_service.plan_curriculum_dag(
                        session=session,
                        user_id=user_id,
                        target_concept_id=new_terminal_concept.id,
                    )
                    reconciled_dag, active_idx, active_cid, is_all_completed = await tutor_state_machine.reconcile_dag_with_mastery(
                        session=session,
                        user_id=user_id,
                        dag_data=temp_dag.model_dump(),
                        requested_concept_id=None,
                        current_index=None,
                    )
                    u_sess.planned_dag = reconciled_dag
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(u_sess, "planned_dag")
                    u_sess.mermaid_diagram = reconciled_dag.get("mermaid_code", "")
                    u_sess.current_concept_index = active_idx
                    u_sess.current_concept_id = active_cid
                    u_sess.status = "completed" if is_all_completed else "teaching"

                await session.commit()
        except Exception as e:
            logger.error(f"Failed to expand track curriculum: {e}", exc_info=True)

        target_concept_id = new_concepts[-1].id if 'new_concepts' in locals() and new_concepts else (existing_ids[-1] if existing_ids else track.id)
        dag_plan = await knowledge_graph_service.plan_curriculum_dag(
            session=session,
            user_id=user_id,
            target_concept_id=target_concept_id,
        )
        return dag_plan


plan_manager = PlanPhaseManager()
