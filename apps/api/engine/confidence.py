"""
Confidence Model v2 — Metric-vector scoring (replaces heuristic threshold bins).

Instead of returning "high"/"medium"/"low" based on arbitrary thresholds,
this module computes continuous [0, 1] scores grounded in measurable properties.

Dimensions:
  - tempo_stability_score:      How stable is the tempo across the song?
  - downbeat_alignment_score:   How well do downbeats align with beats?
  - meter_consistency_score:    How consistent is the meter across sections?
  - section_contrast_score:     How clear are the section boundaries?
  - groove_consistency_score:   How consistent is the groove pattern?
  - hit_classification_score:   How confident are the hit classifications?

Each score is computed on a mathematically defined scale.
An overall_confidence_score is the weighted geometric mean of all dimensions.
Geometric mean is chosen because a single bad dimension should drag
the overall score down significantly (vs arithmetic mean which hides problems).

The scoring functions are PURE — no thresholds, no bins, no heuristics.
The consumer of these scores decides their own thresholds for UI display.
"""

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ConfidenceVector:
    """Continuous confidence scores, all in [0, 1]."""
    tempo_stability_score: float = 0.0
    downbeat_alignment_score: float = 0.0
    meter_consistency_score: float = 0.0
    section_contrast_score: float = 0.0
    groove_consistency_score: float = 0.0
    hit_classification_score: float = 0.0
    overall_confidence_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "tempo_stability_score": round(self.tempo_stability_score, 4),
            "downbeat_alignment_score": round(self.downbeat_alignment_score, 4),
            "meter_consistency_score": round(self.meter_consistency_score, 4),
            "section_contrast_score": round(self.section_contrast_score, 4),
            "groove_consistency_score": round(self.groove_consistency_score, 4),
            "hit_classification_score": round(self.hit_classification_score, 4),
            "overall_confidence_score": round(self.overall_confidence_score, 4),
        }

    def level(self, dimension: str = "overall_confidence_score") -> str:
        """
        Convert a continuous score to a display level.
        Provided as convenience; consumers should prefer raw scores.
        """
        score = getattr(self, dimension, 0.0)
        if score >= 0.75:
            return "high"
        elif score >= 0.45:
            return "medium"
        else:
            return "low"


# Weights for weighted geometric mean
DIMENSION_WEIGHTS = {
    "tempo_stability_score": 0.25,
    "downbeat_alignment_score": 0.20,
    "meter_consistency_score": 0.15,
    "section_contrast_score": 0.10,
    "groove_consistency_score": 0.15,
    "hit_classification_score": 0.15,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_confidence(
    beat_times: list[float],
    downbeat_times: list[float],
    tempo_curve: list[dict],
    sections: list[dict],
    groove_profile: dict,
    hit_confidences: list[float],
    bpm: float,
) -> ConfidenceVector:
    """
    Compute the full confidence vector.

    All inputs are plain dicts/lists from previous stages.
    """
    vec = ConfidenceVector()

    vec.tempo_stability_score = _score_tempo_stability(tempo_curve, bpm)
    vec.downbeat_alignment_score = _score_downbeat_alignment(downbeat_times, beat_times)
    vec.meter_consistency_score = _score_meter_consistency(sections)
    vec.section_contrast_score = _score_section_contrast(sections)
    vec.groove_consistency_score = _score_groove_consistency(groove_profile)
    vec.hit_classification_score = _score_hit_classification(hit_confidences)
    vec.overall_confidence_score = _weighted_geometric_mean(vec)

    logger.info(
        f"Confidence: overall={vec.overall_confidence_score:.3f} "
        f"(tempo={vec.tempo_stability_score:.3f}, "
        f"db_align={vec.downbeat_alignment_score:.3f}, "
        f"meter={vec.meter_consistency_score:.3f}, "
        f"section={vec.section_contrast_score:.3f}, "
        f"groove={vec.groove_consistency_score:.3f}, "
        f"hits={vec.hit_classification_score:.3f})"
    )

    return vec


# ---------------------------------------------------------------------------
# Individual scoring functions
# ---------------------------------------------------------------------------


def _score_tempo_stability(tempo_curve: list[dict], bpm: float) -> float:
    """
    Score: how stable is the tempo?

    Uses the coefficient of variation (CV) of the tempo curve.
    CV = σ/μ. For perfectly stable tempo, CV = 0 → score = 1.

    Mapping: score = exp(-10 * CV²)
    This gives:
      CV = 0.00 → 1.000 (perfect)
      CV = 0.02 → 0.996 (very stable)
      CV = 0.05 → 0.975 (stable)
      CV = 0.10 → 0.905 (slight drift)
      CV = 0.20 → 0.670 (rubato)
      CV = 0.50 → 0.082 (highly variable)
    """
    if not tempo_curve or len(tempo_curve) < 2:
        return 0.5  # insufficient data

    bpms = np.array([p["bpm"] for p in tempo_curve])
    mean_bpm = np.mean(bpms)
    if mean_bpm <= 0:
        return 0.0

    cv = float(np.std(bpms) / mean_bpm)
    return float(np.exp(-10 * cv ** 2))


def _score_downbeat_alignment(
    downbeat_times: list[float], beat_times: list[float]
) -> float:
    """
    Score: what fraction of downbeats coincide with a detected beat?

    A downbeat is "aligned" if it's within 30ms of the nearest beat.
    30ms ≈ the perceptual onset fusion threshold.

    Mapping: score = aligned_fraction ^ 0.5
    The square root makes the score lenient for small numbers of misaligned
    downbeats (3 of 4 aligned = 0.866, not 0.75).
    """
    if not downbeat_times or not beat_times:
        return 0.0

    beats = np.array(beat_times)
    aligned = 0
    for db in downbeat_times:
        min_dist = float(np.min(np.abs(beats - db)))
        if min_dist < 0.030:  # 30ms
            aligned += 1

    fraction = aligned / len(downbeat_times)
    return float(fraction ** 0.5)


def _score_meter_consistency(sections: list[dict]) -> float:
    """
    Score: how consistent is the meter across sections?

    If all sections agree on meter → 1.0.
    Uses Shannon entropy of the meter distribution, normalized.
    """
    if not sections:
        return 0.0

    meters = [s.get("meter", "4/4") for s in sections]
    from collections import Counter
    counts = Counter(meters)
    total = len(meters)

    if total <= 1:
        return 1.0

    # Shannon entropy
    probs = np.array([c / total for c in counts.values()])
    entropy = -np.sum(probs * np.log2(probs + 1e-12))
    max_entropy = np.log2(total)

    if max_entropy <= 0:
        return 1.0

    normalized_entropy = entropy / max_entropy
    # score = 1 - normalized_entropy
    return float(max(0.0, 1.0 - normalized_entropy))


def _score_section_contrast(sections: list[dict]) -> float:
    """
    Score: how clear are section boundaries?

    Uses the boundary_novelty_score from each section (computed by
    the temporal stage's checkerboard novelty).

    score = mean(boundary_novelty_scores) for all non-start boundaries.
    """
    if not sections or len(sections) < 2:
        return 0.5

    novelty_scores = []
    for i, sec in enumerate(sections):
        if i == 0:
            continue  # song start is always certain
        ns = sec.get("boundary_novelty_score", 0.0)
        novelty_scores.append(ns)

    if not novelty_scores:
        return 0.5

    return float(np.mean(novelty_scores))


def _score_groove_consistency(groove_profile: dict) -> float:
    """
    Score: how consistent is the groove pattern?

    Uses groove_tightness_score directly (already 0–1).
    Also penalizes if swing variance is high (inconsistent swing).

    score = tightness * (1 - min(swing_std / 0.15, 1.0))
    """
    if not groove_profile:
        return 0.0

    tightness = groove_profile.get("groove_tightness_score", 0.0)
    swing_std = groove_profile.get("swing_ratio_std", 0.0)

    swing_penalty = min(swing_std / 0.15, 1.0)
    return float(tightness * (1.0 - swing_penalty))


def _score_hit_classification(hit_confidences: list[float]) -> float:
    """
    Score: how confident are we in drum hit classifications?

    Uses the mean confidence across all classified hits.
    Penalizes if a significant fraction of hits are below 0.4.

    score = mean_conf * (1 - low_fraction * 0.5)
    """
    if not hit_confidences:
        return 0.0

    arr = np.array(hit_confidences)
    mean_conf = float(np.mean(arr))
    low_fraction = float(np.sum(arr < 0.4) / len(arr))

    return float(mean_conf * (1.0 - low_fraction * 0.5))


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------


def _weighted_geometric_mean(vec: ConfidenceVector) -> float:
    """
    Weighted geometric mean of all dimension scores.

    WGM = exp( Σ w_i * ln(s_i + ε) / Σ w_i )

    The ε prevents log(0).
    """
    epsilon = 1e-6
    log_sum = 0.0
    weight_sum = 0.0

    for dim, weight in DIMENSION_WEIGHTS.items():
        score = getattr(vec, dim, 0.0)
        log_sum += weight * np.log(score + epsilon)
        weight_sum += weight

    if weight_sum <= 0:
        return 0.0

    return float(np.exp(log_sum / weight_sum))
