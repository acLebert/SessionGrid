"""
SessionGrid Engine — Persistent Subdivision Graph Builder

Structural modeling layer that builds a multi-layer subdivision graph
from drum onset data using beat-aligned adaptive windows.

This stage does NOT:
  - Assign meter
  - Collapse hierarchy
  - Declare modulation
  - Choose dominant layers
  - Interpret grammar

It only builds structure: subdivision layers, their persistence across
time, and phase relationships between layers.

Architecture
------------
Input:  onset_times, onset_strengths, beat_times, downbeat_times
        (all computed upstream)

Windowing:  Adaptive beat-aligned windows of N beats (default 8),
            sliding by 1 beat.  Never fixed-second windows.

Output:  RhythmGraph containing persistent SubdivisionLayers and
         PhaseRelations.

Complexity: O(W × R × N) where W = windows, R = candidate ratios,
            N = onsets per window.

Future: Designed for extension to guitar/bass/piano stems — the
        builder accepts generic onset data, not drum-specific features.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WINDOW_BEATS: int = 8
"""Number of beats per analysis window."""

CANDIDATE_RATIOS: Tuple[int, ...] = (2, 3, 4, 5, 7, 9)
"""Subdivision ratios to test: r subdivisions per beat."""

ALIGNMENT_TOLERANCE_SECONDS: float = 0.020
"""Tolerance for alignment error in confidence computation (20 ms)."""

PERSISTENCE_ALPHA: float = 0.3
"""EMA smoothing coefficient for layer confidence (higher = more reactive)."""

PERSISTENCE_DECAY: float = 0.85
"""Per-window multiplicative decay for non-observed layers."""

PERSISTENCE_FLOOR: float = 0.01
"""Minimum persistence score before layer is pruned."""

PHASE_MERGE_TOLERANCE: float = 0.10
"""Phase difference (in [0, 1)) below which two layers with same ratio
are considered the same layer and merged."""

PHASE_STABILITY_ALPHA: float = 0.2
"""EMA smoothing for phase relationship tracking."""

MIN_ONSETS_PER_WINDOW: int = 3
"""Minimum onsets required in a window for subdivision analysis."""


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class SubdivisionLayer:
    """A persistent subdivision layer in the rhythm graph.

    Represents a detected subdivision ratio (e.g. 2 = 8th notes,
    3 = triplets, 4 = 16ths) with tracked confidence, phase, and
    temporal extent.
    """
    ratio: int
    avg_confidence: float
    phase: float                # in [0, 1)
    first_seen_beat: int
    last_seen_beat: int
    persistence_score: float

    def to_dict(self) -> dict:
        return {
            "ratio": self.ratio,
            "avg_confidence": round(self.avg_confidence, 4),
            "phase": round(self.phase, 4),
            "first_seen_beat": self.first_seen_beat,
            "last_seen_beat": self.last_seen_beat,
            "persistence_score": round(self.persistence_score, 4),
        }


@dataclass
class PhaseRelation:
    """A tracked phase relationship between two subdivision layers.

    Captures the relative phase offset between two layers and its
    stability over time.  Structural data only — no interpretation.
    """
    ratio_a: int
    ratio_b: int
    phase_offset: float         # in [0, 1)
    stability_score: float

    def to_dict(self) -> dict:
        return {
            "ratio_a": self.ratio_a,
            "ratio_b": self.ratio_b,
            "phase_offset": round(self.phase_offset, 4),
            "stability_score": round(self.stability_score, 4),
        }


@dataclass
class RhythmGraph:
    """Complete rhythm subdivision graph for a track.

    Contains the pulse period, all persistent subdivision layers,
    and pairwise phase relationships between layers.
    """
    pulse_period: float
    layers: List[SubdivisionLayer] = field(default_factory=list)
    phase_relations: List[PhaseRelation] = field(default_factory=list)
    total_beats: int = 0

    def to_dict(self) -> dict:
        return {
            "pulse_period": round(self.pulse_period, 6),
            "layers": [layer.to_dict() for layer in self.layers],
            "phase_relations": [pr.to_dict() for pr in self.phase_relations],
            "total_beats": self.total_beats,
        }


# ---------------------------------------------------------------------------
# Internal: per-window subdivision candidate
# ---------------------------------------------------------------------------

@dataclass
class _WindowCandidate:
    """Transient subdivision candidate from a single window."""
    ratio: int
    confidence: float
    phase: float                # in [0, 1)


# ---------------------------------------------------------------------------
# Internal: persistent layer tracker state
# ---------------------------------------------------------------------------

@dataclass
class _TrackedLayer:
    """Internal mutable tracking state for a subdivision layer."""
    ratio: int
    confidence_ema: float
    phase_ema: float            # in [0, 1)
    first_seen_beat: int
    last_seen_beat: int
    persistence: float
    observed_this_window: bool = False


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class PersistentSubdivisionGraphBuilder:
    """Build a persistent multi-layer subdivision graph from onset data.

    Uses beat-aligned adaptive windows (configurable beat count,
    sliding by 1 beat) to extract subdivision candidates, then tracks
    layer persistence and phase relationships across the full track.

    Parameters
    ----------
    window_beats : int
        Number of beats per analysis window (default 8).
    candidate_ratios : tuple[int, ...]
        Subdivision ratios to evaluate.
    alignment_tolerance : float
        Tolerance in seconds for alignment error scoring.
    """

    def __init__(
        self,
        window_beats: int = DEFAULT_WINDOW_BEATS,
        candidate_ratios: Tuple[int, ...] = CANDIDATE_RATIOS,
        alignment_tolerance: float = ALIGNMENT_TOLERANCE_SECONDS,
    ) -> None:
        self.window_beats = window_beats
        self.candidate_ratios = candidate_ratios
        self.alignment_tolerance = alignment_tolerance

    def build(
        self,
        onset_times: np.ndarray,
        onset_strengths: np.ndarray,
        beat_times: np.ndarray,
        downbeat_times: np.ndarray,
    ) -> RhythmGraph:
        """Build the subdivision graph from onset and beat data.

        Parameters
        ----------
        onset_times : np.ndarray
            Onset timestamps in seconds.
        onset_strengths : np.ndarray
            Per-onset strength/velocity values.
        beat_times : np.ndarray
            Beat timestamps in seconds (from beat tracker).
        downbeat_times : np.ndarray
            Downbeat timestamps in seconds.

        Returns
        -------
        RhythmGraph
            Complete subdivision graph with persistent layers and
            phase relationships.
        """
        onset_times = np.asarray(onset_times, dtype=np.float64)
        onset_strengths = np.asarray(onset_strengths, dtype=np.float64)
        beat_times = np.asarray(beat_times, dtype=np.float64)
        downbeat_times = np.asarray(downbeat_times, dtype=np.float64)

        total_beats = len(beat_times)

        if total_beats < self.window_beats + 1:
            # Not enough beats for even one window
            pulse = float(np.median(np.diff(beat_times))) if total_beats > 1 else 0.5
            return RhythmGraph(
                pulse_period=pulse,
                total_beats=total_beats,
            )

        # Global pulse period (median of all beat intervals)
        beat_intervals = np.diff(beat_times)
        global_pulse = float(np.median(beat_intervals))

        # ----- Phase 1: Per-window candidate extraction -----
        tracked_layers: Dict[Tuple[int, int], _TrackedLayer] = {}
        # Key: (ratio, phase_bucket) where phase_bucket = int(phase * 100)
        # This allows merging layers with similar phase.

        n_windows = total_beats - self.window_beats
        logger.debug(
            f"[subdivision_graph] {n_windows} beat-aligned windows, "
            f"{total_beats} beats, pulse={global_pulse:.4f}s"
        )

        for w_start_beat in range(n_windows):
            w_end_beat = w_start_beat + self.window_beats
            t_start = beat_times[w_start_beat]
            t_end = beat_times[w_end_beat]

            # Local beat period for this window
            local_intervals = beat_intervals[w_start_beat:w_end_beat]
            local_pulse = float(np.mean(local_intervals))

            if local_pulse <= 0:
                continue

            # Filter onsets to this window
            mask = (onset_times >= t_start) & (onset_times < t_end)
            w_onsets = onset_times[mask]
            w_strengths = onset_strengths[mask]

            if len(w_onsets) < MIN_ONSETS_PER_WINDOW:
                # Still decay tracked layers
                self._decay_unobserved(tracked_layers)
                continue

            # Extract candidates for this window
            candidates = self._extract_candidates(
                w_onsets, w_strengths, beat_times[w_start_beat:w_end_beat + 1],
                local_pulse,
            )

            # Update tracked layers
            self._update_tracked_layers(
                tracked_layers, candidates,
                w_start_beat, w_end_beat,
            )

        # ----- Phase 2: Finalise persistent layers -----
        layers = self._finalise_layers(tracked_layers)

        # ----- Phase 3: Phase relationship tracking -----
        phase_relations = self._compute_phase_relations(layers)

        logger.info(
            f"[subdivision_graph] Built graph: {len(layers)} layers, "
            f"{len(phase_relations)} phase relations, "
            f"{total_beats} beats"
        )

        return RhythmGraph(
            pulse_period=global_pulse,
            layers=layers,
            phase_relations=phase_relations,
            total_beats=total_beats,
        )

    # ------------------------------------------------------------------
    # Internal: candidate extraction per window
    # ------------------------------------------------------------------

    def _extract_candidates(
        self,
        onset_times: np.ndarray,
        onset_strengths: np.ndarray,
        window_beat_times: np.ndarray,
        local_pulse: float,
    ) -> List[_WindowCandidate]:
        """Extract subdivision candidates from a single beat-aligned window.

        For each candidate ratio r, builds a subdivision grid of r
        subdivisions per beat, measures alignment error of each onset
        to the nearest grid point, and computes a confidence score.

        Parameters
        ----------
        onset_times : np.ndarray
            Onset timestamps within the window.
        onset_strengths : np.ndarray
            Corresponding strength values.
        window_beat_times : np.ndarray
            Beat timestamps bounding the window (N+1 values for N beats).
        local_pulse : float
            Mean beat period in this window.

        Returns
        -------
        list[_WindowCandidate]
            Candidates with confidence > 0 for this window.
        """
        candidates: List[_WindowCandidate] = []
        t_start = window_beat_times[0]
        n_beats = len(window_beat_times) - 1

        for ratio in self.candidate_ratios:
            # Build subdivision grid: for each beat interval, place r
            # equally spaced grid points.
            grid_points: List[float] = []
            for b_idx in range(n_beats):
                b_start = window_beat_times[b_idx]
                b_end = window_beat_times[b_idx + 1]
                b_dur = b_end - b_start
                if b_dur <= 0:
                    continue
                sub_dur = b_dur / ratio
                for s in range(ratio):
                    grid_points.append(b_start + s * sub_dur)

            if len(grid_points) == 0:
                continue

            grid = np.array(grid_points, dtype=np.float64)

            # For each onset, find distance to nearest grid point
            # Vectorised: |onset - nearest_grid|
            errors = np.empty(len(onset_times), dtype=np.float64)
            for i, t in enumerate(onset_times):
                diffs = np.abs(grid - t)
                errors[i] = float(np.min(diffs))

            # Weighted mean alignment error (weight by onset strength)
            total_strength = float(np.sum(onset_strengths))
            if total_strength > 0:
                weighted_error = float(
                    np.sum(errors * onset_strengths) / total_strength
                )
            else:
                weighted_error = float(np.mean(errors))

            # Alignment confidence (precision): how close onsets are
            # to their nearest grid point.
            alignment_conf = float(
                np.exp(-weighted_error / self.alignment_tolerance)
            )

            # Grid completeness (recall): what fraction of grid points
            # have at least one onset within tolerance.  Prevents
            # higher ratios from scoring well when the grid is sparse.
            if len(onset_times) > 0:
                # For each grid point, distance to nearest onset
                grid_errors = np.empty(len(grid), dtype=np.float64)
                for g_idx, g_t in enumerate(grid):
                    grid_errors[g_idx] = float(np.min(np.abs(onset_times - g_t)))
                covered = float(np.sum(grid_errors < self.alignment_tolerance * 3))
                completeness = covered / len(grid)
            else:
                completeness = 0.0

            # Combined confidence: geometric mean of precision & recall
            confidence = float(np.sqrt(alignment_conf * completeness))

            if confidence < 0.01:
                continue

            # Phase offset: for each onset, compute the signed offset
            # from its nearest grid point, normalised to [0, 1) of a
            # subdivision cell.  This is far more stable than computing
            # (onset - window_start) % sub_dur, which is noisy near the
            # 0/1 boundary for well-aligned onsets.
            sub_dur = local_pulse / ratio
            if sub_dur > 0 and len(grid) > 0:
                onset_phases = np.empty(len(onset_times), dtype=np.float64)
                for i, t in enumerate(onset_times):
                    nearest_idx = int(np.argmin(np.abs(grid - t)))
                    offset = t - grid[nearest_idx]
                    onset_phases[i] = (offset / sub_dur) % 1.0
                # Circular mean of phases
                angles = onset_phases * 2.0 * np.pi
                phase = float(
                    np.arctan2(np.mean(np.sin(angles)),
                               np.mean(np.cos(angles)))
                    / (2.0 * np.pi)
                ) % 1.0
            else:
                phase = 0.0

            candidates.append(_WindowCandidate(
                ratio=ratio,
                confidence=confidence,
                phase=phase,
            ))

        return candidates

    # ------------------------------------------------------------------
    # Internal: layer tracking
    # ------------------------------------------------------------------

    def _phase_bucket(self, ratio: int, phase: float) -> int:
        """Quantise phase to a bucket for layer identity matching.

        Layers with the same ratio and nearby phase (within
        PHASE_MERGE_TOLERANCE) should map to the same bucket.
        """
        # Bucket size = PHASE_MERGE_TOLERANCE (in phase units)
        bucket_size = PHASE_MERGE_TOLERANCE
        return int(phase / bucket_size)

    def _find_matching_layer(
        self,
        tracked: Dict[Tuple[int, int], _TrackedLayer],
        ratio: int,
        phase: float,
    ) -> Optional[Tuple[int, int]]:
        """Find existing tracked layer matching this ratio and phase."""
        bucket = self._phase_bucket(ratio, phase)
        max_bucket = int(1.0 / PHASE_MERGE_TOLERANCE)  # e.g. 10

        # Check exact bucket, neighbours, and wrap-around neighbours
        candidates_buckets = {bucket, bucket - 1, bucket + 1}
        # Wrap-around: bucket 0 ↔ bucket (max_bucket - 1)
        if bucket == 0:
            candidates_buckets.add(max_bucket - 1)
        elif bucket == max_bucket - 1:
            candidates_buckets.add(0)

        for b in candidates_buckets:
            key = (ratio, b)
            if key in tracked:
                layer = tracked[key]
                # Verify phase is actually close (circular distance)
                phase_diff = abs(phase - layer.phase_ema)
                # Handle wrap-around
                phase_diff = min(phase_diff, 1.0 - phase_diff)
                if phase_diff < PHASE_MERGE_TOLERANCE:
                    return key
                # Handle wrap-around
                phase_diff = min(phase_diff, 1.0 - phase_diff)
                if phase_diff < PHASE_MERGE_TOLERANCE:
                    return key

        return None

    def _update_tracked_layers(
        self,
        tracked: Dict[Tuple[int, int], _TrackedLayer],
        candidates: List[_WindowCandidate],
        w_start_beat: int,
        w_end_beat: int,
    ) -> None:
        """Update tracked layers with candidates from the current window.

        1. Mark all layers as unobserved.
        2. For each candidate, find or create a matching layer.
        3. Apply EMA smoothing to confidence and phase.
        4. Decay unobserved layers.
        5. Prune dead layers.
        """
        # Mark all as unobserved
        for layer in tracked.values():
            layer.observed_this_window = False

        # Update from candidates
        for cand in candidates:
            key = self._find_matching_layer(tracked, cand.ratio, cand.phase)

            if key is not None:
                layer = tracked[key]
                # EMA update confidence
                layer.confidence_ema = (
                    PERSISTENCE_ALPHA * cand.confidence
                    + (1.0 - PERSISTENCE_ALPHA) * layer.confidence_ema
                )
                # EMA update phase (handling wrap-around)
                layer.phase_ema = _phase_ema(
                    layer.phase_ema, cand.phase, PHASE_STABILITY_ALPHA,
                )
                layer.last_seen_beat = w_end_beat
                layer.persistence += cand.confidence
                layer.observed_this_window = True
            else:
                # Create new tracked layer
                bucket = self._phase_bucket(cand.ratio, cand.phase)
                new_key = (cand.ratio, bucket)
                # Avoid collision
                while new_key in tracked:
                    bucket += 1
                    new_key = (cand.ratio, bucket)
                tracked[new_key] = _TrackedLayer(
                    ratio=cand.ratio,
                    confidence_ema=cand.confidence,
                    phase_ema=cand.phase,
                    first_seen_beat=w_start_beat,
                    last_seen_beat=w_end_beat,
                    persistence=cand.confidence,
                    observed_this_window=True,
                )

        # Decay unobserved and prune
        self._decay_unobserved(tracked)

    def _decay_unobserved(
        self,
        tracked: Dict[Tuple[int, int], _TrackedLayer],
    ) -> None:
        """Decay unobserved layers and prune dead ones."""
        dead_keys: List[Tuple[int, int]] = []
        for key, layer in tracked.items():
            if not layer.observed_this_window:
                layer.confidence_ema *= PERSISTENCE_DECAY
                layer.persistence *= PERSISTENCE_DECAY
                if layer.confidence_ema < PERSISTENCE_FLOOR:
                    dead_keys.append(key)
        for key in dead_keys:
            del tracked[key]

    # ------------------------------------------------------------------
    # Internal: finalise layers
    # ------------------------------------------------------------------

    def _finalise_layers(
        self,
        tracked: Dict[Tuple[int, int], _TrackedLayer],
    ) -> List[SubdivisionLayer]:
        """Convert tracked layers into output SubdivisionLayer objects.

        Merges any remaining same-ratio layers that ended up close in
        phase, sorts by persistence descending.
        """
        # Group by ratio for potential merging
        by_ratio: Dict[int, List[_TrackedLayer]] = {}
        for layer in tracked.values():
            by_ratio.setdefault(layer.ratio, []).append(layer)

        result: List[SubdivisionLayer] = []

        for ratio, group in by_ratio.items():
            # Sort by persistence descending
            group.sort(key=lambda l: l.persistence, reverse=True)

            # Merge layers with similar phase
            merged: List[_TrackedLayer] = []
            for layer in group:
                found = False
                for m in merged:
                    phase_diff = abs(layer.phase_ema - m.phase_ema)
                    phase_diff = min(phase_diff, 1.0 - phase_diff)
                    if phase_diff < PHASE_MERGE_TOLERANCE:
                        # Merge: weighted average
                        total_p = m.persistence + layer.persistence
                        if total_p > 0:
                            w_m = m.persistence / total_p
                            w_l = layer.persistence / total_p
                            m.confidence_ema = (
                                w_m * m.confidence_ema
                                + w_l * layer.confidence_ema
                            )
                            m.phase_ema = _phase_weighted_mean(
                                m.phase_ema, w_m,
                                layer.phase_ema, w_l,
                            )
                        m.persistence += layer.persistence
                        m.first_seen_beat = min(
                            m.first_seen_beat, layer.first_seen_beat,
                        )
                        m.last_seen_beat = max(
                            m.last_seen_beat, layer.last_seen_beat,
                        )
                        found = True
                        break
                if not found:
                    merged.append(layer)

            for m in merged:
                result.append(SubdivisionLayer(
                    ratio=m.ratio,
                    avg_confidence=m.confidence_ema,
                    phase=m.phase_ema % 1.0,
                    first_seen_beat=m.first_seen_beat,
                    last_seen_beat=m.last_seen_beat,
                    persistence_score=m.persistence,
                ))

        # Sort by persistence descending
        result.sort(key=lambda l: l.persistence_score, reverse=True)
        return result

    # ------------------------------------------------------------------
    # Internal: phase relationships
    # ------------------------------------------------------------------

    def _compute_phase_relations(
        self,
        layers: List[SubdivisionLayer],
    ) -> List[PhaseRelation]:
        """Compute pairwise phase relationships between persistent layers.

        For each pair of layers with different ratios, computes the
        relative phase offset and a stability score based on how
        persistent both layers are.
        """
        relations: List[PhaseRelation] = []

        for i in range(len(layers)):
            for j in range(i + 1, len(layers)):
                a = layers[i]
                b = layers[j]

                # Skip same-ratio pairs (these are identical subdivision
                # grids at different phases — not a structural relation)
                if a.ratio == b.ratio:
                    continue

                # Relative phase offset: expressed in terms of the finer
                # grid (higher ratio).
                phase_offset = abs(a.phase - b.phase) % 1.0

                # Stability = geometric mean of persistence scores,
                # normalised to [0, 1] range.
                stability = float(np.sqrt(
                    min(a.persistence_score, 1.0)
                    * min(b.persistence_score, 1.0)
                ))

                relations.append(PhaseRelation(
                    ratio_a=a.ratio,
                    ratio_b=b.ratio,
                    phase_offset=phase_offset,
                    stability_score=stability,
                ))

        # Sort by stability descending
        relations.sort(key=lambda r: r.stability_score, reverse=True)
        return relations


# ---------------------------------------------------------------------------
# Utility: circular phase math
# ---------------------------------------------------------------------------

def _phase_ema(
    prev: float, current: float, alpha: float,
) -> float:
    """Exponential moving average for circular phase values in [0, 1).

    Handles wrap-around by computing the shortest-arc interpolation.
    """
    diff = current - prev
    # Wrap to [-0.5, 0.5)
    if diff > 0.5:
        diff -= 1.0
    elif diff < -0.5:
        diff += 1.0

    result = prev + alpha * diff
    return result % 1.0


def _phase_weighted_mean(
    phase_a: float, weight_a: float,
    phase_b: float, weight_b: float,
) -> float:
    """Weighted mean of two circular phase values in [0, 1).

    Uses the unit-circle embedding to handle wrap-around correctly.
    """
    total = weight_a + weight_b
    if total <= 0:
        return 0.0

    # Convert to unit circle
    angle_a = phase_a * 2.0 * np.pi
    angle_b = phase_b * 2.0 * np.pi

    x = weight_a * np.cos(angle_a) + weight_b * np.cos(angle_b)
    y = weight_a * np.sin(angle_a) + weight_b * np.sin(angle_b)

    result = float(np.arctan2(y, x) / (2.0 * np.pi)) % 1.0
    return result
