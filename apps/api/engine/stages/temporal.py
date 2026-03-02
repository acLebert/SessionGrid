"""
Temporal Stage — Beat tracking, downbeat detection, tempo octave correction,
section segmentation, and meter estimation.

Key v2 changes:
  - Tempo octave correction: score BPM, BPM/2, BPM*2 and pick the best.
  - Beat timestamps stored at full float64 precision (no 4-decimal rounding).
  - Section naming removed (was semantically meaningless).
  - Meter estimation uses downbeat spacing distribution, not just mode.
"""

import logging
from collections import Counter
from typing import Optional

import numpy as np
import librosa
from scipy.ndimage import uniform_filter
from scipy.signal import find_peaks

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Beat Tracking + Tempo Octave Correction
# ---------------------------------------------------------------------------


def analyze_beats(y_drums: np.ndarray, sr: int) -> dict:
    """
    Full beat/tempo analysis on the isolated drum stem.

    Returns:
      {
        overall_bpm, bpm_candidates, bpm_stable,
        beat_times, downbeat_times, onset_times,
        tempo_curve, duration_seconds,
        num_beats, num_downbeats,
        octave_correction_applied
      }
    """
    np.random.seed(settings.random_seed)
    duration = len(y_drums) / sr

    # --- Onset envelope (used by beat tracker) ---
    onset_env = librosa.onset.onset_strength(y=y_drums, sr=sr)

    # --- Beat tracking (librosa DP) ---
    raw_tempo, beat_frames = librosa.beat.beat_track(
        y=y_drums, sr=sr, onset_envelope=onset_env
    )

    # Handle tempo array vs scalar
    if hasattr(raw_tempo, "__len__"):
        raw_bpm = float(raw_tempo[0]) if len(raw_tempo) > 0 else 120.0
    else:
        raw_bpm = float(raw_tempo)

    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    # --- Downbeat detection (madmom RNN + DBN) ---
    # We need the file path for madmom — save drums to temp if needed.
    # For now, this will be called separately with the drums file path.
    # The orchestrator provides downbeat_times.

    # --- Tempo curve (local BPM over time) ---
    tempo_curve = _estimate_tempo_curve(beat_times, window_beats=8)
    bpm_stable = _check_tempo_stability(tempo_curve, tolerance=3.0)

    return {
        "raw_bpm": round(raw_bpm, 2),
        "beat_times": beat_times,  # full float64 precision
        "tempo_curve": tempo_curve,
        "bpm_stable": bpm_stable,
        "duration_seconds": round(duration, 3),
        "num_beats": len(beat_times),
    }


def detect_downbeats(audio_path: str) -> Optional[list[float]]:
    """
    Use madmom RNN + DBN for downbeat detection.

    Returns list of downbeat timestamps in seconds, or None on failure.
    """
    try:
        import madmom

        proc = madmom.features.downbeats.DBNDownBeatTrackingProcessor(
            beats_per_bar=[3, 4],
            fps=100,
        )
        act = madmom.features.downbeats.RNNDownBeatProcessor()(audio_path)
        beats = proc(act)

        # beats: [[time, beat_position], ...] — beat_position==1 is downbeat
        downbeat_times = [float(row[0]) for row in beats if int(row[1]) == 1]

        logger.info(f"madmom: {len(downbeat_times)} downbeats detected")
        return downbeat_times

    except Exception as e:
        logger.warning(f"madmom downbeat detection failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Tempo Octave Correction
# ---------------------------------------------------------------------------


def correct_tempo_octave(
    raw_bpm: float,
    beat_times: list[float],
    downbeat_times: list[float],
    onset_times: list[float],
) -> dict:
    """
    Evaluate BPM, BPM/2, BPM*2 and select the best candidate.

    Scoring formula (per candidate):
      score = w_db * downbeat_alignment
            + w_ioi * ioi_stability
            + w_range * range_plausibility

    where:
      - downbeat_alignment: fraction of downbeats that land within
        half a beat period of a grid point.
      - ioi_stability: 1 - CV(inter-beat intervals) for the candidate grid.
      - range_plausibility: Gaussian penalty centered at 120 BPM, σ=40.
        Most popular music is 70–180 BPM.

    Returns:
      {
        corrected_bpm, correction_factor (1, 0.5, or 2),
        candidates: [{bpm, score, downbeat_alignment, ioi_stability, range_score}]
      }
    """
    candidates = []
    factors = [0.5, 1.0, 2.0]

    for factor in factors:
        candidate_bpm = raw_bpm * factor

        # Skip implausible tempos
        if candidate_bpm < 40 or candidate_bpm > 260:
            continue

        # --- Generate ideal grid at this tempo ---
        beat_period = 60.0 / candidate_bpm
        if len(beat_times) < 2:
            candidates.append({
                "bpm": round(candidate_bpm, 2),
                "factor": factor,
                "score": 0.0,
                "downbeat_alignment": 0.0,
                "ioi_stability": 0.0,
                "range_score": 0.0,
            })
            continue

        # --- Downbeat alignment ---
        # What fraction of downbeats land near a grid point?
        half_period = beat_period / 2
        db_alignment = 0.0
        if downbeat_times:
            # Build candidate beat grid
            grid_start = beat_times[0] if beat_times else 0.0
            grid_end = beat_times[-1] if beat_times else 0.0
            grid = np.arange(grid_start, grid_end + beat_period, beat_period)

            if len(grid) > 0:
                aligned = 0
                for db in downbeat_times:
                    min_dist = np.min(np.abs(grid - db))
                    if min_dist < half_period:
                        aligned += 1
                db_alignment = aligned / len(downbeat_times)

        # --- IOI stability at this tempo ---
        # Compute IOIs from actual beat times, evaluate consistency
        # with expected period
        if len(beat_times) >= 2:
            actual_iois = np.diff(beat_times)

            if factor == 0.5:
                # Half tempo: expect IOIs ≈ 2× current period
                expected_ioi = beat_period
                # Re-grid: merge every 2 beats
                merged_times = beat_times[::2]
                if len(merged_times) >= 2:
                    merged_iois = np.diff(merged_times)
                    cv = float(np.std(merged_iois) / (np.mean(merged_iois) + 1e-9))
                    ioi_stability = max(0.0, 1.0 - cv)
                else:
                    ioi_stability = 0.0
            elif factor == 2.0:
                # Double tempo: expect IOIs ≈ half current period
                # We can't subdivide beats we haven't detected,
                # so just evaluate current grid consistency
                cv = float(np.std(actual_iois) / (np.mean(actual_iois) + 1e-9))
                ioi_stability = max(0.0, 1.0 - cv)
                # Penalize if onset density doesn't support doubled tempo
                if onset_times and len(beat_times) >= 2:
                    expected_count = int((beat_times[-1] - beat_times[0]) * candidate_bpm / 60)
                    actual_onset_count = len([
                        t for t in onset_times
                        if beat_times[0] <= t <= beat_times[-1]
                    ])
                    density_ratio = min(actual_onset_count / (expected_count + 1), 1.0)
                    ioi_stability *= (0.5 + 0.5 * density_ratio)
            else:
                cv = float(np.std(actual_iois) / (np.mean(actual_iois) + 1e-9))
                ioi_stability = max(0.0, 1.0 - cv)
        else:
            ioi_stability = 0.0

        # --- Range plausibility (Gaussian prior around 120 BPM, σ=40) ---
        range_score = float(np.exp(-0.5 * ((candidate_bpm - 120) / 40) ** 2))

        # --- Weighted composite score ---
        W_DB = 0.40
        W_IOI = 0.35
        W_RANGE = 0.25

        score = W_DB * db_alignment + W_IOI * ioi_stability + W_RANGE * range_score

        candidates.append({
            "bpm": round(candidate_bpm, 2),
            "factor": factor,
            "score": round(score, 4),
            "downbeat_alignment": round(db_alignment, 4),
            "ioi_stability": round(ioi_stability, 4),
            "range_score": round(range_score, 4),
        })

    # Select winner
    if not candidates:
        return {
            "corrected_bpm": round(raw_bpm, 2),
            "correction_factor": 1.0,
            "candidates": [],
        }

    best = max(candidates, key=lambda c: c["score"])

    if best["factor"] != 1.0:
        logger.info(
            f"Tempo octave correction: {raw_bpm:.1f} → {best['bpm']:.1f} BPM "
            f"(factor={best['factor']}, score={best['score']:.3f})"
        )
    else:
        logger.info(
            f"Tempo octave check: {raw_bpm:.1f} BPM confirmed "
            f"(score={best['score']:.3f})"
        )

    return {
        "corrected_bpm": best["bpm"],
        "correction_factor": best["factor"],
        "candidates": candidates,
    }


# ---------------------------------------------------------------------------
# Section Detection
# ---------------------------------------------------------------------------


def detect_sections(
    y_mono: np.ndarray,
    sr: int,
    beat_times: list[float],
    downbeat_times: list[float],
    overall_bpm: float,
) -> list[dict]:
    """
    Structural segmentation via recurrence matrix + checkerboard novelty.

    v2 changes:
      - Section names are generic (Section 1, 2, …) — no fake "Verse"/"Chorus".
      - Meter estimated per section.
      - Returns boundary_novelty_score for confidence modeling.
    """
    np.random.seed(settings.random_seed)
    duration = len(y_mono) / sr

    # --- Feature extraction ---
    chroma = librosa.feature.chroma_cqt(y=y_mono, sr=sr)
    mfcc = librosa.feature.mfcc(y=y_mono, sr=sr, n_mfcc=13)

    features = np.vstack([
        librosa.util.normalize(chroma, axis=1),
        librosa.util.normalize(mfcc, axis=1),
    ])

    # --- Self-similarity + novelty ---
    rec = librosa.segment.recurrence_matrix(
        features, width=3, mode="affinity", sym=True
    )
    novelty = _checkerboard_novelty(rec)

    peak_frames = _find_section_peaks(novelty, min_distance_seconds=6.0, sr=sr)
    boundary_times = librosa.frames_to_time(peak_frames, sr=sr).tolist()
    boundary_times = [0.0] + sorted(t for t in boundary_times if 0 < t < duration) + [duration]

    # --- Build sections ---
    sections = []
    for i in range(len(boundary_times) - 1):
        start = boundary_times[i]
        end = boundary_times[i + 1]

        bars, meter, meter_confidence = _estimate_meter_and_bars(
            start, end, beat_times, downbeat_times, overall_bpm
        )

        section_beats = [t for t in beat_times if start <= t < end]
        if len(section_beats) >= 2:
            iois = np.diff(section_beats)
            local_bpm = round(60.0 / float(np.median(iois)), 1)
        else:
            local_bpm = overall_bpm

        # Boundary novelty score (0-1)
        if i > 0 and (i - 1) < len(peak_frames):
            pf = peak_frames[i - 1]
            nov_max = float(novelty.max()) if novelty.max() > 0 else 1.0
            boundary_novelty = float(novelty[pf]) / nov_max if pf < len(novelty) else 0.0
        else:
            boundary_novelty = 1.0  # song start

        sections.append({
            "order_index": i,
            "name": f"Section {i + 1}",
            "start_time": round(start, 4),
            "end_time": round(end, 4),
            "bars": bars,
            "bpm": local_bpm,
            "meter": meter,
            "meter_confidence": meter_confidence,
            "boundary_novelty_score": round(boundary_novelty, 4),
        })

    logger.info(f"Detected {len(sections)} sections")
    return sections


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _estimate_tempo_curve(beat_times: list[float], window_beats: int = 8) -> list[dict]:
    if len(beat_times) < 2:
        return []
    iois = np.diff(beat_times)
    curve = []
    step = max(1, window_beats // 2)
    for i in range(0, len(iois), step):
        window = iois[i:i + window_beats]
        if len(window) < 2:
            break
        avg_ioi = float(np.mean(window))
        local_bpm = 60.0 / avg_ioi if avg_ioi > 0 else 0
        curve.append({
            "time": round(float(beat_times[i]), 4),
            "bpm": round(local_bpm, 2),
        })
    return curve


def _check_tempo_stability(tempo_curve: list[dict], tolerance: float = 3.0) -> bool:
    if len(tempo_curve) < 2:
        return True
    bpms = [p["bpm"] for p in tempo_curve]
    return (max(bpms) - min(bpms)) <= (tolerance * 2)


def _checkerboard_novelty(rec: np.ndarray, kernel_size: int = 64) -> np.ndarray:
    n = rec.shape[0]
    if n < kernel_size:
        kernel_size = max(4, n // 2)

    half = kernel_size // 2
    kern = np.ones((kernel_size, kernel_size))
    kern[:half, half:] = -1
    kern[half:, :half] = -1

    novelty = np.zeros(n)
    for i in range(half, n - half):
        patch = rec[i - half:i + half, i - half:i + half]
        if patch.shape == kern.shape:
            novelty[i] = np.sum(patch * kern)

    novelty = np.maximum(0, novelty)
    if len(novelty) > 8:
        novelty = uniform_filter(novelty, size=8)
    return novelty


def _find_section_peaks(
    novelty: np.ndarray,
    min_distance_seconds: float = 6.0,
    sr: int = 44100,
    hop_length: int = 512,
) -> np.ndarray:
    min_distance_frames = int(min_distance_seconds * sr / hop_length)

    if novelty.max() > 0:
        novelty_norm = novelty / novelty.max()
    else:
        return np.array([])

    threshold = np.median(novelty_norm) + 0.5 * np.std(novelty_norm)

    peaks, _ = find_peaks(
        novelty_norm,
        height=threshold,
        distance=min_distance_frames,
        prominence=0.1,
    )
    return peaks


def _estimate_meter_and_bars(
    start: float,
    end: float,
    beat_times: list[float],
    downbeat_times: list[float],
    overall_bpm: float,
) -> tuple[int, str, str]:
    section_beats = [t for t in beat_times if start <= t < end]
    section_downbeats = [t for t in downbeat_times if start <= t < end]

    if len(section_downbeats) >= 2:
        beats_per_bar_samples = []
        for j in range(len(section_downbeats) - 1):
            db_s = section_downbeats[j]
            db_e = section_downbeats[j + 1]
            bpb = len([b for b in section_beats if db_s <= b < db_e])
            if bpb > 0:
                beats_per_bar_samples.append(bpb)

        if beats_per_bar_samples:
            counter = Counter(beats_per_bar_samples)
            most_common_bpb = counter.most_common(1)[0][0]
            meter_map = {2: "2/4", 3: "3/4", 4: "4/4", 6: "6/8"}
            meter = meter_map.get(most_common_bpb, f"{most_common_bpb}/4")
            bars = len(section_downbeats)
            consistency = counter.most_common(1)[0][1] / len(beats_per_bar_samples)
            conf = "high" if consistency > 0.85 else ("medium" if consistency > 0.6 else "low")
            return bars, meter, conf

    estimated_bars = max(1, round(len(section_beats) / 4))
    return estimated_bars, "4/4", "low"
