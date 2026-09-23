import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Text, Float, Boolean, Integer, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(16), default="ru")
    preferred_model: Mapped[str] = mapped_column(String(64), default="kimi-k3")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    enrollments: Mapped[List["UserTrackEnrollment"]] = relationship(
        "UserTrackEnrollment", back_populates="user", cascade="all, delete-orphan"
    )
    mastery_states: Mapped[List["UserMasteryState"]] = relationship(
        "UserMasteryState", back_populates="user", cascade="all, delete-orphan"
    )
    attempts: Mapped[List["AssessmentAttempt"]] = relationship(
        "AssessmentAttempt", back_populates="user", cascade="all, delete-orphan"
    )


class UserTrackEnrollment(Base):
    __tablename__ = "user_track_enrollments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    is_active_in_feed: Mapped[bool] = mapped_column(Boolean, default=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="enrollments")


class UserMasteryState(Base):
    __tablename__ = "user_mastery_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    concept_id: Mapped[str] = mapped_column(String(36), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False)

    # Bayesian Knowledge Tracing (BKT)
    mastery_prob: Mapped[float] = mapped_column(Float, default=0.0) # P(Mastery) 0.0 -> 1.0
    uncertainty: Mapped[float] = mapped_column(Float, default=1.0)  # Epistemic uncertainty: 1.0 (unknown) -> 0.0 (certain)

    # FSRS (Free Spaced Repetition Scheduler) parameters
    stability: Mapped[float] = mapped_column(Float, default=0.0)    # Memory stability in days
    difficulty: Mapped[float] = mapped_column(Float, default=5.0)   # Scale 1-10
    retrievability: Mapped[float] = mapped_column(Float, default=0.0) # Probability of recall right now
    last_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_review_due: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    # Aggregates & Detected Misconceptions
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)
    successful_reviews: Mapped[int] = mapped_column(Integer, default=0)
    active_misconceptions: Mapped[list] = mapped_column(JSON, default=list)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="mastery_states")


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    assessment_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assessment_items.id", ondelete="CASCADE"), nullable=False
    )
    source_context: Mapped[str] = mapped_column(String(32), default="quick_feed") # quick_feed, deep_session, probe

    selected_option_ids: Mapped[list] = mapped_column(JSON, default=list)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(Integer, default=0)

    prior_mastery: Mapped[float] = mapped_column(Float, default=0.0)
    posterior_mastery: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="attempts")
    voice_log: Mapped[Optional["VoiceReasoningLog"]] = relationship(
        "VoiceReasoningLog", back_populates="attempt", uselist=False, cascade="all, delete-orphan"
    )


class VoiceReasoningLog(Base):
    __tablename__ = "voice_reasoning_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    audio_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stt_transcript: Mapped[str] = mapped_column(Text, nullable=False)
    llm_analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    attempt: Mapped["AssessmentAttempt"] = relationship("AssessmentAttempt", back_populates="voice_log")


class ConceptReaction(Base):
    __tablename__ = "concept_reactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_id: Mapped[str] = mapped_column(String(36), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True)
    vote_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'upvote' | 'downvote'
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "concept_id", name="uq_user_concept_reaction"),
    )
