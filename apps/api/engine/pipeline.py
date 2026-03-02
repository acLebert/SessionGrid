"""
SessionGrid Engine v2 — Pipeline Orchestrator.

Pure-function pipeline that chains all stages.  Has zero database or
Celery dependencies; the Celery task (workers/tasks.py) calls into this
and handles persistence.

Stage ordering:
  1. separation_stage  → stereo extract + Demucs stems
  2. signal_stage      → onset detection + sample-level refinement (on drum stem)
  3. temporal_stage    → beat tracking, downbeats, tempo octave correction, sections
  4. groove_stage      → swing, microtiming, accent profiling
  5. hit_stage         → drum hit classification
  6. export_stage      → MIDI, click, waveforms
  + confidence         → metric vector
  + versioning         → manifest, caching
"""

import logging
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import librosa

from config import get_settings
from engine import ENGINE_VERSION
from engine.stages.separation import extract_audio, separate_stems
from engine.stages.signal import detect_onsets, onset_times_from_result, onset_strengths_from_result
from engine.stages.temporal import (
    analyze_beats, detect_downbeats, correct_tempo_octave, detect_sections,
)
from engine.stages.groove import analyze_groove
from engine.stages.hits import classify_hits, DrumHit
from engine.stages.export import export_midi, generate_click_track, generate_waveform_peaks
from engine.confidence import compute_confidence
from engine.stages.metrical_inference import run_metrical_inference
from engine.stages.subdivision_graph import PersistentSubdivisionGraphBuilder
from engine.versioning import (
    load_manifest, save_manifest, get_stale_stages,
    mark_stage_complete, cache_artifact,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Progress callback type
# ---------------------------------------------------------------------------

ProgressCallback = Optional[Callable[[str, int, str], None]]
"""(stage_name, progress_percent, message) → None"""


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_pipeline(
    input_file_path: str,
    project_dir: str,
    on_progress: ProgressCallback = None,
    force_rerun: bool = False,
) -> dict:
    """
    Execute the full v2 analysis pipeline.

    Parameters
    ----------
    input_file_path : str
        Path to the uploaded audio/video file.
    project_dir : str
        Per-project storage directory.
    on_progress : callable, optional
        Progress callback (stage, percent, message).
    force_rerun : bool
        If True, ignore cached artifacts and re-run everything.

    Returns
    -------
    dict with all analysis results, keyed by stage.
    """
    t0 = time.time()
    project_dir = str(Path(project_dir))

    def progress(stage: str, pct: int, msg: str = ""):
        if on_progress:
            on_progress(stage, pct, msg)
        logger.info(f"[{stage}] {pct}% — {msg}")

    # --- Load / initialize manifest ---
    manifest = load_manifest(project_dir)
    if force_rerun:
        manifest.stages_completed.clear()
    stale = get_stale_stages(manifest)
    logger.info(f"Engine v{ENGINE_VERSION}, stale stages: {stale or 'none'}")

    results = {}

    # =====================================================================
    # STAGE 1: SEPARATION
    # =====================================================================
    progress("separation", 5, "Extracting audio…")

    extract_result = extract_audio(input_file_path, project_dir)
    results["extraction"] = extract_result

    progress("separation", 20, "Separating stems (Demucs)…")

    stems_dir = str(Path(project_dir) / "stems")
    stem_result = separate_stems(extract_result["stereo_path"], stems_dir)
    results["stems"] = stem_result

    mark_stage_complete(manifest, "separation")

    # Get the drum stem waveform (mono, target SR)
    y_drums = stem_result["stem_waveforms"]["drums"]
    sr = settings.sample_rate

    # Also load the mono mix for section detection
    y_mono, _ = librosa.load(extract_result["mono_path"], sr=sr, mono=True)

    # =====================================================================
    # STAGE 2: SIGNAL (onset detection + refinement)
    # =====================================================================
    progress("signal", 35, "Detecting onsets (sample-level)…")

    signal_result = detect_onsets(
        y=y_drums, sr=sr,
        hop_length=512,
        search_radius=512,
        backtrack=True,
        dedup_samples=256,
    )
    results["signal"] = {
        "num_raw_onsets": signal_result.num_raw_onsets,
        "num_refined_onsets": signal_result.num_refined_onsets,
    }

    onset_times = onset_times_from_result(signal_result)
    onset_strengths = onset_strengths_from_result(signal_result)
    onset_sample_indices = [o.sample_index for o in signal_result.onsets]

    # Cache onset array
    cache_artifact(
        project_dir, "signal", "onset_times",
        np.array(onset_times), manifest,
    )
    mark_stage_complete(manifest, "signal")

    # =====================================================================
    # STAGE 3: TEMPORAL (beats, downbeats, tempo correction, sections)
    # =====================================================================
    progress("temporal", 50, "Tracking beats…")

    beat_result = analyze_beats(y_drums, sr)

    progress("temporal", 58, "Detecting downbeats (madmom)…")

    # madmom needs a file path
    drums_path = stem_result["stem_paths"]["drums"]
    downbeat_times = detect_downbeats(drums_path)

    if downbeat_times is None or len(downbeat_times) == 0:
        logger.warning("Downbeat detection failed, using fallback")
        downbeat_times = beat_result["beat_times"][::4]
        if not downbeat_times and beat_result["beat_times"]:
            downbeat_times = [beat_result["beat_times"][0]]

    progress("temporal", 63, "Correcting tempo octave…")

    octave_result = correct_tempo_octave(
        raw_bpm=beat_result["raw_bpm"],
        beat_times=beat_result["beat_times"],
        downbeat_times=downbeat_times,
        onset_times=onset_times,
    )

    corrected_bpm = octave_result["corrected_bpm"]

    progress("temporal", 68, "Detecting sections…")

    sections = detect_sections(
        y_mono=y_mono, sr=sr,
        beat_times=beat_result["beat_times"],
        downbeat_times=downbeat_times,
        overall_bpm=corrected_bpm,
    )

    results["temporal"] = {
        "raw_bpm": beat_result["raw_bpm"],
        "corrected_bpm": corrected_bpm,
        "octave_correction": octave_result,
        "bpm_stable": beat_result["bpm_stable"],
        "beat_times": beat_result["beat_times"],
        "downbeat_times": downbeat_times,
        "onset_times": onset_times,
        "tempo_curve": beat_result["tempo_curve"],
        "duration_seconds": beat_result["duration_seconds"],
        "num_beats": beat_result["num_beats"],
        "num_downbeats": len(downbeat_times),
        "sections": sections,
        "time_signature": sections[0]["meter"] if sections else "4/4",
    }

    mark_stage_complete(manifest, "temporal")

    # =====================================================================
    # STAGE 3b: METRICAL INFERENCE (debug — attached to results)
    # =====================================================================
    progress("temporal", 70, "Running metrical inference…")

    try:
        metrical_result = run_metrical_inference(
            onset_times=onset_times,
            duration_seconds=beat_result["duration_seconds"],
            sr=sr,
            estimated_bpm=corrected_bpm,
            onset_strengths=onset_strengths,
            downbeat_times=downbeat_times,
        )
        # DEBUG ONLY — temporary logging for serialization verification
        n_win = len(metrical_result.window_inferences)
        n_dom_obj = sum(1 for w in metrical_result.window_inferences if w.dominant_hypothesis is not None)
        logger.info(f"[metrical_inference] {n_win} windows, {n_dom_obj} with dominant object")
        if metrical_result.global_dominant:
            gd = metrical_result.global_dominant
            logger.info(f"[metrical_inference] global_dominant: beat_count={gd.beat_count}, period={gd.base_period_seconds:.4f}, conf={gd.confidence:.4f}")
        else:
            logger.info("[metrical_inference] global_dominant: None")
        mi_dict = metrical_result.to_dict()
        n_dom_dict = sum(1 for w in mi_dict.get("window_inferences", []) if w.get("dominant") is not None)
        logger.info(f"[metrical_inference] After to_dict(): {n_dom_dict}/{n_win} windows have dominant != null")
        logger.info(f"[metrical_inference] Modulations: {len(mi_dict.get('detected_modulations', []))}")
        results["metrical_inference"] = mi_dict
    except Exception as _mi_err:
        logger.warning(f"Metrical inference failed (non-fatal): {_mi_err}")
        results["metrical_inference"] = None

    # =====================================================================
    # STAGE 3c: SUBDIVISION GRAPH
    # =====================================================================
    progress("subdivision_graph", 70, "Building subdivision graph…")
    try:
        _sg_builder = PersistentSubdivisionGraphBuilder(window_beats=8)
        _sg_graph = _sg_builder.build(
            onset_times=onset_times,
            onset_strengths=onset_strengths,
            beat_times=beat_result["beat_times"],
            downbeat_times=downbeat_times,
        )
        results["subdivision_graph"] = _sg_graph.to_dict()
        logger.info(
            f"[subdivision_graph] {len(_sg_graph.layers)} layers, "
            f"{len(_sg_graph.phase_relations)} phase relations"
        )
    except Exception as _sg_err:
        logger.warning(f"Subdivision graph failed (non-fatal): {_sg_err}")
        results["subdivision_graph"] = None

    # =====================================================================
    # STAGE 4: GROOVE
    # =====================================================================
    progress("groove", 73, "Analyzing groove…")

    groove_profile = analyze_groove(
        onset_times=onset_times,
        onset_strengths=onset_strengths,
        beat_times=beat_result["beat_times"],
        downbeat_times=downbeat_times,
        bpm=corrected_bpm,
        subdivisions=2,
    )
    results["groove"] = groove_profile.to_dict()

    mark_stage_complete(manifest, "groove")

    # =====================================================================
    # STAGE 5: HIT CLASSIFICATION
    # =====================================================================
    progress("hits", 80, "Classifying drum hits…")

    drum_hits = classify_hits(
        y_drums=y_drums,
        sr=sr,
        onset_times=onset_times,
        onset_sample_indices=onset_sample_indices,
        onset_strengths=onset_strengths,
        window_ms=50.0,
    )

    hits_dicts = [h.to_dict() for h in drum_hits]
    hit_confidences = [h.confidence for h in drum_hits]
    results["hits"] = {
        "drum_hits": hits_dicts,
        "num_hits": len(drum_hits),
    }

    mark_stage_complete(manifest, "hits")

    # =====================================================================
    # STAGE 6: EXPORT (MIDI + click + waveforms)
    # =====================================================================
    progress("export", 87, "Generating MIDI…")

    midi_path = str(Path(project_dir) / "drums.mid")
    try:
        midi_result = export_midi(
            hits=hits_dicts,
            tempo_curve=beat_result["tempo_curve"],
            time_signature=results["temporal"]["time_signature"],
            sections=sections,
            output_path=midi_path,
            quantization_strength=0.0,  # raw timing by default
            swing_ratio=groove_profile.swing_ratio_mean,
            beat_times=beat_result["beat_times"],
        )
        results["midi"] = midi_result
    except ImportError:
        logger.warning("mido not installed — skipping MIDI export")
        results["midi"] = None

    progress("export", 91, "Generating click track…")

    click_path = str(Path(project_dir) / "click.wav")
    click_result = generate_click_track(
        beat_times=beat_result["beat_times"],
        downbeat_times=downbeat_times,
        duration_seconds=beat_result["duration_seconds"],
        output_path=click_path,
        mode="quarter",
        swing_ratio=groove_profile.swing_ratio_mean,
    )
    results["click"] = click_result

    progress("export", 94, "Generating waveforms…")

    # Waveform peaks for mix + all stems
    waveform_path = str(Path(project_dir) / "waveform.json")
    generate_waveform_peaks(extract_result["mono_path"], waveform_path)

    for stem_name, stem_path in stem_result["stem_paths"].items():
        wp = str(Path(project_dir) / f"waveform_{stem_name}.json")
        generate_waveform_peaks(stem_path, wp)

    mark_stage_complete(manifest, "export")

    # =====================================================================
    # CONFIDENCE SCORING
    # =====================================================================
    progress("confidence", 97, "Computing confidence…")

    confidence = compute_confidence(
        beat_times=beat_result["beat_times"],
        downbeat_times=downbeat_times,
        tempo_curve=beat_result["tempo_curve"],
        sections=sections,
        groove_profile=results["groove"],
        hit_confidences=hit_confidences,
        bpm=corrected_bpm,
    )
    results["confidence"] = confidence.to_dict()

    # =====================================================================
    # FINALIZE
    # =====================================================================
    elapsed_ms = int((time.time() - t0) * 1000)
    results["pipeline"] = {
        "engine_version": ENGINE_VERSION,
        "elapsed_ms": elapsed_ms,
        "stages_run": manifest.stages_completed,
    }

    # Save manifest
    manifest.config_snapshot = {
        "sample_rate": settings.sample_rate,
        "demucs_model": settings.demucs_model,
        "random_seed": settings.random_seed,
    }
    save_manifest(project_dir, manifest)

    progress("complete", 100, f"Pipeline complete in {elapsed_ms}ms")

    return results
