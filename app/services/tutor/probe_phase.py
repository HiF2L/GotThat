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

    TARGET_DIAGNOSTIC_DEPTH = 10

    DIAGNOSTIC_SUITE_PROMPT = (
        "You are an elite academic professor and technical examiner.\n"
        "Your task is to construct a rigorous, 10-question TECHNICAL DIAGNOSTIC QUIZ to accurately test a student's real depth of understanding in the specified subject.\n\n"
        "CRITICAL RULES:\n"
        "1. REAL TECHNICAL QUESTIONS ONLY: Every question must test concrete technical facts, code syntax, execution flow, internal mechanisms, or specific edge cases. "
        "FORBIDDEN: NEVER ask meta-survey questions like 'How confident are you in X?' or 'Evaluate your skill'.\n"
        "2. CONCRETE TECHNICAL OPTIONS: Each of the 4 options (a, b, c, d) must be a specific, plausible technical answer (e.g. real code snippets, framework terms, exact mechanism behaviors), with exactly 1 correct answer and 3 realistic distractors.\n"
        "3. DOMAIN PURITY: Strictly test only technologies and concepts belonging to the requested topic (e.g. if topic is 'FastAPI в Python', questions must be strictly about Python/FastAPI/Pydantic/ASGI/Starlette/Uvicorn/SQLAlchemy/AsyncIO, never mentioning .NET, Java, PHP, etc.).\n"
        "4. PROGRESSIVE DIFFICULTY:\n"
        "   - Q1-Q2: Fundamental architectural concepts and core primitives.\n"
        "   - Q3-Q5: Syntax, type annotations, Dependency Injection, request lifecycle.\n"
        "   - Q6-Q8: Concurrency (async/def vs def), database integration, middleware, security.\n"
        "   - Q9-Q10: Advanced edge cases, performance tuning, and architectural design.\n"
        "5. CRITICAL LANGUAGE MANDATE: All questions, subtopics, options, and explanations MUST strictly be in the SAME LANGUAGE as the subject topic (Russian if Russian, English if English).\n\n"
        "Return valid JSON matching this exact structure:\n"
        "{\n"
        '  "questions": [\n'
        '    {\n'
        '      "id": "q1",\n'
        '      "subtopic_title": "Архитектура ASGI и сервера",\n'
        '      "prompt": "Какой спецификацией интерфейса руководствуется FastAPI для обеспечения асинхронной обработки HTTP-запросов и WebSocket?",\n'
        '      "options": [\n'
        '        {"id": "a", "text": "WSGI (Web Server Gateway Interface)", "is_correct": false, "explanation": "WSGI синхронный."},\n'
        '        {"id": "b", "text": "ASGI (Asynchronous Server Gateway Interface)", "is_correct": true, "explanation": "FastAPI построен поверх Starlette и реализует спецификацию ASGI."},\n'
        '        {"id": "c", "text": "CGI (Common Gateway Interface)", "is_correct": false, "explanation": "Устаревший протокол."},\n'
        '        {"id": "d", "text": "FastCGI", "is_correct": false, "explanation": "Не используется как нативный интерфейс FastAPI."}\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    async def initialize_suite_if_needed(
        self,
        session: AsyncSession,
        deep_session: DeepLearningSession,
    ) -> List[Dict[str, Any]]:
        """
        Generates the complete technical diagnostic suite in ONE batch call if not yet present in session state.
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
                    "Generate 10 concrete, technical, domain-specific multiple-choice diagnostic questions."
                ),
            },
        ]

        suite_data = await ai_clients.generate_json(
            messages=messages,
            model=settings.FAST_MODEL,
            temperature=0.25,
        )

        raw_questions = (
            suite_data.get("questions")
            or suite_data.get("diagnostic_questions")
            or suite_data.get("items")
            or []
        )

        # Format options with standard 'I don't know / not sure yet' fallback
        formatted_suite = []
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
