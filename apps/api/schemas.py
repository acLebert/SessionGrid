"""SessionGrid API — Pydantic Schemas"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


# ─── Enums (mirror DB enums for serialization) ─────────────────────────────

class ProjectStatusSchema(str):
    pass


class ConfidenceLevelSchema(str):
    pass


# ─── Section ────────────────────────────────────────────────────────────────

class SectionOut(BaseModel):
    id: UUID
    order_index: int
    name: str
    start_time: float
    end_time: float
    bars: Optional[int] = None
    bpm: Optional[float] = None
    meter: Optional[str] = None
    confidence: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class SectionUpdate(BaseModel):
    name: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    bars: Optional[int] = None
    bpm: Optional[float] = None
    meter: Optional[str] = None
    notes: Optional[str] = None


# ─── Stem ───────────────────────────────────────────────────────────────────

class StemOut(BaseModel):
    id: UUID
    stem_type: str
    file_path: str
    quality_score: Optional[float] = None

    class Config:
        from_attributes = True


# ─── Analysis Result ────────────────────────────────────────────────────────

class AnalysisResultOut(BaseModel):
    id: UUID
    pipeline_version: str
    overall_bpm: Optional[float] = None
    bpm_stable: Optional[bool] = None
    time_signature: Optional[str] = None
    confidence_stem: Optional[str] = None
    confidence_beat: Optional[str] = None
    confidence_downbeat: Optional[str] = None
    confidence_meter: Optional[str] = None
    confidence_sections: Optional[str] = None
    beats_json: Optional[list] = None
    downbeats_json: Optional[list] = None
    onset_times_json: Optional[list] = None
    tempo_curve_json: Optional[list] = None
    analysis_duration_ms: Optional[int] = None

    # v2: Groove
    groove_profile_json: Optional[dict] = None
    swing_ratio: Optional[float] = None
    groove_type: Optional[str] = None

    # v2: Drum hits
    drum_hits_json: Optional[list] = None
    num_drum_hits: Optional[int] = None

    # v2: Confidence vector
    confidence_vector_json: Optional[dict] = None

    # v2: Tempo correction
    raw_bpm: Optional[float] = None
    octave_correction_factor: Optional[float] = None
    tempo_candidates_json: Optional[list] = None

    # v2: MIDI
    midi_file_path: Optional[str] = None

    # v2: Metrical inference (debug)
    metrical_inference_json: Optional[dict] = None

    class Config:
        from_attributes = True


# ─── Click Track ────────────────────────────────────────────────────────────

class ClickTrackOut(BaseModel):
    id: UUID
    file_path: str
    mode: str

    class Config:
        from_attributes = True


# ─── Project ───────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class ProjectOut(BaseModel):
    id: UUID
    name: str
    status: str
    status_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    original_filename: str
    duration_seconds: Optional[float] = None
    file_hash_sha256: Optional[str] = None

    # Nested
    analysis: Optional[AnalysisResultOut] = None
    stems: list[StemOut] = []
    sections: list[SectionOut] = []
    click_track: Optional[ClickTrackOut] = None

    class Config:
        from_attributes = True


class ProjectListOut(BaseModel):
    id: UUID
    name: str
    status: str
    created_at: datetime
    original_filename: str
    duration_seconds: Optional[float] = None

    class Config:
        from_attributes = True


class ProjectStatusOut(BaseModel):
    id: UUID
    status: str
    status_message: Optional[str] = None


# ─── Upload Confirmation ───────────────────────────────────────────────────

class UploadConfirmation(BaseModel):
    """Returned after a user confirms they have rights to the uploaded content."""
    rights_confirmed: bool = Field(..., description="User confirms they have rights to this audio")
