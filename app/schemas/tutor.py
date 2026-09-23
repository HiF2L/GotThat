from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.feed import QuizOption


class DAGNodeSchema(BaseModel):
    id: str
    code: str
    title: str
    slug: Optional[str] = None
    status: str = Field("pending", description="'completed', 'active', 'pending', 'remediation'")
    mastery_prob: float = 0.0


class DAGEdgeSchema(BaseModel):
    source: str
    target: str
    relation_type: str = "strict_prerequisite"


class PlannedDAGSchema(BaseModel):
    mermaid_code: str
    nodes: List[DAGNodeSchema]
    edges: List[DAGEdgeSchema]
    total_nodes: int
    completed_nodes: int


class VisualArtifactSchema(BaseModel):
    type: str = Field(..., description="'svg', 'mermaid', 'image', 'none'")
    payload: str
    alt_text: Optional[str] = None


class VerificationChallengeSchema(BaseModel):
    item_id: str
    prompt_markdown: str
    options: List[QuizOption]
    allow_voice: bool = True


class DeepStepPayload(BaseModel):
    session_id: str
    concept_id: str
    concept_title: str
    concept_slug: Optional[str] = None
    track_id: Optional[str] = None
    track_slug: Optional[str] = None
    step_sequence: int
    step_type: str = "explanation" # explanation, visual, remediation
    explanation_markdown: str # strictly 1 atomic reasoning step with LaTeX
    visual_artifact: Optional[VisualArtifactSchema] = None
    verification_challenge: Optional[VerificationChallengeSchema] = None
    is_session_completed: bool = False
    dag_state: Optional[PlannedDAGSchema] = None
    qa_history: Optional[List[Dict[str, Any]]] = None


class DeepStepAnswerSubmission(BaseModel):
    session_id: str
    step_sequence: int
    selected_option_ids: List[str]
    concept_id: Optional[str] = None
    yap_text_note: Optional[str] = None
    user_voice_transcript: Optional[str] = None


class DeepStepAnswerResult(BaseModel):
    session_id: str
    step_sequence: int
    is_correct: bool
    explanation: str
    remediation_required: bool
    remediation_node_inserted: Optional[DAGNodeSchema] = None
    updated_dag: Optional[PlannedDAGSchema] = None
    next_step_ready: bool


class StartDeepSessionRequest(BaseModel):
    user_id: str
    target_concept_id: str
    initial_user_context: Optional[str] = None # e.g. "I already know basic vector calculus"
    language: Optional[str] = "ru"
    depth_level: Optional[str] = None
    skip_probing: Optional[bool] = False

