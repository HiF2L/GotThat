import re
import unicodedata
from typing import Optional, Dict, Any
from app.services.moderation.base import BaseModerationProvider
from app.services.moderation.schemas import ModerationVerdict, SafetyCategory

ZERO_WIDTH_CHARS = re.compile(r"[\u200B-\u200D\uFEFF\u200E\u200F\u00AD]")

# Critical immediate-block regex patterns (high precision zero-tolerance categories)
CRITICAL_PATTERNS = [
    (
        re.compile(r"(?:child\s+porn|csam|детск(?:ое|ую|ой)\s+порн)", re.IGNORECASE),
        SafetyCategory.SEXUAL_AND_CSAM,
        "Материалы с сексуальной эксплуатацией категорически запрещены законодательством и этическими нормами.",
    ),
    (
        re.compile(r"(?:как\s+совершить\s+суицид|способы\s+самоубийств|how\s+to\s+commit\s+suicide)", re.IGNORECASE),
        SafetyCategory.SELF_HARM_AND_SUICIDE,
        "Платформа заботится о вашей безопасности и не поддерживает контент, связанный с причинением вреда себе или суицидом.",
    ),
    (
        re.compile(r"(?:изготовлен(?:ие|ить)\s+(?:гексоген|взрывчатк|бомб[уы]|зарин|иприт)|how\s+to\s+(?:make|build)\s+a\s+bomb)", re.IGNORECASE),
        SafetyCategory.ILLEGAL_ACTS_AND_WEAPONS,
        "Создание взрывчатых веществ, оружия или опасных химических соединений строго запрещено.",
    ),
]


def normalize_text(text: str) -> str:
    """
    Cleans text from hidden formatting, zero-width spaces, and normalizes unicode forms.
    """
    if not text:
        return ""
    # Remove zero-width characters
    cleaned = ZERO_WIDTH_CHARS.sub("", text)
    # Unicode NFKC normalization
    cleaned = unicodedata.normalize("NFKC", cleaned)
    # Collapse excess whitespace
    return re.sub(r"\s+", " ", cleaned).strip()


class FastHeuristicGuard(BaseModerationProvider):
    """
    Tier-1 Fast Deterministic Guard:
    Executes in <0.05ms to sanitize text and catch zero-tolerance severe violations.
    """

    async def evaluate(self, text: str, context: Optional[Dict[str, Any]] = None) -> ModerationVerdict:
        clean_text = normalize_text(text)
        if not clean_text:
            return ModerationVerdict(
                is_safe=False,
                category=SafetyCategory.IMMORAL_AND_UNETHICAL,
                risk_score=1.0,
                reason="Empty or whitespace-only input",
                user_message="Пожалуйста, укажите содержательную тему курса.",
            )

        if len(clean_text) > 4000:
            return ModerationVerdict(
                is_safe=False,
                category=SafetyCategory.JAILBREAK_AND_PROMPT_INJECTION,
                risk_score=1.0,
                reason="Input text length exceeds safety limit",
                user_message="Запрос слишком длинный. Пожалуйста, сократите описание темы.",
            )

        for pattern, category, user_msg in CRITICAL_PATTERNS:
            if pattern.search(clean_text):
                return ModerationVerdict(
                    is_safe=False,
                    category=category,
                    risk_score=1.0,
                    reason=f"Matched critical safety rule: {category.value}",
                    user_message=user_msg,
                )

        return ModerationVerdict(is_safe=True, risk_score=0.0)
