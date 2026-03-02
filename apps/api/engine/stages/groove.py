"""
Groove Stage — Swing detection, microtiming analysis, accent profiling.

This module operates on the drum stem's onset times + the computed beat grid
to extract groove characteristics that go beyond "where are the beats".

Key metrics:
  - Swing ratio: deviation of off-beat onsets from straight 8th-note grid.
  - Microtiming deviation: per-beat timing error relative to the quantized grid.
  - Accent profile: velocity/strength emphasis pattern across the bar.
  - Groove tightness: aggregate timing variance around the grid.
  - Groove type classification: straight / light-swing / swing / heavy-swing / shuffle.

All computations use sample-level onset times from the signal stage.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class GrooveProfile:
    """Complete groove analysis output."""
    swing_ratio_mean: float = 0.5       # 0.5 = straight, 0.67 = triplet swing
    swing_ratio_std: float = 0.0        # variance in swing ratio
    groove_type: str = "straight"       # straight|light_swing|swing|heavy_swing|shuffle
    accent_profile: list[float] = field(default_factory=list)  # per-subdivision strength
    microtiming_deviations_ms: list[float] = field(default_factory=list)
    groove_tightness_score: float = 0.0  # 0–1, higher = tighter
    mean_deviation_ms: float = 0.0
    median_deviation_ms: float = 0.0
    num_analyzed_beats: int = 0

    def to_dict(self) -> dict:
        return {
            "swing_ratio_mean": round(self.swing_ratio_mean, 4),
            "swing_ratio_std": round(self.swing_ratio_std, 4),
            "groove_type": self.groove_type,
            "accent_profile": [round(a, 4) for a in self.accent_profile],
            "microtiming_deviations_ms": [round(d, 3) for d in self.microtiming_deviations_ms],
            "groove_tightness_score": round(self.groove_tightness_score, 4),
            "mean_deviation_ms": round(self.mean_deviation_ms, 3),
            "median_deviation_ms": round(self.median_deviation_ms, 3),
            "num_analyzed_beats": self.num_analyzed_beats,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_groove(
    onset_times: list[float],
    onset_strengths: list[float],
    beat_times: list[float],
    downbeat_times: list[float],
    bpm: float,
    subdivisions: int = 2,
) -> GrooveProfile:
    """
    Full groove analysis.

    Parameters
    ----------
    onset_times : list[float]
        Sample-level refined onset timestamps from the drum stem.
    onset_strengths : list[float]
        Onset strength values (proxy for velocity).
    beat_times : list[float]
        Beat grid timestamps.
    downbeat_times : list[float]
        Downbeat timestamps.
    bpm : float
        Overall tempo.
    subdivisions : int
        Subdivision level for swing analysis (2 = 8th notes, 4 = 16th notes).

    Returns
    -------
    GrooveProfile
    """
    if len(beat_times) < 4 or len(onset_times) < 4:
        logger.warning("Insufficient data for groove analysis")
        return GrooveProfile()

    beat_period = 60.0 / bpm
    sub_period = beat_period / subdivisions

    # === 1. Build subdivision grid ===
    grid_points = _build_subdivision_grid(beat_times, subdivisions)

    if len(grid_points) < 4:
        return GrooveProfile()

    # === 2. Match onsets to nearest grid point ===
    matched = _match_onsets_to_grid(onset_times, onset_strengths, grid_points, sub_period)

    # === 3. Compute swing ratio ===
    swing_ratios = _compute_swing_ratios(matched, subdivisions)
    if swing_ratios:
        swing_mean = float(np.mean(swing_ratios))
        swing_std = float(np.std(swing_ratios))
    else:
        swing_mean = 0.5
        swing_std = 0.0

    # === 4. Compute microtiming deviations ===
    deviations_ms = [m["deviation_ms"] for m in matched if m["deviation_ms"] is not None]
    if deviations_ms:
        mean_dev = float(np.mean(np.abs(deviations_ms)))
        median_dev = float(np.median(np.abs(deviations_ms)))
    else:
        mean_dev = 0.0
        median_dev = 0.0

    # === 5. Groove tightness ===
    # Tightness = 1 - normalized_std_deviation
    # Scale: 0ms std → 1.0 (perfect), 30ms std → 0.0 (sloppy)
    if deviations_ms:
        std_dev = float(np.std(deviations_ms))
        tightness = max(0.0, 1.0 - (std_dev / 30.0))
    else:
        tightness = 0.0

    # === 6. Accent profile ===
    accent_profile = _compute_accent_profile(matched, subdivisions, beat_times, downbeat_times)

    # === 7. Classify groove type ===
    groove_type = _classify_groove(swing_mean, swing_std, tightness)

    profile = GrooveProfile(
        swing_ratio_mean=swing_mean,
        swing_ratio_std=swing_std,
        groove_type=groove_type,
        accent_profile=accent_profile,
        microtiming_deviations_ms=deviations_ms[:200],  # cap for storage
        groove_tightness_score=tightness,
        mean_deviation_ms=mean_dev,
        median_deviation_ms=median_dev,
        num_analyzed_beats=len(beat_times),
    )

    logger.info(
        f"Groove analysis: type={groove_type}, swing={swing_mean:.3f}±{swing_std:.3f}, "
        f"tightness={tightness:.3f}, mean_dev={mean_dev:.1f}ms"
    )

    return profile


# ---------------------------------------------------------------------------
# Internal algorithms
# ---------------------------------------------------------------------------


def _build_subdivision_grid(
    beat_times: list[float], subdivisions: int
) -> list[dict]:
    """
    Build a subdivision grid from beat times.

    Returns list of {time, beat_index, sub_index} where sub_index 0..subdivisions-1.
    """
    grid = []
    for i in range(len(beat_times) - 1):
        t0 = beat_times[i]
        t1 = beat_times[i + 1]
        for s in range(subdivisions):
            frac = s / subdivisions
            grid.append({
                "time": t0 + frac * (t1 - t0),
                "beat_index": i,
                "sub_index": s,
            })
    # Add last beat
    if beat_times:
        grid.append({
            "time": beat_times[-1],
            "beat_index": len(beat_times) - 1,
            "sub_index": 0,
        })
    return grid


def _match_onsets_to_grid(
    onset_times: list[float],
    onset_strengths: list[float],
    grid: list[dict],
    max_distance: float,
) -> list[dict]:
    """
    For each onset, find the nearest grid point and compute deviation.

    Returns list of matched events with deviation and strength.
    """
    if not grid or not onset_times:
        return []

    grid_times = np.array([g["time"] for g in grid])
    matched = []

    for idx, onset_t in enumerate(onset_times):
        dists = np.abs(grid_times - onset_t)
        nearest_idx = int(np.argmin(dists))
        min_dist = float(dists[nearest_idx])

        if min_dist > max_distance:
            continue  # onset too far from any grid point

        deviation_s = onset_t - grid[nearest_idx]["time"]
        deviation_ms = deviation_s * 1000.0

        strength = onset_strengths[idx] if idx < len(onset_strengths) else 0.0

        matched.append({
            "onset_time": onset_t,
            "grid_time": grid[nearest_idx]["time"],
            "beat_index": grid[nearest_idx]["beat_index"],
            "sub_index": grid[nearest_idx]["sub_index"],
            "deviation_ms": deviation_ms,
            "strength": strength,
        })

    return matched


def _compute_swing_ratios(matched: list[dict], subdivisions: int) -> list[float]:
    """
    Compute swing ratio for each pair of on-beat + off-beat subdivisions.

    Swing ratio = duration of first subdivision / total beat period.
    Straight = 0.50, triplet swing ≈ 0.667, hard swing ≈ 0.75.

    For subdivision=2 (8th notes):
      On-beat hits land at sub_index=0, off-beat at sub_index=1.
      We measure the actual timing of each off-beat hit relative to the
      surrounding on-beat hits to compute the swing ratio.
    """
    if subdivisions != 2:
        # Swing ratio is only meaningful for 8th-note subdivisions
        return []

    # Group by beat
    from collections import defaultdict
    by_beat = defaultdict(list)
    for m in matched:
        by_beat[m["beat_index"]].append(m)

    ratios = []
    sorted_beats = sorted(by_beat.keys())

    for bi in sorted_beats:
        events = by_beat[bi]
        on_beats = [e for e in events if e["sub_index"] == 0]
        off_beats = [e for e in events if e["sub_index"] == 1]

        if not on_beats or not off_beats:
            continue

        # Find on-beat time for this beat and next beat
        on_time = on_beats[0]["onset_time"]

        # Find next beat's on-beat
        if bi + 1 in by_beat:
            next_on = [e for e in by_beat[bi + 1] if e["sub_index"] == 0]
            if next_on:
                next_on_time = next_on[0]["onset_time"]
                off_time = off_beats[0]["onset_time"]
                total_period = next_on_time - on_time
                if total_period > 0:
                    first_half = off_time - on_time
                    ratio = first_half / total_period
                    # Clamp to reasonable range
                    if 0.3 <= ratio <= 0.85:
                        ratios.append(ratio)

    return ratios


def _compute_accent_profile(
    matched: list[dict],
    subdivisions: int,
    beat_times: list[float],
    downbeat_times: list[float],
) -> list[float]:
    """
    Compute average accent strength per subdivision position within a bar.

    For 4/4 with 8th notes (subdivisions=2): 8 positions per bar.
    Returns normalized strengths [0, 1] per position.
    """
    # Determine beats per bar from downbeat spacing
    if len(downbeat_times) >= 2:
        db_iois = np.diff(downbeat_times)
        median_db_ioi = float(np.median(db_iois))
        if len(beat_times) >= 2:
            beat_iois = np.diff(beat_times)
            median_beat_ioi = float(np.median(beat_iois))
            if median_beat_ioi > 0:
                beats_per_bar = max(2, min(7, round(median_db_ioi / median_beat_ioi)))
            else:
                beats_per_bar = 4
        else:
            beats_per_bar = 4
    else:
        beats_per_bar = 4

    positions_per_bar = beats_per_bar * subdivisions
    strength_accum = np.zeros(positions_per_bar)
    count_accum = np.zeros(positions_per_bar)

    # Determine which beat in the bar each matched onset falls in
    db_arr = np.array(downbeat_times) if downbeat_times else np.array([0.0])

    for m in matched:
        t = m["onset_time"]
        # Find which bar this onset is in
        bar_idx = int(np.searchsorted(db_arr, t, side="right")) - 1
        if bar_idx < 0:
            bar_idx = 0

        # Position within bar: beat_in_bar * subdivisions + sub_index
        if bar_idx < len(db_arr):
            bar_start = db_arr[bar_idx]
        else:
            continue

        # Find beat index within this bar
        bar_beats = [
            bt for bt in beat_times
            if bar_start <= bt < bar_start + (beats_per_bar + 0.5) * (60.0 / 120.0)
        ]

        beat_in_bar = m["beat_index"] % beats_per_bar
        pos = beat_in_bar * subdivisions + m["sub_index"]

        if 0 <= pos < positions_per_bar:
            strength_accum[pos] += m["strength"]
            count_accum[pos] += 1

    # Normalize
    with np.errstate(divide="ignore", invalid="ignore"):
        avg_strength = np.where(count_accum > 0, strength_accum / count_accum, 0.0)

    max_s = avg_strength.max()
    if max_s > 0:
        avg_strength = avg_strength / max_s

    return avg_strength.tolist()


def _classify_groove(swing_mean: float, swing_std: float, tightness: float) -> str:
    """
    Classify groove type from swing ratio statistics.

    Classification thresholds:
      straight:     ratio < 0.53
      light_swing:  0.53 ≤ ratio < 0.58
      swing:        0.58 ≤ ratio < 0.65
      heavy_swing:  0.65 ≤ ratio < 0.72
      shuffle:      ratio ≥ 0.72
    """
    if swing_std > 0.12:
        # Inconsistent swing — probably not intentional
        return "irregular"

    if swing_mean < 0.53:
        return "straight"
    elif swing_mean < 0.58:
        return "light_swing"
    elif swing_mean < 0.65:
        return "swing"
    elif swing_mean < 0.72:
        return "heavy_swing"
    else:
        return "shuffle"
