"""SessionGrid — Celery Task Definitions (Full Analysis Pipeline)"""

import logging
import hashlib
import time
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
    Full analysis pipeline task.
    
    Steps:
    1. Extract audio (FFmpeg)
    2. Separate stems (Demucs)
    3. Analyze beats (librosa + madmom)
    4. Detect sections
    5. Score confidence
    6. Generate click track
    7. Generate waveform peaks
    8. Persist all results
    """
    start_time = time.time()
    logger.info(f"Starting analysis pipeline for project: {project_id}")
    
    db = _get_db()
    
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        
        original_path = project.original_file_path
        project_dir = Path(settings.storage_root) / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # ─── Step 1: Extract Audio ──────────────────────────────────────
        _update_status(project_id, ProjectStatus.EXTRACTING, "Extracting audio from file...")
        self.update_state(state="PROGRESS", meta={"step": "extracting", "progress": 10})
        
        from services.audio_extract import extract_audio
        
        audio_output = str(project_dir / "audio.wav")
        extract_result = extract_audio(original_path, audio_output)
        
        project.audio_file_path = extract_result["output_path"]
        project.duration_seconds = extract_result["duration_seconds"]
        project.file_hash_sha256 = extract_result["file_hash_sha256"]
        db.commit()
        
        # ─── Step 2: Separate Stems ─────────────────────────────────────
        _update_status(project_id, ProjectStatus.SEPARATING, "Separating instrument stems...")
        self.update_state(state="PROGRESS", meta={"step": "separating", "progress": 30})
        
        from services.stem_separate import separate_stems
        
        stems_dir = str(project_dir / "stems")
        stem_result = separate_stems(audio_output, stems_dir)
        
        # Save stem files to DB
        for stem_name, stem_path in stem_result["stem_paths"].items():
            try:
                stem_type = StemType(stem_name)
            except ValueError:
                stem_type = StemType.OTHER
            
            stem_file = StemFile(
                project_id=project.id,
                stem_type=stem_type,
                file_path=stem_path,
                quality_score=stem_result["quality_scores"].get(stem_name),
            )
            db.add(stem_file)
        db.commit()
        
        # ─── Step 3: Beat Analysis ──────────────────────────────────────
        _update_status(project_id, ProjectStatus.ANALYZING, "Analyzing beats and tempo...")
        self.update_state(state="PROGRESS", meta={"step": "analyzing_beats", "progress": 55})
        
        from services.beat_analysis import analyze_beats
        
        # Analyze the drums stem for better beat detection
        drums_path = stem_result["stem_paths"].get("drums", audio_output)
        beat_result = analyze_beats(drums_path)
        
        # ─── Step 4: Section Detection ──────────────────────────────────
        self.update_state(state="PROGRESS", meta={"step": "detecting_sections", "progress": 70})
        
        from services.section_detect import detect_sections
        
        sections_result = detect_sections(
            audio_output,
            beat_result["beat_times"],
            beat_result["downbeat_times"],
            beat_result["overall_bpm"],
        )
        
        # Save sections to DB
        for sec_data in sections_result:
            section = Section(
                project_id=project.id,
                order_index=sec_data["order_index"],
                name=sec_data["name"],
                start_time=sec_data["start_time"],
                end_time=sec_data["end_time"],
                bars=sec_data.get("bars"),
                bpm=sec_data.get("bpm"),
                meter=sec_data.get("meter"),
                confidence=CONFIDENCE_MAP.get(sec_data.get("confidence", "low"), ConfidenceLevel.LOW),
            )
            db.add(section)
        db.commit()
        
        # ─── Step 5: Confidence Scoring ─────────────────────────────────
        self.update_state(state="PROGRESS", meta={"step": "scoring_confidence", "progress": 80})
        
        from services.confidence import score_all_confidence
        
        confidence_result = score_all_confidence(
            beat_result,
            sections_result,
            stem_result["quality_scores"],
        )
        
        # ─── Step 6: Click Track ────────────────────────────────────────
        _update_status(project_id, ProjectStatus.GENERATING_CLICK, "Generating click track...")
        self.update_state(state="PROGRESS", meta={"step": "generating_click", "progress": 88})
        
        from services.click_generate import generate_click_track
        
        click_path = str(project_dir / "click.wav")
        click_result = generate_click_track(
            beat_result["beat_times"],
            beat_result["downbeat_times"],
            beat_result["duration_seconds"],
            click_path,
            mode="quarter",
        )
        
        click_track = ClickTrack(
            project_id=project.id,
            file_path=click_result["file_path"],
            mode=click_result["mode"],
        )
        db.add(click_track)
        db.commit()
        
        # ─── Step 7: Waveform Peaks ────────────────────────────────────
        self.update_state(state="PROGRESS", meta={"step": "generating_waveform", "progress": 93})
        
        from services.waveform import generate_waveform_peaks
        
        waveform_path = str(project_dir / "waveform.json")
        generate_waveform_peaks(audio_output, waveform_path)
        
        # Also generate waveform for drums stem
        if "drums" in stem_result["stem_paths"]:
            drums_waveform_path = str(project_dir / "waveform_drums.json")
            generate_waveform_peaks(stem_result["stem_paths"]["drums"], drums_waveform_path)
        
        # ─── Step 8: Persist Analysis Result ────────────────────────────
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        # Compute output hash for determinism validation
        output_hash = _compute_output_hash(beat_result, sections_result)
        
        analysis = AnalysisResult(
            project_id=project.id,
            pipeline_version=settings.pipeline_version,
            model_versions={
                "demucs": stem_result["model_name"],
                "librosa": "0.10.2",
                "madmom": "0.17.dev0",
            },
            random_seeds={"torch": settings.random_seed, "numpy": settings.random_seed},
            config_snapshot={
                "sample_rate": settings.sample_rate,
                "demucs_model": settings.demucs_model,
            },
            overall_bpm=beat_result["overall_bpm"],
            bpm_stable=beat_result["bpm_stable"],
            time_signature=sections_result[0]["meter"] if sections_result else "4/4",
            confidence_stem=CONFIDENCE_MAP.get(confidence_result["confidence_stem"]),
            confidence_beat=CONFIDENCE_MAP.get(confidence_result["confidence_beat"]),
            confidence_downbeat=CONFIDENCE_MAP.get(confidence_result["confidence_downbeat"]),
            confidence_meter=CONFIDENCE_MAP.get(confidence_result["confidence_meter"]),
            confidence_sections=CONFIDENCE_MAP.get(confidence_result["confidence_sections"]),
            beats_json=beat_result["beat_times"],
            downbeats_json=beat_result["downbeat_times"],
            tempo_curve_json=beat_result["tempo_curve"],
            output_hash_sha256=output_hash,
            analysis_duration_ms=elapsed_ms,
        )
        db.add(analysis)
        
        project.status = ProjectStatus.COMPLETE
        project.status_message = f"Analysis complete in {elapsed_ms / 1000:.1f}s"
        project.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        logger.info(f"Pipeline complete for {project_id} in {elapsed_ms}ms")
        
        return {
            "project_id": str(project_id),
            "status": "complete",
            "duration_ms": elapsed_ms,
            "bpm": beat_result["overall_bpm"],
            "sections": len(sections_result),
            "output_hash": output_hash,
        }
    
    except Exception as e:
        logger.exception(f"Pipeline failed for {project_id}: {e}")
        _update_status(project_id, ProjectStatus.FAILED, str(e)[:500])
        raise
    
    finally:
        db.close()


def _compute_output_hash(beat_result: dict, sections_result: list[dict]) -> str:
    """Compute a determinism hash over all analysis outputs."""
    hasher = hashlib.sha256()
    
    # Hash beat data
    hasher.update(json.dumps(beat_result["beat_times"], sort_keys=True).encode())
    hasher.update(json.dumps(beat_result["downbeat_times"], sort_keys=True).encode())
    hasher.update(str(beat_result["overall_bpm"]).encode())
    
    # Hash section data
    for sec in sections_result:
        hasher.update(json.dumps(sec, sort_keys=True).encode())
    
    return hasher.hexdigest()
