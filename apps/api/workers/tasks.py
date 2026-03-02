"""SessionGrid — Celery Task Definitions (v2 Engine Pipeline)"""

import logging
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

from workers.celery_app import celery_app
from config import get_settings
from database import SyncSessionLocal
from models import (
    Project, ProjectStatus, AnalysisResult, StemFile, StemType,
    Section, ConfidenceLevel, ClickTrack,
)

logger = logging.getLogger(__name__)
settings = get_settings()

CONFIDENCE_MAP = {
    "high": ConfidenceLevel.HIGH,
    "medium": ConfidenceLevel.MEDIUM,
    "low": ConfidenceLevel.LOW,
}


def _get_db():
    session = SyncSessionLocal()
    return session


def _update_status(project_id: str, status: ProjectStatus, message: str = None):
    """Update project status in DB."""
    db = _get_db()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            project.status = status
            project.status_message = message
            project.updated_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


@celery_app.task(bind=True, name="analyze_project")
def analyze_project(self, project_id: str):
    """
    Full v2 analysis pipeline task.

    Delegates all analysis to engine.pipeline.run_pipeline() and
    persists results to the database.

    Stages (handled by engine):
      1. separation  — Stereo extract + Demucs stem isolation
      2. signal      — Onset detection + sample-level refinement
      3. temporal    — Beat tracking, downbeats, tempo octave correction, sections
      4. groove      — Swing, microtiming, accent profiling
      5. hits        — Drum hit classification
      6. export      — MIDI, click track, waveform peaks
      + confidence   — Metric-vector scoring
      + versioning   — Manifest, artifact caching
    """
    logger.info(f"Starting v2 analysis pipeline for project: {project_id}")

    db = _get_db()

    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        original_path = project.original_file_path
        project_dir = Path(settings.storage_root) / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        # Progress callback: updates Celery state + DB status
        def on_progress(stage: str, pct: int, msg: str = ""):
            self.update_state(state="PROGRESS", meta={
                "step": stage, "progress": pct, "message": msg,
            })
            # Map stages to DB statuses
            stage_status_map = {
                "separation": ProjectStatus.SEPARATING,
                "signal": ProjectStatus.ANALYZING,
                "temporal": ProjectStatus.ANALYZING,
                "groove": ProjectStatus.ANALYZING,
                "hits": ProjectStatus.ANALYZING,
                "export": ProjectStatus.GENERATING_CLICK,
                "confidence": ProjectStatus.ANALYZING,
            }
            db_status = stage_status_map.get(stage, ProjectStatus.ANALYZING)
            _update_status(project_id, db_status, msg)

        # ─── Run the v2 engine pipeline ─────────────────────────────────
        from engine.pipeline import run_pipeline

        results = run_pipeline(
            input_file_path=original_path,
            project_dir=str(project_dir),
            on_progress=on_progress,
            force_rerun=False,
        )

        # ─── Persist results to database ────────────────────────────────

        # Update project metadata
        extract = results.get("extraction", {})
        project.audio_file_path = extract.get("mono_path")
        project.duration_seconds = extract.get("duration_seconds")
        project.file_hash_sha256 = extract.get("file_hash_sha256")
        db.commit()

        # Save stem files
        stems = results.get("stems", {})
        for stem_name, stem_path in stems.get("stem_paths", {}).items():
            try:
                stem_type = StemType(stem_name)
            except ValueError:
                stem_type = StemType.OTHER
            stem_file = StemFile(
                project_id=project.id,
                stem_type=stem_type,
                file_path=stem_path,
                quality_score=stems.get("quality_scores", {}).get(stem_name),
            )
            db.add(stem_file)
        db.commit()

        # Save sections
        temporal = results.get("temporal", {})
        sections_data = temporal.get("sections", [])
        for sec_data in sections_data:
            section = Section(
                project_id=project.id,
                order_index=sec_data["order_index"],
                name=sec_data["name"],
                start_time=sec_data["start_time"],
                end_time=sec_data["end_time"],
                bars=sec_data.get("bars"),
                bpm=sec_data.get("bpm"),
                meter=sec_data.get("meter"),
                confidence=CONFIDENCE_MAP.get(
                    sec_data.get("meter_confidence", "low"), ConfidenceLevel.LOW
                ),
            )
            db.add(section)
        db.commit()

        # Save click track
        click = results.get("click", {})
        if click:
            click_track = ClickTrack(
                project_id=project.id,
                file_path=click.get("file_path", ""),
                mode=click.get("mode", "quarter"),
            )
            db.add(click_track)
            db.commit()

        # Build analysis result
        confidence = results.get("confidence", {})
        groove = results.get("groove", {})
        octave = temporal.get("octave_correction", {})
        hits_data = results.get("hits", {})
        pipeline = results.get("pipeline", {})
        midi = results.get("midi", {})

        elapsed_ms = pipeline.get("elapsed_ms", 0)
        output_hash = _compute_output_hash(temporal, sections_data)

        analysis = AnalysisResult(
            project_id=project.id,
            pipeline_version=settings.pipeline_version,
            model_versions={
                "demucs": stems.get("model_name", settings.demucs_model),
                "librosa": "0.10.2",
                "madmom": "0.17.dev0",
                "engine": pipeline.get("engine_version", "2.0.0"),
            },
            random_seeds={"torch": settings.random_seed, "numpy": settings.random_seed},
            config_snapshot={
                "sample_rate": settings.sample_rate,
                "demucs_model": settings.demucs_model,
            },
            overall_bpm=temporal.get("corrected_bpm"),
            bpm_stable=temporal.get("bpm_stable"),
            time_signature=temporal.get("time_signature", "4/4"),

            # Legacy confidence columns (derived from vector for backward compat)
            confidence_stem=CONFIDENCE_MAP.get(
                _level_from_score(confidence.get("hit_classification_score", 0))
            ),
            confidence_beat=CONFIDENCE_MAP.get(
                _level_from_score(confidence.get("tempo_stability_score", 0))
            ),
            confidence_downbeat=CONFIDENCE_MAP.get(
                _level_from_score(confidence.get("downbeat_alignment_score", 0))
            ),
            confidence_meter=CONFIDENCE_MAP.get(
                _level_from_score(confidence.get("meter_consistency_score", 0))
            ),
            confidence_sections=CONFIDENCE_MAP.get(
                _level_from_score(confidence.get("section_contrast_score", 0))
            ),

            # Core data
            beats_json=temporal.get("beat_times"),
            downbeats_json=temporal.get("downbeat_times"),
            onset_times_json=temporal.get("onset_times"),
            tempo_curve_json=temporal.get("tempo_curve"),

            # v2: Groove
            groove_profile_json=groove,
            swing_ratio=groove.get("swing_ratio_mean"),
            groove_type=groove.get("groove_type"),

            # v2: Hits
            drum_hits_json=hits_data.get("drum_hits"),
            num_drum_hits=hits_data.get("num_hits"),

            # v2: Confidence vector
            confidence_vector_json=confidence,

            # v2: Tempo octave correction
            raw_bpm=temporal.get("raw_bpm"),
            octave_correction_factor=octave.get("correction_factor"),
            tempo_candidates_json=octave.get("candidates"),

            # v2: MIDI
            midi_file_path=midi.get("file_path") if midi else None,

            # v2: Metrical inference (debug)
            metrical_inference_json=results.get("metrical_inference"),

            # v2: Subdivision graph (debug)
            subdivision_graph_json=results.get("subdivision_graph"),

            output_hash_sha256=output_hash,
            analysis_duration_ms=elapsed_ms,
        )
        db.add(analysis)

        project.status = ProjectStatus.COMPLETE
        project.status_message = f"v2 analysis complete in {elapsed_ms / 1000:.1f}s"
        project.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"v2 pipeline complete for {project_id} in {elapsed_ms}ms")

        return {
            "project_id": str(project_id),
            "status": "complete",
            "engine_version": pipeline.get("engine_version"),
            "duration_ms": elapsed_ms,
            "bpm": temporal.get("corrected_bpm"),
            "raw_bpm": temporal.get("raw_bpm"),
            "groove_type": groove.get("groove_type"),
            "num_sections": len(sections_data),
            "num_hits": hits_data.get("num_hits"),
            "confidence": confidence.get("overall_confidence_score"),
            "output_hash": output_hash,
        }

    except Exception as e:
        logger.exception(f"Pipeline failed for {project_id}: {e}")
        _update_status(project_id, ProjectStatus.FAILED, str(e)[:500])
        raise

    finally:
        db.close()


def _level_from_score(score: float) -> str:
    """Convert continuous 0–1 score to high/medium/low for legacy columns."""
    if score >= 0.75:
        return "high"
    elif score >= 0.45:
        return "medium"
    else:
        return "low"


def _compute_output_hash(temporal: dict, sections: list[dict]) -> str:
    """Compute a determinism hash over all analysis outputs."""
    hasher = hashlib.sha256()

    hasher.update(json.dumps(temporal.get("beat_times", []), sort_keys=True).encode())
    hasher.update(json.dumps(temporal.get("downbeat_times", []), sort_keys=True).encode())
    hasher.update(str(temporal.get("corrected_bpm", 0)).encode())

    for sec in sections:
        hasher.update(json.dumps(sec, sort_keys=True).encode())

    return hasher.hexdigest()
