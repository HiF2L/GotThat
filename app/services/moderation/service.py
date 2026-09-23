import hashlib
import logging
from collections import OrderedDict
from typing import Optional, Dict, Any, List
from fastapi import HTTPException

from app.services.moderation.base import BaseModerationProvider
from app.services.moderation.schemas import ModerationVerdict, SafetyCategory
from app.services.moderation.providers.fast_guard import FastHeuristicGuard, normalize_text
from app.services.moderation.providers.ai_guard import AISafetyClassifier

logger = logging.getLogger(__name__)


class ContentPolicyViolationException(HTTPException):
    """
    Structured HTTP exception thrown when user content violates platform safety policies.
    """
    def __init__(self, verdict: ModerationVerdict):
        user_msg = verdict.user_message or "Запрос нарушает правила безопасности платформы GotThat."
        cat_val = verdict.category.value if verdict.category else "content_policy_violation"
        super().__init__(
            status_code=400,
            detail={
                "error": "CONTENT_POLICY_VIOLATION",
                "category": cat_val,
                "message": user_msg,
                "reason": verdict.reason,
            },
        )


class ContentModerationService:
    """
    Orchestrates the multi-tier Content Safety and Moderation Pipeline:
    - Tier 0: In-Memory LRU Hash Cache (<0.01ms lookup)
    - Tier 1: Fast Heuristic & Structural Guard (<0.05ms)
    - Tier 2: Semantic AI Safety Classifier (Audits intent, politics, military, ethics)
    """

    def __init__(self, max_cache_size: int = 2048):
        self.fast_guard = FastHeuristicGuard()
        self.ai_classifier = AISafetyClassifier()
        self.providers: List[BaseModerationProvider] = [
            self.fast_guard,
            self.ai_classifier,
        ]
        self._cache: OrderedDict[str, ModerationVerdict] = OrderedDict()
        self._max_cache_size = max_cache_size

    def _get_cache_key(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        norm = normalize_text(text)
        ctx_serialized = ""
        if context:
            ctx_serialized = ":".join(f"{k}={v}" for k, v in sorted(context.items()) if v)
        payload = f"{norm}|{ctx_serialized}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    async def evaluate_text(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ModerationVerdict:
        """
        Executes moderation pipeline for arbitrary text with LRU caching.
        """
        if not text or not text.strip():
            return ModerationVerdict(is_safe=True)

        cache_key = self._get_cache_key(text, context)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        # 1. Tier 1: Fast Heuristic Guard
        fast_verdict = await self.fast_guard.evaluate(text, context)
        if not fast_verdict.is_safe:
            self._record_cache(cache_key, fast_verdict)
            return fast_verdict

        # 2. Tier 2: Semantic AI Safety Classifier
        ai_verdict = await self.ai_classifier.evaluate(text, context)
        self._record_cache(cache_key, ai_verdict)
        return ai_verdict

    async def check_course_request(
        self,
        topic_query: str,
        user_wishes: Optional[str] = None,
    ) -> ModerationVerdict:
        """
        Audits incoming course generation or expansion requests.
        Evaluates topic and wishes together.
        """
        # 1. Check topic query first
        topic_verdict = await self.evaluate_text(
            text=topic_query,
            context={"intent": "course_generation_topic"},
        )
        if not topic_verdict.is_safe:
            logger.warning(
                f"Course topic rejected by moderation: '{topic_query}' (Category: {topic_verdict.category}, Reason: {topic_verdict.reason})"
            )
            return topic_verdict

        # 2. If wishes provided, check user wishes against prompt injections & harmful instructions
        if user_wishes and user_wishes.strip():
            wishes_verdict = await self.evaluate_text(
                text=user_wishes,
                context={"intent": "user_pedagogical_wishes", "topic": topic_query},
            )
            if not wishes_verdict.is_safe:
                logger.warning(
                    f"Course user wishes rejected by moderation for topic '{topic_query}': '{user_wishes}'"
                )
                return wishes_verdict

        return topic_verdict

    async def validate_or_raise(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Helper that evaluates text and automatically raises ContentPolicyViolationException if unsafe.
        """
        verdict = await self.evaluate_text(text, context)
        if not verdict.is_safe:
            raise ContentPolicyViolationException(verdict)

    async def validate_course_request_or_raise(
        self,
        topic_query: str,
        user_wishes: Optional[str] = None,
    ):
        """
        Helper that validates topic & wishes and raises ContentPolicyViolationException if unsafe.
        """
        verdict = await self.check_course_request(topic_query, user_wishes)
        if not verdict.is_safe:
            raise ContentPolicyViolationException(verdict)

    def _record_cache(self, key: str, verdict: ModerationVerdict):
        if len(self._cache) >= self._max_cache_size:
            self._cache.popitem(last=False)
        self._cache[key] = verdict


moderation_service = ContentModerationService()
