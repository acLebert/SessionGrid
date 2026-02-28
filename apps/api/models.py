"""SessionGrid API — Database Models"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, Enum, ForeignKey, Text, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, DeclarativeBase
import enum


class Base(DeclarativeBase):
    pass


# ─── Enums ───────────────────────────────────────────────────────────────────

class ProjectStatus(str, enum.Enum):
    UPLOADING = "uploading"
    EXTRACTING = "extracting"
    SEPARATING = "separating"
    ANALYZING = "analyzing"
    GENERATING_CLICK = "generating_click"
    COMPLETE = "complete"
    FAILED = "failed"


class ConfidenceLevel(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class StemType(str, enum.Enum):
    DRUMS = "drums"
    BASS = "bass"
    VOCALS = "vocals"
    OTHER = "other"


# ─── Models ──────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    status = Column(Enum(ProjectStatus), default=ProjectStatus.UPLOADING, nullable=False)
    status_message = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # File info
    original_filename = Column(String(500), nullable=False)
    original_file_path = Column(String(1000), nullable=True)
    audio_file_path = Column(String(1000), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    file_hash_sha256 = Column(String(64), nullable=True)

    # Relationships
    analysis = relationship("AnalysisResult", back_populates="project", uselist=False, cascade="all, delete-orphan")
    stems = relationship("StemFile", back_populates="project", cascade="all, delete-orphan")
    sections = relationship("Section", back_populates="project", order_by="Section.order_index", cascade="all, delete-orphan")
    click_track = relationship("ClickTrack", back_populates="project", uselist=False, cascade="all, delete-orphan")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Pipeline tracking (determinism)
    pipeline_version = Column(String(20), nullable=False)
    model_versions = Column(JSON, nullable=True)
    random_seeds = Column(JSON, nullable=True)
    config_snapshot = Column(JSON, nullable=True)

    # Global analysis
    overall_bpm = Column(Float, nullable=True)
    bpm_stable = Column(Boolean, default=True)
    time_signature = Column(String(10), nullable=True)

    # Confidence scores
    confidence_stem = Column(Enum(ConfidenceLevel), nullable=True)
    confidence_beat = Column(Enum(ConfidenceLevel), nullable=True)
    confidence_downbeat = Column(Enum(ConfidenceLevel), nullable=True)
    confidence_meter = Column(Enum(ConfidenceLevel), nullable=True)
    confidence_sections = Column(Enum(ConfidenceLevel), nullable=True)

    # Raw analysis data
    beats_json = Column(JSON, nullable=True)       # Array of beat timestamps in seconds
    downbeats_json = Column(JSON, nullable=True)    # Array of downbeat timestamps in seconds
    tempo_curve_json = Column(JSON, nullable=True)  # Array of {time, bpm} for tempo changes

    # Validation
    output_hash_sha256 = Column(String(64), nullable=True)
    analysis_duration_ms = Column(Integer, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="analysis")


class StemFile(Base):
    __tablename__ = "stem_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    stem_type = Column(Enum(StemType), nullable=False)
    file_path = Column(String(1000), nullable=False)
    quality_score = Column(Float, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="stems")


class Section(Base):
    __tablename__ = "sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    order_index = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False)
    start_time = Column(Float, nullable=False)   # seconds
    end_time = Column(Float, nullable=False)      # seconds
    bars = Column(Integer, nullable=True)
    bpm = Column(Float, nullable=True)
    meter = Column(String(20), nullable=True)
    confidence = Column(Enum(ConfidenceLevel), default=ConfidenceLevel.MEDIUM)
    notes = Column(Text, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="sections")


class ClickTrack(Base):
    __tablename__ = "click_tracks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    file_path = Column(String(1000), nullable=False)
    mode = Column(String(50), default="quarter")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    project = relationship("Project", back_populates="click_track")
