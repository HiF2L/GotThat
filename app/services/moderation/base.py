from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from app.services.moderation.schemas import ModerationVerdict


class BaseModerationProvider(ABC):
    """
    Abstract interface for pluggable moderation providers.
    Supports local heuristic guards, LLM semantic guards, or external safety APIs.
    """

    @abstractmethod
    async def evaluate(self, text: str, context: Optional[Dict[str, Any]] = None) -> ModerationVerdict:
        """
        Evaluates input text against safety policies.
        Returns ModerationVerdict with is_safe flag, category, and localized user message.
        """
        pass
