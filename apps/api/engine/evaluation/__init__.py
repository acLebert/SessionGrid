"""
engine.evaluation — Evaluation framework for metrical inference.

Modules
~~~~~~~
- **ground_truth** — Canonical data structures (GroundTruth,
  MeterSegment, GroundTruthModulation, TempoSegment,
  PolyrhythmSegment).
- **transcript_parser** — JSON loading and validation.
- **metrics** — Side-effect-free metric computation.
- **evaluator** — Top-level evaluation pipeline and test scenarios.
"""

from engine.evaluation.ground_truth import (        # noqa: F401
    GroundTruth,
    GroundTruthModulation,
    MeterSegment,
    PolyrhythmSegment,
    TempoSegment,
)
from engine.evaluation.transcript_parser import (   # noqa: F401
    TranscriptValidationError,
    load_ground_truth,
    parse_ground_truth,
)
from engine.evaluation.metrics import (             # noqa: F401
    CorpusMetrics,
    EvaluationMetrics,
    aggregate_corpus_metrics,
    compute_metrics,
)
from engine.evaluation.evaluator import (           # noqa: F401
    evaluate_corpus,
    evaluate_song,
    run_all_tests,
)

__all__ = [
    # ground_truth
    "GroundTruth",
    "GroundTruthModulation",
    "MeterSegment",
    "PolyrhythmSegment",
    "TempoSegment",
    # transcript_parser
    "TranscriptValidationError",
    "load_ground_truth",
    "parse_ground_truth",
    # metrics
    "CorpusMetrics",
    "EvaluationMetrics",
    "aggregate_corpus_metrics",
    "compute_metrics",
    # evaluator
    "evaluate_corpus",
    "evaluate_song",
    "run_all_tests",
]
