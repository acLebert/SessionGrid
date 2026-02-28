"""Beat & Rhythm Analysis Service — librosa + madmom-based analysis."""

import logging
import numpy as np
import librosa

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def analyze_beats(audio_path: str) -> dict:
    """
    Full beat analysis pipeline:
    - Onset detection
    - Beat tracking (librosa)
    - Downbeat detection (madmom)
    - Tempo estimation
    - Tempo stability check
    
    Returns comprehensive beat analysis dict.
    """
    np.random.seed(settings.random_seed)
    
    logger.info(f"Loading audio for beat analysis: {audio_path}")
    y, sr = librosa.load(audio_path, sr=settings.sample_rate, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)
    
    logger.info(f"Audio loaded: {duration:.1f}s at {sr}Hz")
    
    # ─── Onset Detection ────────────────────────────────────────────────
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, onset_envelope=onset_env)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr).tolist()
    
    # ─── Beat Tracking (librosa) ────────────────────────────────────────
    tempo_estimate, beat_frames = librosa.beat.beat_track(
        y=y, sr=sr, onset_envelope=onset_env
    )
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    
    # Handle tempo — librosa may return array or scalar
    if hasattr(tempo_estimate, '__len__'):
        overall_bpm = float(tempo_estimate[0]) if len(tempo_estimate) > 0 else 120.0
    else:
        overall_bpm = float(tempo_estimate)
    
    # ─── Tempo Curve (local tempo over time) ────────────────────────────
    tempo_curve = _estimate_tempo_curve(beat_times)
    bpm_stable = _check_tempo_stability(tempo_curve, tolerance=3.0)
    
    # ─── Downbeat Detection (madmom) ────────────────────────────────────
    downbeat_times = _detect_downbeats_madmom(audio_path)
    
    # Fallback: if madmom fails, estimate downbeats from beats (every 4 beats)
    if downbeat_times is None or len(downbeat_times) == 0:
        logger.warning("Madmom downbeat detection failed, using fallback (every 4 beats)")
        downbeat_times = beat_times[::4] if len(beat_times) >= 4 else beat_times[:1]
    
    logger.info(f"Analysis complete: {overall_bpm:.1f} BPM, {len(beat_times)} beats, {len(downbeat_times)} downbeats")
    
    return {
        "overall_bpm": round(overall_bpm, 2),
        "bpm_stable": bpm_stable,
        "beat_times": [round(t, 4) for t in beat_times],
        "downbeat_times": [round(t, 4) for t in downbeat_times],
        "onset_times": [round(t, 4) for t in onset_times],
        "tempo_curve": tempo_curve,
        "duration_seconds": round(duration, 3),
        "num_beats": len(beat_times),
        "num_downbeats": len(downbeat_times),
    }


def _estimate_tempo_curve(beat_times: list[float], window_beats: int = 8) -> list[dict]:
    """Estimate local tempo over time from beat positions."""
    if len(beat_times) < 2:
        return []
    
    iois = np.diff(beat_times)  # Inter-onset intervals
    curve = []
    
    for i in range(0, len(iois), max(1, window_beats // 2)):
        window = iois[i:i + window_beats]
        if len(window) < 2:
            break
        
        avg_ioi = np.mean(window)
        local_bpm = 60.0 / avg_ioi if avg_ioi > 0 else 0
        time_pos = beat_times[i]
        
        curve.append({
            "time": round(float(time_pos), 3),
            "bpm": round(float(local_bpm), 2),
        })
    
    return curve


def _check_tempo_stability(tempo_curve: list[dict], tolerance: float = 3.0) -> bool:
    """Check if tempo stays within ±tolerance BPM across the song."""
    if len(tempo_curve) < 2:
        return True
    
    bpms = [point["bpm"] for point in tempo_curve]
    return (max(bpms) - min(bpms)) <= (tolerance * 2)


def _detect_downbeats_madmom(audio_path: str) -> list[float] | None:
    """
    Use madmom for downbeat detection (superior to librosa for this task).
    Returns list of downbeat timestamps, or None on failure.
    """
    try:
        import madmom
        
        proc = madmom.features.downbeats.DBNDownBeatTrackingProcessor(
            beats_per_bar=[3, 4],
            fps=100,
        )
        act = madmom.features.downbeats.RNNDownBeatProcessor()(audio_path)
        beats = proc(act)
        
        # beats is array of [[time, beat_position], ...]
        # beat_position == 1 means downbeat
        downbeat_times = [float(row[0]) for row in beats if int(row[1]) == 1]
        
        logger.info(f"madmom detected {len(downbeat_times)} downbeats")
        return downbeat_times
        
    except Exception as e:
        logger.warning(f"madmom downbeat detection failed: {e}")
        return None
