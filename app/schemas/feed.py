from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class QuizOption(BaseModel):
    id: str
    text: str
    is_correct: Optional[bool] = None
    misconception_id: Optional[str] = None
    explanation: Optional[str] = None


class FeedCardResponse(BaseModel):
    card_id: str
    concept_id: str
    concept_title: str
    concept_code: str
    track_title: str
    item_type: str
    prompt_markdown: str
    options: List[QuizOption]
    card_mode: str = Field(..., description="'srs' for spaced repetition, 'probe' for frontier exploration")
    current_mastery: float
    current_uncertainty: float
    allow_voice_reasoning: bool = True


class QuizAnswerSubmission(BaseModel):
    user_id: str
    card_id: str
    concept_id: str
    selected_option_ids: List[str]
    response_time_ms: int = 0
    yap_text_note: Optional[str] = None # Optional user scratchpad note


class VoiceReasoningAnalysis(BaseModel):
    logical_coherence_score: float = Field(..., ge=0.0, le=1.0)
    demonstrated_understanding: List[str] = []
    misconceptions_detected: List[str] = []
    reasoning_summary: str
    speech_hesitation_detected: bool = False
    is_genuine_understanding: bool = True


class QuizAnswerResult(BaseModel):
    is_correct: bool
    correct_option_ids: List[str]
    explanation: str
    prior_mastery: float
    posterior_mastery: float
    prior_uncertainty: float
    posterior_uncertainty: float
    voice_analysis: Optional[VoiceReasoningAnalysis] = None


class DiscoveryLessonTeaser(BaseModel):
    concept_id: str
    concept_title: str
    concept_code: str
    track_id: str
    track_title: str
    track_slug: str
    teaser_text: str  # Intro / Hook of the lesson
    bloom_level: Optional[str] = "understand"
    is_mastered: bool = False
    total_track_concepts: int = 1
    mastery_prob: float = 0.0
    score: int = 0
    upvotes: int = 0
    downvotes: int = 0
    user_vote: Optional[str] = None  # "upvote", "downvote", or None
    comments_count: int = 0
    read_time_minutes: int = 3


class ConceptVoteRequest(BaseModel):
    user_id: str
    concept_id: str
    vote_type: str = Field(..., description="'upvote', 'downvote', or 'clear'")


class ConceptVoteResponse(BaseModel):
    concept_id: str
    user_vote: Optional[str] = None  # 'upvote', 'downvote', or None
    score: int
    upvotes: int
    downvotes: int


