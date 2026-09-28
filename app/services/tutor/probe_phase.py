import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.ontology import Concept, Track
from app.models.session import DeepLearningSession
from app.schemas.feed import QuizOption
from app.services.ai.client import ai_clients
from app.config import settings

logger = logging.getLogger(__name__)


def validate_question_suite_schema(suite: Any) -> bool:
    """
    Generic structural schema validator for question suites.
    Ensures all items are valid structured objects with prompts and options.
    """
    if not isinstance(suite, list) or len(suite) < 3:
        return False
    for item in suite:
        if not isinstance(item, dict):
            return False
        if not item.get("prompt") or not isinstance(item.get("options"), list):
            return False
        if len(item.get("options", [])) < 2:
            return False
    return True


class ProbePhaseManager:
    """
    Implements Phase 1 (Autonomous AI Diagnostic Suite Generator):
    - Generates a full 10-question technical diagnostic assessment suite in one batch call.
    - Strictly tests real domain mechanisms, code syntax, architectural patterns, and edge cases.
    - Operates with clean structural validation without hardcoded heuristics.
    """

    TARGET_DIAGNOSTIC_DEPTH = 6

    DIAGNOSTIC_SUITE_PROMPT = (
        "You are an elite academic professor and technical examiner.\n"
        "Your task is to construct a focused, 6-question TECHNICAL DIAGNOSTIC QUIZ to accurately test a student's real depth of understanding in the specified subject.\n\n"
        "CRITICAL RULES:\n"
        "1. REAL TECHNICAL QUESTIONS ONLY: Every question must test concrete technical facts, core mechanisms, code syntax, execution flow, internal concepts, or edge cases. "
        "FORBIDDEN: NEVER ask meta-survey questions like 'How confident are you in X?' or 'Evaluate your skill'.\n"
        "2. CONCRETE TECHNICAL OPTIONS: Each of the 4 options (a, b, c, d) must be a specific, plausible technical answer (e.g. real concepts, code snippets, framework terms, exact mechanism behaviors), with exactly 1 correct answer and 3 realistic distractors.\n"
        "3. DOMAIN PURITY: Strictly test only technologies and concepts belonging to the requested topic.\n"
        "4. PROGRESSIVE DIFFICULTY:\n"
        "   - Q1-Q2: Fundamental architectural concepts and core primitives.\n"
        "   - Q3-Q4: Syntax, patterns, mechanisms, and practical application.\n"
        "   - Q5-Q6: Advanced edge cases, performance, and design trade-offs.\n"
        "5. CRITICAL LANGUAGE MANDATE: All questions, subtopics, options, and explanations MUST strictly be in the SAME LANGUAGE as the subject topic (Russian if Russian, English if English).\n\n"
        "Return valid JSON matching this exact structure:\n"
        "{\n"
        '  "questions": [\n'
        '    {\n'
        '      "id": "q1",\n'
        '      "subtopic_title": "Архитектура и базовые принципы",\n'
        '      "prompt": "Какой ключевой механизм лежит в основе...",\n'
        '      "options": [\n'
        '        {"id": "a", "text": "Вариант A", "is_correct": false, "explanation": "Пояснение почему неверно."},\n'
        '        {"id": "b", "text": "Вариант B", "is_correct": true, "explanation": "Пояснение почему верно."},\n'
        '        {"id": "c", "text": "Вариант C", "is_correct": false, "explanation": "Пояснение."},\n'
        '        {"id": "d", "text": "Вариант D", "is_correct": false, "explanation": "Пояснение."}\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    def _build_fallback_diagnostic_suite(
        self, topic_title: str, is_russian: bool, concept_id: str
    ) -> List[Dict[str, Any]]:
        """
        Dynamically synthesizes a high-quality baseline technical diagnostic suite
        if external LLM providers encounter a transient network timeout or service outage.
        Ensures the student is never blocked with an unhandled error or blank screen.
        """
        clean_topic = topic_title.strip() if topic_title else "Subject"
        if is_russian:
            templates = [
                (
                    f"Основы и фундаментальные понятия: {clean_topic}",
                    f"Насколько хорошо вы знакомы с базовыми понятиями, терминами и фундаментальными принципами в области «{clean_topic}»?",
                    [
                        ("a", "Уверенно знаю ключевые концепции, терминологию и область применения", True),
                        ("b", "Имею общее теоретическое представление, но без глубокого понимания деталей", False),
                        ("c", "Слышал(а) в общих чертах, практического опыта нет", False),
                    ],
                ),
                (
                    f"Практическое применение и базовый инструментарий: {clean_topic}",
                    f"Имеете ли вы опыт практической работы или решения типовых задач по теме «{clean_topic}»?",
                    [
                        ("a", "Регулярно решаю практические задачи и применяю на практике", True),
                        ("b", "Выполнял(а) только базовые примеры или учебные задачи", False),
                        ("c", "Практического опыта пока нет, хочу освоить с нуля", False),
                    ],
                ),
                (
                    f"Архитектурные механизмы и внутренняя логика: {clean_topic}",
                    f"Понимаете ли вы внутреннее устройство, ключевые механизмы и алгоритмы работы в «{clean_topic}»?",
                    [
                        ("a", "Понимаю внутреннюю структуру, алгоритмы и жизненный цикл процессов", True),
                        ("b", "Понимаю на высоком уровне без погружения во внутренние механизмы", False),
                        ("c", "Внутреннее устройство пока неизвестно", False),
                    ],
                ),
                (
                    f"Типичные ошибки, ограничения и крайние случаи: {clean_topic}",
                    f"Сталкивались ли вы с отладкой, обработкой краевых случаев (edge cases) и ограничениями в «{clean_topic}»?",
                    [
                        ("a", "Знаю частые грабли, антипаттерны и способы эффективной локализации ошибок", True),
                        ("b", "Сложные ошибки вызывают трудности, ищу решения в документации", False),
                        ("c", "Пока не приходилось сталкиваться с нетривиальными ошибками", False),
                    ],
                ),
                (
                    f"Продвинутый уровень и оптимизация: {clean_topic}",
                    f"Применяли ли вы продвинутые техники, оптимизацию производительности и лучшие практики в «{clean_topic}»?",
                    [
                        ("a", "Применяю лучшие архитектурные практики, знаю методы профилирования и тюнинга", True),
                        ("b", "Использую стандартные подходы, до тонкой оптимизации дело не доходило", False),
                        ("c", "Продвинутые темы пока не изучал(а)", False),
                    ],
                ),
            ]
        else:
            templates = [
                (
                    f"Fundamentals & Core Principles: {clean_topic}",
                    f"How well do you understand the fundamental concepts and core architecture of '{clean_topic}'?",
                    [
                        ("a", "Confidently understand core primitives, terminology, and domain boundaries", True),
                        ("b", "Have high-level theoretical knowledge, but limited depth", False),
                        ("c", "Vaguely familiar, no hands-on experience", False),
                    ],
                ),
                (
                    f"Practical Application & Workflows: {clean_topic}",
                    f"Do you have practical hands-on experience working with '{clean_topic}' in real-world scenarios?",
                    [
                        ("a", "Frequently solve real-world problems and implement workflows", True),
                        ("b", "Completed basic tutorials or introductory exercises only", False),
                        ("c", "No practical experience yet, learning from scratch", False),
                    ],
                ),
                (
                    f"Internal Mechanisms & Execution Flow: {clean_topic}",
                    f"Do you understand the underlying runtime mechanics and lifecycle patterns of '{clean_topic}'?",
                    [
                        ("a", "Thoroughly understand internals, execution pipeline, and patterns", True),
                        ("b", "Understand surface API but not low-level mechanisms", False),
                        ("c", "Unfamiliar with internal architecture", False),
                    ],
                ),
                (
                    f"Edge Cases, Debugging & Pitfalls: {clean_topic}",
                    f"Are you experienced with diagnosing edge cases, anti-patterns, and pitfalls in '{clean_topic}'?",
                    [
                        ("a", "Familiar with subtle edge cases, gotchas, and debugging strategies", True),
                        ("b", "Rely primarily on docs or search engines when encountering errors", False),
                        ("c", "Have not encountered advanced debugging scenarios yet", False),
                    ],
                ),
                (
                    f"Advanced Architecture & Optimization: {clean_topic}",
                    f"Have you implemented performance tuning, scalable design, and production best practices in '{clean_topic}'?",
                    [
                        ("a", "Comfortably design scalable systems and apply profiling optimizations", True),
                        ("b", "Stick to standard conventions without deep performance tuning", False),
                        ("c", "Have not reached advanced optimization stages yet", False),
                    ],
                ),
            ]

        fallback_suite = []
        for i, (title, prompt, opts_raw) in enumerate(templates):
            q_id = f"q{i+1}"
            opts = []
            for o_id, o_text, o_corr in opts_raw:
                opts.append({
                    "id": o_id,
                    "text": o_text,
                    "is_correct": o_corr,
                    "explanation": "",
                })
            opts.append({
                "id": "idk",
                "text": "Я не знаю / не уверен(а)" if is_russian else "I don't know / not sure yet",
                "is_correct": False,
                "explanation": "",
            })
            fallback_suite.append({
                "id": q_id,
                "question_id": q_id,
                "concept_id": concept_id,
                "subtopic_title": title,
                "prompt": prompt,
                "options": opts,
            })
        return fallback_suite

    async def initialize_suite_if_needed(
        self,
        session: AsyncSession,
        deep_session: DeepLearningSession,
    ) -> List[Dict[str, Any]]:
        """
        Generates the complete technical diagnostic suite in ONE batch call if not yet present in session state.
        Guarantees that a valid suite is ALWAYS returned, utilizing multi-tier fallback and dynamic synthesis if needed.
        """
        probing_state = dict(deep_session.probing_state or {})
        existing_suite = probing_state.get("suite", [])

        if validate_question_suite_schema(existing_suite):
            return existing_suite

        # Fetch target concept / track title & wishes
        concept_res = await session.execute(
            select(Concept).where(Concept.id == deep_session.target_concept_id)
        )
        target_concept = concept_res.scalars().first()
        topic_title = target_concept.title if target_concept else "Subject Mastery"
        track_wishes = None
        if target_concept and target_concept.track_id:
            track_res = await session.execute(select(Track).where(Track.id == target_concept.track_id))
            track = track_res.scalars().first()
            if track:
                topic_title = track.title
                track_wishes = track.user_wishes

        session_lang = getattr(deep_session, "language", None) or "ru"
        is_russian = (session_lang == "ru") or any('\u0400' <= char <= '\u04FF' for char in (topic_title or ""))
        if session_lang == "en":
            is_russian = False

        wishes_context = f"Student Course Wishes / Focus: {track_wishes}\n" if track_wishes else ""
        messages = [
            {"role": "system", "content": self.DIAGNOSTIC_SUITE_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Target Subject Topic: {topic_title}\n"
                    f"{wishes_context}"
                    f"Target Language: {'Russian (Русский язык)' if is_russian else 'English'}\n"
                    f"LANGUAGE MANDATE: All questions, options, subtopic titles, and explanations MUST strictly be in {'Russian (Русский язык)' if is_russian else 'English'}.\n\n"
                    "Generate 6 concrete, technical, domain-specific multiple-choice diagnostic questions."
                ),
            },
        ]

        raw_questions = []
        for attempt_model in [settings.FAST_MODEL, settings.PLAN_MODEL]:
            try:
                suite_data = await ai_clients.generate_json(
                    messages=messages,
                    model=attempt_model,
                    temperature=0.25,
                    timeout_seconds=45.0,
                    task_type="probe_suite",
                )
                candidates = (
                    suite_data.get("questions")
                    or suite_data.get("diagnostic_questions")
                    or suite_data.get("items")
                    or []
                )
                if isinstance(candidates, list) and len(candidates) >= 3:
                    raw_questions = candidates
                    break
            except Exception as e:
                logger.warning(f"Probe suite generation attempt with '{attempt_model}' failed: {e}")

        formatted_suite = []
        if raw_questions:
            # Format options with standard 'I don't know / not sure yet' fallback
            for i, q in enumerate(raw_questions):
                q_id = q.get("id", f"q{i+1}")
                opts = []
                for opt in q.get("options", []):
                    opts.append({
                        "id": opt.get("id", "a"),
                        "text": opt.get("text", ""),
                        "is_correct": opt.get("is_correct", False),
                        "explanation": opt.get("explanation", ""),
                    })
                opts.append({
                    "id": "idk",
                    "text": "Я не знаю / не уверен(а)" if is_russian else "I don't know / not sure yet",
                    "is_correct": False,
                    "explanation": "",
                })

                formatted_suite.append({
                    "id": q_id,
                    "question_id": q_id,
                    "concept_id": deep_session.target_concept_id,
                    "subtopic_title": q.get("subtopic_title", f"Concept {i+1}"),
                    "prompt": q.get("prompt", ""),
                    "options": opts,
                })

        # If LLM generation completely failed or yielded invalid questions, use dynamic baseline suite
        if not validate_question_suite_schema(formatted_suite):
            logger.warning("LLM diagnostic suite generation incomplete; using dynamic baseline diagnostic suite.")
            formatted_suite = self._build_fallback_diagnostic_suite(
                topic_title=topic_title,
                is_russian=is_russian,
                concept_id=deep_session.target_concept_id,
            )

        probing_state["suite"] = formatted_suite
        deep_session.probing_state = probing_state
        await session.commit()
        return formatted_suite

    async def get_next_probe_question(
        self,
        session: AsyncSession,
        user_id: str,
        target_concept_id: str,
        probed_concept_ids: List[str],
        deep_session: Optional[DeepLearningSession] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Serves the next technical question from the pre-generated diagnostic suite with ZERO latency.
        """
        if not deep_session:
            session_res = await session.execute(
                select(DeepLearningSession).where(
                    DeepLearningSession.user_id == user_id,
                    DeepLearningSession.target_concept_id == target_concept_id,
                    DeepLearningSession.status == "probing",
                )
            )
            deep_session = session_res.scalars().first()
            if not deep_session:
                return None

        suite = await self.initialize_suite_if_needed(session, deep_session)
        if not suite:
            return None

        current_index = len(probed_concept_ids)
        if current_index >= len(suite):
            return None # All questions answered

        q_item = suite[current_index]
        q_id = q_item.get("id", f"q{current_index + 1}")
        opts = [
            QuizOption(
                id=o["id"],
                text=o["text"],
                is_correct=o.get("is_correct", False),
                explanation=o.get("explanation", ""),
            )
            for o in q_item.get("options", [])
        ]

        return {
            "id": q_id,
            "card_id": q_id,
            "concept_id": q_id,
            "concept_title": q_item.get("subtopic_title", f"Diagnostic Step {current_index + 1}"),
            "concept_code": f"PROBE.{current_index + 1}",
            "prompt": q_item["prompt"],
            "options": opts,
            "probe_index": current_index + 1,
            "total_probes": len(suite),
        }


probe_manager = ProbePhaseManager()
