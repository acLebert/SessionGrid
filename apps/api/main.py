"""SessionGrid API — FastAPI Application"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from config import get_settings
from database import get_db, async_engine
from models import Base, Project, ProjectStatus, AnalysisResult, Section, StemFile, ClickTrack
from schemas import (
    ProjectCreate, ProjectOut, ProjectListOut, ProjectStatusOut,
    UploadConfirmation, SectionUpdate,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("SessionGrid API started")
    yield
    logger.info("SessionGrid API shutting down")


# ─── App ───────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SessionGrid API",
    description="Turn demos into musician-ready arrangement maps",
    version=settings.pipeline_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.pipeline_version}


# ─── Projects ──────────────────────────────────────────────────────────────

@app.get("/api/projects", response_model=list[ProjectListOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List all projects."""
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc())
    )
    return result.scalars().all()


@app.post("/api/projects", response_model=ProjectOut)
async def create_project_and_upload(
    name: str = Form(...),
    rights_confirmed: bool = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a project and upload a file in one step.
    User must confirm they have rights to the content.
    """
    if not rights_confirmed:
        raise HTTPException(
            status_code=400,
            detail="You must confirm you have rights to upload this content."
        )
    
    # Validate file extension
    allowed_extensions = {".mp3", ".wav", ".flac", ".ogg", ".mp4", ".mov", ".webm", ".m4a", ".aac"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Validate file size
    max_bytes = settings.upload_max_size_mb * 1024 * 1024
    
    # Create project
    project = Project(
        name=name,
        original_filename=file.filename,
        status=ProjectStatus.UPLOADING,
    )
    db.add(project)
    await db.flush()  # Get the ID
    
    # Save uploaded file
    upload_dir = settings.upload_dir / str(project.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename
    
    total_size = 0
    with open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            total_size += len(chunk)
            if total_size > max_bytes:
                # Clean up
                file_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail=f"File too large. Max: {settings.upload_max_size_mb}MB")
            f.write(chunk)
    
    project.original_file_path = str(file_path)
    project.status = ProjectStatus.UPLOADING
    project.status_message = "File uploaded, ready for analysis"
    
    # Reload with relationships
    await db.commit()
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.analysis),
            selectinload(Project.stems),
            selectinload(Project.sections),
            selectinload(Project.click_track),
        )
        .filter(Project.id == project.id)
    )
    return result.scalar_one()


@app.post("/api/projects/{project_id}/analyze")
async def trigger_analysis(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Trigger the analysis pipeline for a project."""
    result = await db.execute(select(Project).filter(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.status not in (ProjectStatus.UPLOADING, ProjectStatus.FAILED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot analyze project in status: {project.status.value}"
        )
    
    # Import and dispatch Celery task
    from workers.tasks import analyze_project
    task = analyze_project.delay(str(project_id))
    
    project.status = ProjectStatus.EXTRACTING
    project.status_message = "Analysis queued..."
    
    return {"task_id": task.id, "project_id": str(project_id), "status": "queued"}


@app.get("/api/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get full project details with analysis results."""
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.analysis),
            selectinload(Project.stems),
            selectinload(Project.sections),
            selectinload(Project.click_track),
        )
        .filter(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return project


@app.get("/api/projects/{project_id}/status", response_model=ProjectStatusOut)
async def get_project_status(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Poll project processing status."""
    result = await db.execute(
        select(Project.id, Project.status, Project.status_message)
        .filter(Project.id == project_id)
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return {"id": row[0], "status": row[1].value, "status_message": row[2]}


# ─── File Streaming ───────────────────────────────────────────────────────

@app.get("/api/projects/{project_id}/stems/{stem_type}")
async def get_stem(project_id: UUID, stem_type: str, db: AsyncSession = Depends(get_db)):
    """Download a stem audio file."""
    result = await db.execute(
        select(StemFile)
        .filter(StemFile.project_id == project_id, StemFile.stem_type == stem_type)
    )
    stem = result.scalar_one_or_none()
    
    if not stem or not Path(stem.file_path).exists():
        raise HTTPException(status_code=404, detail=f"Stem not found: {stem_type}")
    
    return FileResponse(
        stem.file_path,
        media_type="audio/wav",
        filename=f"{stem_type}.wav",
    )


@app.get("/api/projects/{project_id}/click")
async def get_click_track(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Download the click track."""
    result = await db.execute(
        select(ClickTrack).filter(ClickTrack.project_id == project_id)
    )
    click = result.scalar_one_or_none()
    
    if not click or not Path(click.file_path).exists():
        raise HTTPException(status_code=404, detail="Click track not found")
    
    return FileResponse(
        click.file_path,
        media_type="audio/wav",
        filename="click.wav",
    )


@app.get("/api/projects/{project_id}/waveform")
async def get_waveform(project_id: UUID, stem: str = "mix"):
    """Get waveform peaks data for frontend rendering."""
    suffix = f"_{stem}" if stem != "mix" else ""
    waveform_path = Path(settings.storage_root) / str(project_id) / f"waveform{suffix}.json"
    
    if not waveform_path.exists():
        raise HTTPException(status_code=404, detail="Waveform data not found")
    
    return FileResponse(waveform_path, media_type="application/json")


# ─── v2: MIDI Export ──────────────────────────────────────────────────────

@app.get("/api/projects/{project_id}/midi")
async def get_midi(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Download the MIDI file."""
    result = await db.execute(
        select(AnalysisResult).filter(AnalysisResult.project_id == project_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis or not analysis.midi_file_path or not Path(analysis.midi_file_path).exists():
        raise HTTPException(status_code=404, detail="MIDI file not found")

    return FileResponse(
        analysis.midi_file_path,
        media_type="audio/midi",
        filename="drums.mid",
    )


@app.post("/api/projects/{project_id}/midi/quantize")
async def export_quantized_midi(
    project_id: UUID,
    quantization_strength: float = 0.5,
    db: AsyncSession = Depends(get_db),
):
    """Re-export MIDI with a specific quantization strength (0–1)."""
    result = await db.execute(
        select(AnalysisResult).filter(AnalysisResult.project_id == project_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis or not analysis.drum_hits_json:
        raise HTTPException(status_code=404, detail="Drum hits not found")

    from engine.stages.export import export_midi

    project_dir = Path(settings.storage_root) / str(project_id)
    q_pct = int(quantization_strength * 100)
    output_path = str(project_dir / f"drums_q{q_pct}.mid")

    midi_result = export_midi(
        hits=analysis.drum_hits_json,
        tempo_curve=analysis.tempo_curve_json or [],
        time_signature=analysis.time_signature or "4/4",
        sections=[],
        output_path=output_path,
        quantization_strength=max(0.0, min(1.0, quantization_strength)),
        swing_ratio=analysis.swing_ratio or 0.5,
        beat_times=analysis.beats_json,
    )

    return FileResponse(
        midi_result["file_path"],
        media_type="audio/midi",
        filename=f"drums_q{q_pct}.mid",
    )


# ─── v2: Drum Hits API ───────────────────────────────────────────────────

@app.get("/api/projects/{project_id}/drum-hits")
async def get_drum_hits(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get classified drum hits."""
    result = await db.execute(
        select(AnalysisResult).filter(AnalysisResult.project_id == project_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis or not analysis.drum_hits_json:
        raise HTTPException(status_code=404, detail="Drum hits not found")

    return JSONResponse(content={
        "hits": analysis.drum_hits_json,
        "num_hits": analysis.num_drum_hits,
        "groove": analysis.groove_profile_json,
    })


# ─── v2: Groove Profile API ──────────────────────────────────────────────

@app.get("/api/projects/{project_id}/groove")
async def get_groove(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get groove analysis profile."""
    result = await db.execute(
        select(AnalysisResult).filter(AnalysisResult.project_id == project_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis or not analysis.groove_profile_json:
        raise HTTPException(status_code=404, detail="Groove profile not found")

    return JSONResponse(content=analysis.groove_profile_json)


# ─── v2: Confidence Vector API ───────────────────────────────────────────

@app.get("/api/projects/{project_id}/confidence")
async def get_confidence(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get continuous confidence vector."""
    result = await db.execute(
        select(AnalysisResult).filter(AnalysisResult.project_id == project_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis or not analysis.confidence_vector_json:
        raise HTTPException(status_code=404, detail="Confidence data not found")

    return JSONResponse(content=analysis.confidence_vector_json)


# ─── v2: Rhythm Debug (DEBUG ONLY) ────────────────────────────────────

@app.get("/api/projects/{project_id}/rhythm-debug")
async def get_rhythm_debug(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """DEBUG ONLY — Return summarised metrical inference results."""
    result = await db.execute(
        select(AnalysisResult).filter(AnalysisResult.project_id == project_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis or not analysis.metrical_inference_json:
        raise HTTPException(status_code=404, detail="Metrical inference data not found")

    mi = analysis.metrical_inference_json
    windows = mi.get("window_inferences", [])
    modulations = mi.get("detected_modulations", [])
    polyrhythms = mi.get("persistent_polyrhythms", [])

    # Unique dominant meters
    unique_meters = set()
    confidences = []
    ambiguous_count = 0

    for w in windows:
        dom = w.get("dominant")  # key from WindowInferenceResult.to_dict()
        if dom:
            bc = dom.get("beat_count", 0)
            unique_meters.add(f"{bc}/4")
            confidences.append(dom.get("confidence", 0.0))
        if w.get("ambiguous"):  # key from WindowInferenceResult.to_dict()
            ambiguous_count += 1

    # Sample first 10 windows
    sample_windows = []
    for w in windows[:10]:
        dom = w.get("dominant")  # key from WindowInferenceResult.to_dict()
        sample_windows.append({
            "start_time": round(w.get("start_time", 0), 2),
            "end_time": round(w.get("end_time", 0), 2),
            "beat_count": dom.get("beat_count") if dom else None,
            "grouping": dom.get("grouping_vector") if dom else None,
            "confidence": round(dom.get("confidence", 0), 4) if dom else None,
        })

    return JSONResponse(content={
        "unique_meters": sorted(unique_meters),
        "confidence_min": round(min(confidences), 4) if confidences else None,
        "confidence_max": round(max(confidences), 4) if confidences else None,
        "modulation_count": len(modulations),
        "polyrhythm_count": len(polyrhythms),
        "ambiguous_window_count": ambiguous_count,
        "total_windows": len(windows),
        "sample_windows": sample_windows,
    })


@app.get("/api/projects/{project_id}/audio")
async def get_audio(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Stream the original extracted audio."""
    result = await db.execute(select(Project).filter(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project or not project.audio_file_path or not Path(project.audio_file_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    return FileResponse(
        project.audio_file_path,
        media_type="audio/wav",
        filename="audio.wav",
    )


# ─── Section Editing ──────────────────────────────────────────────────────

@app.patch("/api/projects/{project_id}/sections/{section_id}")
async def update_section(
    project_id: UUID,
    section_id: UUID,
    update: SectionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Manually override a section's properties."""
    result = await db.execute(
        select(Section)
        .filter(Section.id == section_id, Section.project_id == project_id)
    )
    section = result.scalar_one_or_none()
    
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(section, field, value)
    
    return {"status": "updated", "section_id": str(section_id)}


# ─── Delete ───────────────────────────────────────────────────────────────

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a project and all associated files."""
    import shutil
    
    result = await db.execute(select(Project).filter(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Delete files
    project_dir = Path(settings.storage_root) / str(project_id)
    if project_dir.exists():
        shutil.rmtree(project_dir, ignore_errors=True)
    
    upload_dir = settings.upload_dir / str(project_id)
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)
    
    await db.delete(project)
    
    return {"status": "deleted", "project_id": str(project_id)}


# ─── Export ───────────────────────────────────────────────────────────────

@app.get("/api/projects/{project_id}/export/json")
async def export_json(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Export full analysis as JSON."""
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.analysis),
            selectinload(Project.sections),
        )
        .filter(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project or not project.analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    export = {
        "project": {
            "name": project.name,
            "original_filename": project.original_filename,
            "duration_seconds": project.duration_seconds,
        },
        "analysis": {
            "pipeline_version": project.analysis.pipeline_version,
            "overall_bpm": project.analysis.overall_bpm,
            "bpm_stable": project.analysis.bpm_stable,
            "time_signature": project.analysis.time_signature,
            "confidence": {
                "stem": project.analysis.confidence_stem.value if project.analysis.confidence_stem else None,
                "beat": project.analysis.confidence_beat.value if project.analysis.confidence_beat else None,
                "downbeat": project.analysis.confidence_downbeat.value if project.analysis.confidence_downbeat else None,
                "meter": project.analysis.confidence_meter.value if project.analysis.confidence_meter else None,
                "sections": project.analysis.confidence_sections.value if project.analysis.confidence_sections else None,
            },
            "beats": project.analysis.beats_json,
            "downbeats": project.analysis.downbeats_json,
            "tempo_curve": project.analysis.tempo_curve_json,
        },
        "sections": [
            {
                "name": s.name,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "bars": s.bars,
                "bpm": s.bpm,
                "meter": s.meter,
                "confidence": s.confidence.value if s.confidence else None,
            }
            for s in project.sections
        ],
    }
    
    return JSONResponse(content=export)
