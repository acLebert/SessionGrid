"""
Evaluator — Top-level evaluation pipeline + synthetic test scenarios.

This module provides:

  * ``evaluate_song()``  — metrics for one inference run vs one ground
    truth.
  * ``evaluate_corpus()`` — micro/macro aggregation across songs.
  * Five self-contained test scenarios that exercise the evaluation
    pipeline end-to-end with synthetic data (no audio required).

Design constraints
~~~~~~~~~~~~~~~~~~
*  Evaluation is **side-effect free** — no files written, no globals
   mutated, no network calls.
*  All metrics are **deterministic** — identical inputs produce
   identical outputs.
*  The evaluation module **never modifies** inference results or
   ground truth objects.
"""

import logging
from typing import List, Optional

from engine.evaluation.ground_truth import (
    GroundTruth,
    GroundTruthModulation,
    MeterSegment,
    PolyrhythmSegment,
    TempoSegment,
)
from engine.evaluation.metrics import (
    EvaluationMetrics,
    CorpusMetrics,
    aggregate_corpus_metrics,
    compute_metrics,
)
from engine.stages.metrical_inference import (
    InferenceResult,
    MeterHypothesis,
    ModulationEvent,
    PolyrhythmLayer,
    WindowInferenceResult,
)

logger = logging.getLogger(__name__)


# ===================================================================
# Public API
# ===================================================================


def evaluate_song(
    inference: InferenceResult,
    ground_truth: GroundTruth,
) -> EvaluationMetrics:
    """Evaluate a single song's inference output against ground truth.

    Parameters
    ----------
    inference : InferenceResult
        The immutable output of ``run_metrical_inference()``.
    ground_truth : GroundTruth
        Parsed and validated ground truth from ``load_ground_truth()``
        or ``parse_ground_truth()``.

    Returns
    -------
    EvaluationMetrics
        Fully populated metrics with per-window comparisons.

    Side effects: None.
    """
    metrics = compute_metrics(inference, ground_truth)
    logger.info(
        f"[evaluate_song] {ground_truth.song_id}: "
        f"meter={metrics.meter_accuracy:.3f}, "
        f"grouping={metrics.grouping_accuracy:.3f}, "
        f"mod_prec={metrics.modulation_precision:.3f}, "
        f"mod_rec={metrics.modulation_recall:.3f}"
    )
    return metrics


def evaluate_corpus(
    songs: List[dict],
) -> CorpusMetrics:
    """Evaluate a corpus of (inference, ground_truth) pairs.

    Parameters
    ----------
    songs : list[dict]
        Each entry must have keys ``"inference"`` (InferenceResult)
        and ``"ground_truth"`` (GroundTruth).

    Returns
    -------
    CorpusMetrics
        Aggregated corpus-level metrics with per-song breakdown.
    """
    per_song_metrics: List[EvaluationMetrics] = []
    for entry in songs:
        m = evaluate_song(entry["inference"], entry["ground_truth"])
        per_song_metrics.append(m)

    corpus = aggregate_corpus_metrics(per_song_metrics)
    logger.info(
        f"[evaluate_corpus] {corpus.num_songs} songs — "
        f"mean_meter={corpus.mean_meter_accuracy:.3f}"
    )
    return corpus


# ===================================================================
# Synthetic test helpers
# ===================================================================


def _make_windows(
    duration: float,
    window_sec: float,
    hop_sec: float,
    dominant_fn=None,
    competing_fn=None,
    ambiguity_fn=None,
    modulation_fn=None,
) -> List[WindowInferenceResult]:
    """Generate a sequence of synthetic inference windows.

    ``dominant_fn(start, end)`` → MeterHypothesis or None
    ``competing_fn(start, end)`` → list[MeterHypothesis]
    ``ambiguity_fn(start, end)`` → bool
    ``modulation_fn(start, end)`` → bool
    """
    windows: List[WindowInferenceResult] = []
    t = 0.0
    while t + window_sec <= duration + 1e-6:
        start = t
        end = min(t + window_sec, duration)
        dom = dominant_fn(start, end) if dominant_fn else None
        comp = competing_fn(start, end) if competing_fn else []
        amb = ambiguity_fn(start, end) if ambiguity_fn else False
        mod = modulation_fn(start, end) if modulation_fn else False
        windows.append(WindowInferenceResult(
            start_time=start,
            end_time=end,
            dominant_hypothesis=dom,
            competing_hypotheses=comp,
            ambiguity_flag=amb,
            modulation_flag=mod,
        ))
        t += hop_sec
    return windows


def _hyp(
    beat_count: int,
    grouping: Optional[List[int]] = None,
    confidence: float = 0.85,
    base_period: float = 0.5,
    stability: float = 0.8,
) -> MeterHypothesis:
    """Build a synthetic MeterHypothesis."""
    return MeterHypothesis(
        base_period_seconds=base_period,
        beat_count=beat_count,
        grouping_vector=grouping or [],
        phase_offset=0.0,
        periodicity_strength=0.8,
        accent_alignment_score=0.7,
        prediction_error_score=0.1,
        ioi_consistency_score=0.8,
        structural_repetition_score=0.7,
        harmonic_penalty=0.0,
        stability_score=stability,
        confidence=confidence,
    )


# ===================================================================
# Test 1: Perfect 4/4
# ===================================================================


def test_perfect_4_4() -> EvaluationMetrics:
    """Scenario: Perfect 4/4 rock — engine and ground truth agree.

    Expected: meter_accuracy = 1.0, grouping_accuracy = 1.0,
    ambiguity_alignment = 1.0.

    Duration: 60 s, window = 4 s, hop = 2 s.
    """
    duration = 60.0
    gt = GroundTruth(
        song_id="test_perfect_4_4",
        duration_seconds=duration,
        meter_timeline=[
            MeterSegment(
                start_time=0.0,
                end_time=duration,
                meter="4/4",
                numerator=4,
                denominator=4,
                grouping=[2, 2],
            ),
        ],
        modulations=[],
        tempo_map=[TempoSegment(0.0, duration, 120.0)],
        polyrhythm_segments=[],
    )

    dom_hyp = _hyp(beat_count=4, grouping=[2, 2], confidence=0.92)

    def dominant_fn(start, end):
        return dom_hyp

    windows = _make_windows(duration, 4.0, 2.0, dominant_fn=dominant_fn)

    inference = InferenceResult(
        window_inferences=windows,
        detected_modulations=[],
        persistent_polyrhythms=[],
        global_dominant=dom_hyp,
        duration_seconds=duration,
    )

    return evaluate_song(inference, gt)


# ===================================================================
# Test 2: 7/8 Additive (correct grouping)
# ===================================================================


def test_7_8_additive() -> EvaluationMetrics:
    """Scenario: 7/8 with [2,2,3] grouping — engine matches exactly.

    Expected: meter_accuracy = 1.0, grouping_accuracy = 1.0.

    Duration: 45 s.
    """
    duration = 45.0
    gt = GroundTruth(
        song_id="test_7_8_additive",
        duration_seconds=duration,
        meter_timeline=[
            MeterSegment(
                start_time=0.0,
                end_time=duration,
                meter="7/8",
                numerator=7,
                denominator=8,
                grouping=[2, 2, 3],
            ),
        ],
        modulations=[],
        polyrhythm_segments=[],
    )

    dom_hyp = _hyp(beat_count=7, grouping=[2, 2, 3], confidence=0.88)

    windows = _make_windows(
        duration, 4.0, 2.0,
        dominant_fn=lambda s, e: dom_hyp,
    )

    inference = InferenceResult(
        window_inferences=windows,
        detected_modulations=[],
        persistent_polyrhythms=[],
        global_dominant=dom_hyp,
        duration_seconds=duration,
    )

    return evaluate_song(inference, gt)


# ===================================================================
# Test 3: Known modulation (4/4 → 7/8 at t=30 s)
# ===================================================================


def test_known_modulation() -> EvaluationMetrics:
    """Scenario: Song modulates from 4/4 to 7/8 at t=30 s.
    Engine detects the modulation at t=30.5 s (0.5 s offset).

    Expected: modulation_recall = 1.0, modulation_precision = 1.0,
    modulation_timing_error ≈ 500 ms.

    Duration: 60 s.
    """
    duration = 60.0
    gt = GroundTruth(
        song_id="test_known_modulation",
        duration_seconds=duration,
        meter_timeline=[
            MeterSegment(0.0, 30.0, "4/4", 4, 4, grouping=[2, 2]),
            MeterSegment(30.0, 60.0, "7/8", 7, 8, grouping=[2, 2, 3]),
        ],
        modulations=[
            GroundTruthModulation(30.0, "4/4", "7/8"),
        ],
        polyrhythm_segments=[],
    )

    hyp_4_4 = _hyp(beat_count=4, grouping=[2, 2], confidence=0.90)
    hyp_7_8 = _hyp(beat_count=7, grouping=[2, 2, 3], confidence=0.85)

    def dominant_fn(start, end):
        mid = (start + end) / 2.0
        return hyp_7_8 if mid >= 30.0 else hyp_4_4

    windows = _make_windows(
        duration, 4.0, 2.0,
        dominant_fn=dominant_fn,
    )

    detected_modulation = ModulationEvent(
        time=30.5,
        from_hypothesis=hyp_4_4,
        to_hypothesis=hyp_7_8,
        confidence_delta=0.15,
    )

    inference = InferenceResult(
        window_inferences=windows,
        detected_modulations=[detected_modulation],
        persistent_polyrhythms=[],
        global_dominant=hyp_4_4,
        duration_seconds=duration,
    )

    return evaluate_song(inference, gt)


# ===================================================================
# Test 4: Polymeter (3/4 + 4/4)
# ===================================================================


def test_polymeter() -> EvaluationMetrics:
    """Scenario: Polyrhythmic section at 10–40 s with 3/4 + 4/4 layers.
    Engine detects a PolyrhythmLayer spanning that region.
    Dominant hypothesis picks 4/4 (matching the ground truth meter
    timeline which records 4/4 as the notated meter).

    Expected: polyrhythm_recall = 1.0, meter_accuracy = 1.0.

    Duration: 60 s.
    """
    duration = 60.0
    gt = GroundTruth(
        song_id="test_polymeter",
        duration_seconds=duration,
        meter_timeline=[
            MeterSegment(0.0, 60.0, "4/4", 4, 4, grouping=[2, 2]),
        ],
        modulations=[],
        polyrhythm_segments=[
            PolyrhythmSegment(10.0, 40.0, "3/4", "4/4"),
        ],
    )

    dom_hyp = _hyp(beat_count=4, grouping=[2, 2], confidence=0.87)

    windows = _make_windows(
        duration, 4.0, 2.0,
        dominant_fn=lambda s, e: dom_hyp,
    )

    detected_poly = PolyrhythmLayer(
        period_a_seconds=0.75,      # 3/4 at ~80 bpm
        period_b_seconds=1.0,       # 4/4 at ~60 bpm
        period_ratio=1.333,
        first_window_time=12.0,     # slightly after GT start
        last_window_time=38.0,      # slightly before GT end
        window_count=13,
        mean_confidence_a=0.75,
        mean_confidence_b=0.82,
    )

    inference = InferenceResult(
        window_inferences=windows,
        detected_modulations=[],
        persistent_polyrhythms=[detected_poly],
        global_dominant=dom_hyp,
        duration_seconds=duration,
    )

    return evaluate_song(inference, gt)


# ===================================================================
# Test 5: Sparse intro (ambiguous region)
# ===================================================================


def test_sparse_intro() -> EvaluationMetrics:
    """Scenario: Sparse intro (0–10 s) is ambiguous, followed by
    solid 4/4.  Engine flags first windows as ambiguous.

    Expected: ambiguity_alignment = 1.0 (engine agrees on ambiguity),
    meter_accuracy < 1.0 (intro windows may not match).

    Duration: 60 s.
    """
    duration = 60.0
    gt = GroundTruth(
        song_id="test_sparse_intro",
        duration_seconds=duration,
        meter_timeline=[
            MeterSegment(
                0.0, 10.0, "4/4", 4, 4,
                grouping=[2, 2],
                is_ambiguous=True,
            ),
            MeterSegment(
                10.0, 60.0, "4/4", 4, 4,
                grouping=[2, 2],
            ),
        ],
        modulations=[],
        polyrhythm_segments=[],
    )

    hyp_4_4 = _hyp(beat_count=4, grouping=[2, 2], confidence=0.90)
    hyp_weak = _hyp(beat_count=3, grouping=[3], confidence=0.35)

    def dominant_fn(start, end):
        mid = (start + end) / 2.0
        return hyp_weak if mid < 10.0 else hyp_4_4

    def ambiguity_fn(start, end):
        mid = (start + end) / 2.0
        return mid < 10.0

    windows = _make_windows(
        duration, 4.0, 2.0,
        dominant_fn=dominant_fn,
        ambiguity_fn=ambiguity_fn,
    )

    inference = InferenceResult(
        window_inferences=windows,
        detected_modulations=[],
        persistent_polyrhythms=[],
        global_dominant=hyp_4_4,
        duration_seconds=duration,
    )

    return evaluate_song(inference, gt)


# ===================================================================
# Run all tests
# ===================================================================


def run_all_tests() -> CorpusMetrics:
    """Execute all 5 synthetic test scenarios and print results.

    Returns
    -------
    CorpusMetrics
        Aggregated metrics over all test scenarios.
    """
    tests = [
        ("Test 1: Perfect 4/4", test_perfect_4_4),
        ("Test 2: 7/8 Additive", test_7_8_additive),
        ("Test 3: Known Modulation", test_known_modulation),
        ("Test 4: Polymeter", test_polymeter),
        ("Test 5: Sparse Intro", test_sparse_intro),
    ]

    all_metrics: List[EvaluationMetrics] = []
    for name, test_fn in tests:
        print(f"\n{'=' * 60}")
        print(f"  {name}")
        print(f"{'=' * 60}")
        m = test_fn()
        print(m.summary_string())
        all_metrics.append(m)

    corpus = aggregate_corpus_metrics(all_metrics)
    print(f"\n{'=' * 60}")
    print(corpus.summary_string())
    print(f"{'=' * 60}")

    return corpus


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_all_tests()
