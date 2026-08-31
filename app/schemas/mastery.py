from typing import List, Optional
from pydantic import BaseModel


class ConceptMasterySummary(BaseModel):
    concept_id: str
    concept_code: str
    title: str
    slug: Optional[str] = None
    mastery_prob: float
    uncertainty: float
    retrievability: float
    stability: float
    is_mastered: bool
    is_due_for_review: bool


class UserMasteryOverview(BaseModel):
    user_id: str
    track_id: str
    track_slug: Optional[str] = None
    track_title: str
    track_description: Optional[str] = None
    track_user_wishes: Optional[str] = None
    track_depth_level: Optional[str] = "high"
    track_folder_id: Optional[str] = None
    track_is_pinned: Optional[bool] = False
    total_concepts: int
    mastered_concepts: int
    in_progress_concepts: int
    concepts: List[ConceptMasterySummary]
