"""
Evaluation Metrics — Structured comparison of inference vs ground truth.

All metrics are deterministic, side-effect free, and computed from
the immutable outputs of the inference engine and the parsed ground
truth.

Metric definitions
~~~~~~~~~~~~~~~~~~

A) **Meter accuracy** — For each inference window, determine the ground
   truth meter at the window midpoint.  If the dominant hypothesis's
   ``beat_count`` matches the ground truth numerator → 1.0 (correct).
   If any competing hypothesis matches → 0.5 (partial credit).
   Otherwise → 0.0.  Final score = mean across windows.

B) **Grouping accuracy** — Same window alignment, but comparing
   ``grouping_vector`` exactly to ground truth grouping.  Only computed
   for segments where grouping is defined in the ground truth.

C) **Modulation precision / recall / timing error** —
   A detected modulation is a *true positive* if there exists a ground
   truth modulation within ±2 seconds.
     - Precision = TP / total_detected
     - Recall    = TP / total_ground_truth
     - Timing error = mean |t_detected − t_gt| for matched pairs (ms).

D) **Polyrhythm recall** — For each ground truth polyrhythm segment,
   check whether the engine detected persistent polyrhythmic layers
   overlapping that segment.  Binary per segment; score = mean.

E) **Ambiguity alignment** — For windows whose ground truth segment is
   marked ``is_ambiguous``, check whether the engine also flagged
   ``ambiguity_flag``.  Score = agreement rate.

F) **Confidence calibration** — Bin windows by confidence [0.0–0.1,
   0.1–0.2, …, 0.9–1.0].  For each bin, compute the actual meter
   accuracy.  Returns a dict mapping bin midpoint to empirical accuracy.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from engine.evaluation.ground_truth import GroundTruth, MeterSegment
from engine.stages.metrical_inference import (
    InferenceResult,
    MeterHypothesis,
    WindowInferenceResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODULATION_TOLERANCE_SEC: float = 2.0
"""Maximum temporal distance (seconds) for modulation matching."""

CONFIDENCE_BIN_COUNT: int = 10
"""Number of bins for calibration curve (0.0–1.0 in 0.1 steps)."""

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EvaluationMetrics:
    """Complete evaluation result for one song.

    All scores in [0, 1] unless otherwise noted.
    """
    song_id: str = ""
    meter_accuracy: float = 0.0
    grouping_accuracy: float = 0.0
    modulation_precision: float = 0.0
    modulation_recall: float = 0.0
    modulation_timing_error_ms: float = 0.0
    polyrhythm_recall: float = 0.0
    ambiguity_alignment: float = 0.0
    confidence_calibration_curve: Dict[float, float] = field(
        default_factory=dict,
    )
    num_windows: int = 0
    num_windows_with_grouping_gt: int = 0
    num_gt_modulations: int = 0
    num_detected_modulations: int = 0
    num_tp_modulations: int = 0
    num_gt_polyrhythm_segments: int = 0
    num_detected_polyrhythm_layers: int = 0
    num_ambiguous_windows: int = 0

    def to_dict(self) -> dict:
        return {
            "song_id": self.song_id,
            "meter_accuracy": round(self.meter_accuracy, 4),
            "grouping_accuracy": round(self.grouping_accuracy, 4),
            "modulation_precision": round(self.modulation_precision, 4),
            "modulation_recall": round(self.modulation_recall, 4),
            "modulation_timing_error_ms": round(
                self.modulation_timing_error_ms, 1,
            ),
            "polyrhythm_recall": round(self.polyrhythm_recall, 4),
            "ambiguity_alignment": round(self.ambiguity_alignment, 4),
            "confidence_calibration_curve": {
                str(k): round(v, 4)
                for k, v in self.confidence_calibration_curve.items()
            },
            "num_windows": self.num_windows,
            "num_gt_modulations": self.num_gt_modulations,
            "num_detected_modulations": self.num_detected_modulations,
            "num_tp_modulations": self.num_tp_modulations,
        }

    def summary_string(self) -> str:
        """Human-readable evaluation summary."""
        lines = [
            f"Song: {self.song_id}",
            f"Meter Accuracy: {self.meter_accuracy:.2f}",
            f"Grouping Accuracy: {self.grouping_accuracy:.2f}",
            f"Modulation Precision: {self.modulation_precision:.2f}",
            f"Modulation Recall: {self.modulation_recall:.2f}",
            f"Avg Modulation Timing Error: "
            f"{self.modulation_timing_error_ms:.0f} ms",
            f"Polyrhythm Recall: {self.polyrhythm_recall:.2f}",
            f"Ambiguity Alignment: {self.ambiguity_alignment:.2f}",
        ]
        return "\n".join(lines)


@dataclass
class CorpusMetrics:
    """Aggregated evaluation over a corpus of songs."""
    num_songs: int = 0
    mean_meter_accuracy: float = 0.0
    mean_grouping_accuracy: float = 0.0
    overall_modulation_precision: float = 0.0
    overall_modulation_recall: float = 0.0
    mean_modulation_timing_error_ms: float = 0.0
    mean_polyrhythm_recall: float = 0.0
    mean_ambiguity_alignment: float = 0.0
    aggregated_calibration: Dict[float, float] = field(default_factory=dict)
    per_song: List[EvaluationMetrics] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "num_songs": self.num_songs,
            "mean_meter_accuracy": round(self.mean_meter_accuracy, 4),
            "mean_grouping_accuracy": round(self.mean_grouping_accuracy, 4),
            "overall_modulation_precision": round(
                self.overall_modulation_precision, 4,
            ),
            "overall_modulation_recall": round(
                self.overall_modulation_recall, 4,
            ),
            "mean_modulation_timing_error_ms": round(
                self.mean_modulation_timing_error_ms, 1,
            ),
            "mean_polyrhythm_recall": round(
                self.mean_polyrhythm_recall, 4,
            ),
            "mean_ambiguity_alignment": round(
                self.mean_ambiguity_alignment, 4,
            ),
            "aggregated_calibration": {
                str(k): round(v, 4)
                for k, v in self.aggregated_calibration.items()
            },
            "per_song": [s.to_dict() for s in self.per_song],
        }

    def summary_string(self) -> str:
        lines = [
            f"=== Corpus Evaluation ({self.num_songs} songs) ===",
            f"Mean Meter Accuracy:       {self.mean_meter_accuracy:.2f}",
            f"Mean Grouping Accuracy:    {self.mean_grouping_accuracy:.2f}",
            f"Modulation Precision:      {self.overall_modulation_precision:.2f}",
            f"Modulation Recall:         {self.overall_modulation_recall:.2f}",
            f"Avg Timing Error:          "
            f"{self.mean_modulation_timing_error_ms:.0f} ms",
            f"Mean Polyrhythm Recall:    {self.mean_polyrhythm_recall:.2f}",
            f"Mean Ambiguity Alignment:  {self.mean_ambiguity_alignment:.2f}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core metric computations
# ---------------------------------------------------------------------------


def compute_metrics(
    inference: InferenceResult,
    ground_truth: GroundTruth,
) -> EvaluationMetrics:
    """Compute all evaluation metrics for one song.

    Parameters
    ----------
    inference : InferenceResult
        Output of ``run_metrical_inference()``.
    ground_truth : GroundTruth
        Parsed ground truth from ``load_ground_truth()`` or
        ``parse_ground_truth()``.

    Returns
    -------
    EvaluationMetrics
        Fully populated metrics object.

    Time complexity
    ---------------
    O(W × log(S) + D × G + P × R) where:
      W = inference windows, S = ground truth segments,
      D = detected modulations, G = ground truth modulations,
      P = polyrhythm segments, R = detected polyrhythm layers.
    Typically O(W) dominates.

    Side effects: None.  Pure function.
    """
    windows = inference.window_inferences

    # --- Meter & grouping accuracy ---
    meter_scores: List[float] = []
    grouping_scores: List[float] = []
    # For calibration
    confidence_correctness: List[Tuple[float, float]] = []

    # For ambiguity
    ambiguity_total = 0
    ambiguity_correct = 0

    for win in windows:
        mid_time = (win.start_time + win.end_time) / 2.0
        gt_seg = ground_truth.meter_at_time(mid_time)

        if gt_seg is None:
            continue

        # Meter accuracy
        meter_score = _meter_match_score(
            win, gt_seg.numerator, gt_seg.denominator,
        )
        meter_scores.append(meter_score)

        # Confidence + correctness for calibration
        conf = (
            win.dominant_hypothesis.confidence
            if win.dominant_hypothesis
            else 0.0
        )
        confidence_correctness.append((conf, meter_score))

        # Grouping accuracy (only if GT provides grouping)
        if gt_seg.grouping is not None:
            grp_score = _grouping_match_score(win, gt_seg.grouping)
            grouping_scores.append(grp_score)

        # Ambiguity alignment
        if gt_seg.is_ambiguous:
            ambiguity_total += 1
            if win.ambiguity_flag:
                ambiguity_correct += 1

    meter_accuracy = _safe_mean(meter_scores)
    grouping_accuracy = _safe_mean(grouping_scores)
    ambiguity_alignment = (
        ambiguity_correct / ambiguity_total
        if ambiguity_total > 0
        else 1.0  # no ambiguous segments → perfect by default
    )

    # --- Modulation metrics ---
    mod_precision, mod_recall, mod_timing = _compute_modulation_metrics(
        detected=inference.detected_modulations,
        ground_truth_mods=ground_truth.modulations,
    )

    # --- Polyrhythm recall ---
    poly_recall = _compute_polyrhythm_recall(
        detected_layers=inference.persistent_polyrhythms,
        gt_segments=ground_truth.polyrhythm_segments,
    )

    # --- Confidence calibration ---
    calibration = _compute_calibration_curve(confidence_correctness)

    # Count TPs for reporting
    num_tp = _count_modulation_tps(
        detected=inference.detected_modulations,
        ground_truth_mods=ground_truth.modulations,
    )

    return EvaluationMetrics(
        song_id=ground_truth.song_id,
        meter_accuracy=meter_accuracy,
        grouping_accuracy=grouping_accuracy,
        modulation_precision=mod_precision,
        modulation_recall=mod_recall,
        modulation_timing_error_ms=mod_timing,
        polyrhythm_recall=poly_recall,
        ambiguity_alignment=ambiguity_alignment,
        confidence_calibration_curve=calibration,
        num_windows=len(windows),
        num_windows_with_grouping_gt=len(grouping_scores),
        num_gt_modulations=len(ground_truth.modulations),
        num_detected_modulations=len(inference.detected_modulations),
        num_tp_modulations=num_tp,
        num_gt_polyrhythm_segments=len(ground_truth.polyrhythm_segments),
        num_detected_polyrhythm_layers=len(inference.persistent_polyrhythms),
        num_ambiguous_windows=ambiguity_total,
    )


def aggregate_corpus_metrics(
    per_song: List[EvaluationMetrics],
) -> CorpusMetrics:
    """Aggregate per-song metrics into a corpus summary.

    Parameters
    ----------
    per_song : list[EvaluationMetrics]
        One ``EvaluationMetrics`` per song.

    Returns
    -------
    CorpusMetrics
        Aggregated summary.

    Time complexity: O(S × B) where S = songs, B = calibration bins.
    """
    if not per_song:
        return CorpusMetrics()

    n = len(per_song)

    # Micro-averaged modulation metrics
    total_detected = sum(s.num_detected_modulations for s in per_song)
    total_gt = sum(s.num_gt_modulations for s in per_song)
    total_tp = sum(s.num_tp_modulations for s in per_song)

    overall_precision = total_tp / total_detected if total_detected > 0 else 1.0
    overall_recall = total_tp / total_gt if total_gt > 0 else 1.0

    # Timing errors (weighted by TP count)
    timing_errors = [
        s.modulation_timing_error_ms
        for s in per_song
        if s.num_tp_modulations > 0
    ]
    mean_timing = (
        sum(
            s.modulation_timing_error_ms * s.num_tp_modulations
            for s in per_song
            if s.num_tp_modulations > 0
        )
        / total_tp
        if total_tp > 0
        else 0.0
    )

    # Aggregate calibration: merge all bins
    agg_cal: Dict[float, List[float]] = {}
    for s in per_song:
        for bin_mid, acc in s.confidence_calibration_curve.items():
            agg_cal.setdefault(bin_mid, []).append(acc)
    aggregated_calibration = {
        k: sum(vs) / len(vs) for k, vs in sorted(agg_cal.items())
    }

    return CorpusMetrics(
        num_songs=n,
        mean_meter_accuracy=sum(s.meter_accuracy for s in per_song) / n,
        mean_grouping_accuracy=sum(s.grouping_accuracy for s in per_song) / n,
        overall_modulation_precision=overall_precision,
        overall_modulation_recall=overall_recall,
        mean_modulation_timing_error_ms=mean_timing,
        mean_polyrhythm_recall=sum(s.polyrhythm_recall for s in per_song) / n,
        mean_ambiguity_alignment=sum(
            s.ambiguity_alignment for s in per_song
        ) / n,
        aggregated_calibration=aggregated_calibration,
        per_song=per_song,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _meter_match_score(
    win: WindowInferenceResult,
    gt_numerator: int,
    gt_denominator: int,
) -> float:
    """Score a single window's meter accuracy against ground truth.

    Returns
    -------
    float
        1.0 if dominant matches, 0.5 if a competing hypothesis matches,
        0.0 otherwise.

    How matching works
    ------------------
    A hypothesis "matches" the ground truth meter if its ``beat_count``
    equals the ground truth numerator.  We do NOT compare the denominator
    because the inference engine works with periodicity (seconds), not
    note values.  The denominator is implicit in the beat period.

    Partial credit rationale
    ------------------------
    If the engine preserved the correct answer among competing hypotheses,
    it demonstrates sensitivity to the meter — it just didn't rank it
    highest.  This is better than missing it entirely.

    Time complexity: O(C) where C = competing hypotheses (≤ 5).
    """
    if win.dominant_hypothesis is not None:
        if win.dominant_hypothesis.beat_count == gt_numerator:
            return 1.0

    for h in win.competing_hypotheses:
        if h.beat_count == gt_numerator:
            return 0.5

    return 0.0


def _grouping_match_score(
    win: WindowInferenceResult,
    gt_grouping: List[int],
) -> float:
    """Score a single window's grouping accuracy.

    Returns 1.0 for exact match of dominant hypothesis grouping_vector
    to ground truth grouping, 0.0 otherwise.

    Exact match is required because grouping carries musical meaning:
    [2,2,3] and [3,2,2] are distinct feels.

    Time complexity: O(G) where G = grouping length (≤ 16).
    """
    if win.dominant_hypothesis is None:
        return 0.0
    return 1.0 if win.dominant_hypothesis.grouping_vector == gt_grouping else 0.0


def _compute_modulation_metrics(
    detected: list,
    ground_truth_mods: list,
) -> Tuple[float, float, float]:
    """Compute modulation precision, recall, and timing error.

    A detected modulation is a true positive if there exists a ground
    truth modulation within ±``MODULATION_TOLERANCE_SEC``.  Each ground
    truth modulation can only be matched once (greedy nearest-first).

    Parameters
    ----------
    detected : list[ModulationEvent]
        From inference result.
    ground_truth_mods : list[GroundTruthModulation]
        From ground truth.

    Returns
    -------
    (precision, recall, avg_timing_error_ms)

    Time complexity: O(D × G) where D = detected, G = ground truth.
    With typical D, G < 20: negligible.
    """
    if len(detected) == 0 and len(ground_truth_mods) == 0:
        return 1.0, 1.0, 0.0

    if len(detected) == 0:
        return 1.0, 0.0, 0.0  # precision 1.0 by convention (nothing wrong)

    if len(ground_truth_mods) == 0:
        return 0.0, 1.0, 0.0  # all detections are false positives

    # Greedy matching: for each detected, find nearest unmatched GT
    gt_matched = [False] * len(ground_truth_mods)
    tp = 0
    timing_errors: List[float] = []

    for det in detected:
        best_idx = -1
        best_dist = float("inf")
        for gi, gt_mod in enumerate(ground_truth_mods):
            if gt_matched[gi]:
                continue
            dist = abs(det.time - gt_mod.time)
            if dist < best_dist:
                best_dist = dist
                best_idx = gi

        if best_idx >= 0 and best_dist <= MODULATION_TOLERANCE_SEC:
            gt_matched[best_idx] = True
            tp += 1
            timing_errors.append(best_dist * 1000.0)  # convert to ms

    precision = tp / len(detected) if len(detected) > 0 else 1.0
    recall = tp / len(ground_truth_mods) if len(ground_truth_mods) > 0 else 1.0
    avg_timing = sum(timing_errors) / len(timing_errors) if timing_errors else 0.0

    return precision, recall, avg_timing


def _count_modulation_tps(
    detected: list,
    ground_truth_mods: list,
) -> int:
    """Count true positive modulations (for corpus aggregation)."""
    if not detected or not ground_truth_mods:
        return 0

    gt_matched = [False] * len(ground_truth_mods)
    tp = 0
    for det in detected:
        best_idx = -1
        best_dist = float("inf")
        for gi, gt_mod in enumerate(ground_truth_mods):
            if gt_matched[gi]:
                continue
            dist = abs(det.time - gt_mod.time)
            if dist < best_dist:
                best_dist = dist
                best_idx = gi
        if best_idx >= 0 and best_dist <= MODULATION_TOLERANCE_SEC:
            gt_matched[best_idx] = True
            tp += 1
    return tp


def _compute_polyrhythm_recall(
    detected_layers: list,
    gt_segments: list,
) -> float:
    """Compute polyrhythm recall.

    For each ground truth polyrhythm segment, check whether any detected
    polyrhythm layer temporally overlaps it.  Binary match per segment.

    Parameters
    ----------
    detected_layers : list[PolyrhythmLayer]
    gt_segments : list[PolyrhythmSegment]

    Returns
    -------
    float
        Fraction of GT polyrhythm segments matched.  1.0 if no GT
        segments exist.

    Time complexity: O(G × D) where G = GT segments, D = detected layers.
    """
    if len(gt_segments) == 0:
        return 1.0  # nothing to recall

    matched = 0
    for gt_seg in gt_segments:
        for layer in detected_layers:
            # Temporal overlap check
            if (
                layer.first_window_time < gt_seg.end_time
                and layer.last_window_time > gt_seg.start_time
            ):
                matched += 1
                break

    return matched / len(gt_segments)


def _compute_calibration_curve(
    confidence_correctness: List[Tuple[float, float]],
) -> Dict[float, float]:
    """Bin confidence values and compute empirical accuracy per bin.

    Parameters
    ----------
    confidence_correctness : list[(confidence, meter_score)]
        One entry per inference window.

    Returns
    -------
    dict[float, float]
        Maps bin midpoint (0.05, 0.15, …, 0.95) to empirical meter
        accuracy in that bin.  Empty bins are omitted.

    Time complexity: O(W) where W = number of windows.
    """
    bins: Dict[float, List[float]] = {}
    for i in range(CONFIDENCE_BIN_COUNT):
        midpoint = round(0.05 + i * 0.1, 2)
        bins[midpoint] = []

    for conf, score in confidence_correctness:
        idx = min(int(conf * CONFIDENCE_BIN_COUNT), CONFIDENCE_BIN_COUNT - 1)
        midpoint = round(0.05 + idx * 0.1, 2)
        bins[midpoint].append(score)

    result: Dict[float, float] = {}
    for midpoint, scores in sorted(bins.items()):
        if scores:
            result[midpoint] = sum(scores) / len(scores)

    return result


def _safe_mean(values: List[float]) -> float:
    """Mean that returns 0.0 for empty lists."""
    return sum(values) / len(values) if values else 0.0
