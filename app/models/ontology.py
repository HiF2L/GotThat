import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Text, Float, Boolean, DateTime, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from app.core.database import Base


class DependencyType(str, enum.Enum):
    STRICT_PREREQUISITE = "strict_prerequisite"
    SOFT_PREREQUISITE = "soft_prerequisite"
    ANALOGY = "analogy"
    PART_OF = "part_of"


class AssessmentType(str, enum.Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    ERROR_SPOTTING = "error_spotting"
    FREE_REASONING = "free_reasoning"


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tracks: Mapped[List["Track"]] = relationship("Track", back_populates="domain", cascade="all, delete-orphan")


class TrackFolder(Base):
    __tablename__ = "track_folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(32), default="#6366f1")
    icon: Mapped[Optional[str]] = mapped_column(String(64), default="folder")
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tracks: Mapped[List["Track"]] = relationship("Track", back_populates="folder")


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    domain_id: Mapped[str] = mapped_column(String(36), ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)
    folder_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("track_folders.id", ondelete="SET NULL"), nullable=True, index=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_wishes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    depth_level: Mapped[str] = mapped_column(String(32), default="high")
    icon_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    domain: Mapped["Domain"] = relationship("Domain", back_populates="tracks")
    folder: Mapped[Optional["TrackFolder"]] = relationship("TrackFolder", back_populates="tracks")
    concepts: Mapped[List["Concept"]] = relationship("Concept", back_populates="track", cascade="all, delete-orphan")


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    bloom_level: Mapped[str] = mapped_column(String(32), default="understand")
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    track: Mapped["Track"] = relationship("Track", back_populates="concepts")
    dependencies_as_target: Mapped[List["ConceptDependency"]] = relationship(
        "ConceptDependency",
        foreign_keys="[ConceptDependency.target_concept_id]",
        back_populates="target_concept",
        cascade="all, delete-orphan",
    )
    dependencies_as_source: Mapped[List["ConceptDependency"]] = relationship(
        "ConceptDependency",
        foreign_keys="[ConceptDependency.source_concept_id]",
        back_populates="source_concept",
        cascade="all, delete-orphan",
    )
    assessment_items: Mapped[List["AssessmentItem"]] = relationship(
        "AssessmentItem", back_populates="concept", cascade="all, delete-orphan"
    )
    misconceptions: Mapped[List["Misconception"]] = relationship(
        "Misconception", back_populates="concept", cascade="all, delete-orphan"
    )


class ConceptDependency(Base):
    __tablename__ = "concept_dependencies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    target_concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[DependencyType] = mapped_column(
        SQLEnum(DependencyType), default=DependencyType.STRICT_PREREQUISITE
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    source_concept: Mapped["Concept"] = relationship("Concept", foreign_keys=[source_concept_id], back_populates="dependencies_as_source")
    target_concept: Mapped["Concept"] = relationship("Concept", foreign_keys=[target_concept_id], back_populates="dependencies_as_target")


class Misconception(Base):
    __tablename__ = "misconceptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    concept_id: Mapped[str] = mapped_column(String(36), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    correction_hint: Mapped[str] = mapped_column(Text, nullable=False)

    concept: Mapped["Concept"] = relationship("Concept", back_populates="misconceptions")


class AssessmentItem(Base):
    __tablename__ = "assessment_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    concept_id: Mapped[str] = mapped_column(String(36), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False)
    item_type: Mapped[AssessmentType] = mapped_column(SQLEnum(AssessmentType), default=AssessmentType.SINGLE_CHOICE)
    prompt_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict] = mapped_column(JSON, default=list)
    rubric_guidelines: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    difficulty: Mapped[float] = mapped_column(Float, default=0.5)
    discrimination_index: Mapped[float] = mapped_column(Float, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    concept: Mapped["Concept"] = relationship("Concept", back_populates="assessment_items")
