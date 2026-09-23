from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SafetyCategory(str, Enum):
    ILLEGAL_ACTS_AND_WEAPONS = "illegal_acts_and_weapons"
    CYBER_ATTACKS_AND_FRAUD = "cyber_attacks_and_fraud"
    HATE_SPEECH_AND_EXTREMISM = "hate_speech_and_extremism"
    SELF_HARM_AND_SUICIDE = "self_harm_and_suicide"
    SEXUAL_AND_CSAM = "sexual_and_csam"
    HARASSMENT_AND_DOXXING = "harassment_and_doxxing"
    POLITICS_AND_PROPAGANDA = "politics_and_propaganda"
    MILITARY_AND_WARFARE = "military_and_warfare"
    IMMORAL_AND_UNETHICAL = "immoral_and_unethical"
    JAILBREAK_AND_PROMPT_INJECTION = "jailbreak_and_prompt_injection"


class ModerationVerdict(BaseModel):
    is_safe: bool = Field(default=True, description="True if content passes all safety and academic policies")
    category: Optional[SafetyCategory] = Field(default=None, description="Identified violation category if unsafe")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk confidence score between 0.0 and 1.0")
    reason: Optional[str] = Field(default=None, description="Internal technical rationale for the decision")
    user_message: Optional[str] = Field(
        default=None,
        description="Polite, educational explanation for the student explaining why this query cannot be processed"
    )
    defensive_focus: Optional[str] = Field(
        default=None,
        description="For dual-use educational topics (e.g. infosec), directive to reframe purely around defense & ethics"
    )
