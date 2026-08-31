import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class DeepLearningSession(Base):
    __tablename__ = "deep_learning_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )

    # State Machine Status: 'probing', 'planning', 'teaching', 'completed', 'abandoned'
    status: Mapped[str] = mapped_column(String(32), default="probing")
    language: Mapped[str] = mapped_column(String(16), default="ru")
    depth_level: Mapped[str] = mapped_column(String(32), default="high")

    # Planned DAG structure (Mermaid string + parsed JSON nodes/edges)
    planned_dag: Mapped[dict] = mapped_column(JSON, default=dict)
    mermaid_diagram: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    current_concept_index: Mapped[int] = mapped_column(Integer, default=0)
    current_concept_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Probing state during phase 1
    probing_state: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    steps: Mapped[List["DeepSessionStep"]] = relationship(
        "DeepSessionStep", back_populates="session", cascade="all, delete-orphan", order_by="DeepSessionStep.step_sequence"
    )


class DeepSessionStep(Base):
    __tablename__ = "deep_session_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deep_learning_sessions.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[str] = mapped_column(String(36), ForeignKey("concepts.id"), nullable=False)
    step_sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    step_type: Mapped[str] = mapped_column(String(32), default="explanation") # explanation, visual, remediation
    explanation_markdown: Mapped[str] = mapped_column(Text, nullable=False) # 1 atomic quantum of reasoning with LaTeX

    # Visual Artifact
    visual_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True) # svg, mermaid, none
    visual_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # raw SVG or diagram code
    visual_alt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Verification Quiz for locking this step
    verification_item_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    verification_challenge: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    verification_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    user_response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    qa_history: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["DeepLearningSession"] = relationship("DeepLearningSession", back_populates="steps")
