"""Confidence Scoring Service — Rates analysis quality across dimensions."""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


def score_all_confidence(
    beat_analysis: dict,
    sections: list[dict],
    stem_quality_scores: dict,
) -> dict:
    """
    Compute confidence scores across all analysis dimensions.
    
    Returns dict with confidence levels for:
    - stem, beat, downbeat, meter, sections
    """
    return {
        "confidence_stem": _score_stem_quality(stem_quality_scores),
        "confidence_beat": _score_beat_quality(beat_analysis),
        "confidence_downbeat": _score_downbeat_quality(beat_analysis),
        "confidence_meter": _score_meter_quality(sections),
        "confidence_sections": _score_section_quality(sections, beat_analysis),
    }


def _score_stem_quality(quality_scores: dict) -> str:
    """Score stem separation quality based on energy ratios."""
    drums_score = quality_scores.get("drums", 0)
    
    # Higher energy ratio = cleaner separation
    if drums_score > 0.15:
        return "high"
    elif drums_score > 0.08:
        return "medium"
    else:
        return "low"


def _score_beat_quality(beat_analysis: dict) -> str:
    """Score beat grid quality based on tempo stability and beat regularity."""
    beat_times = beat_analysis.get("beat_times", [])
    bpm_stable = beat_analysis.get("bpm_stable", False)
    
    if len(beat_times) < 4:
        return "low"
    
    # Check inter-beat interval consistency
    iois = np.diff(beat_times)
    if len(iois) == 0:
        return "low"
    
    cv = np.std(iois) / np.mean(iois) if np.mean(iois) > 0 else 1.0  # Coefficient of variation
    
    if bpm_stable and cv < 0.08:
        return "high"
    elif cv < 0.15:
        return "medium"
    else:
        return "low"


def _score_downbeat_quality(beat_analysis: dict) -> str:
    """Score downbeat detection quality."""
    downbeat_times = beat_analysis.get("downbeat_times", [])
    beat_times = beat_analysis.get("beat_times", [])
    duration = beat_analysis.get("duration_seconds", 0)
    
    if len(downbeat_times) < 2:
        return "low"
    
    # Check downbeat spacing regularity
    db_iois = np.diff(downbeat_times)
    if len(db_iois) == 0:
        return "low"
    
    cv = np.std(db_iois) / np.mean(db_iois) if np.mean(db_iois) > 0 else 1.0
    
    # Also check that downbeats align with beats
    alignment_score = _check_downbeat_alignment(downbeat_times, beat_times)
    
    if cv < 0.1 and alignment_score > 0.85:
        return "high"
    elif cv < 0.2 and alignment_score > 0.6:
        return "medium"
    else:
        return "low"


def _check_downbeat_alignment(downbeats: list[float], beats: list[float]) -> float:
    """Check what fraction of downbeats align closely with detected beats."""
    if not downbeats or not beats:
        return 0.0
    
    beats_arr = np.array(beats)
    aligned = 0
    
    for db in downbeats:
        min_dist = np.min(np.abs(beats_arr - db))
        if min_dist < 0.05:  # Within 50ms
            aligned += 1
    
    return aligned / len(downbeats)


def _score_meter_quality(sections: list[dict]) -> str:
    """Score meter detection quality based on consistency across sections."""
    if not sections:
        return "low"
    
    confidences = [s.get("confidence", "low") for s in sections]
    
    high_count = confidences.count("high")
    total = len(confidences)
    
    if total == 0:
        return "low"
    
    high_ratio = high_count / total
    
    if high_ratio > 0.7:
        return "high"
    elif high_ratio > 0.4:
        return "medium"
    else:
        return "low"


def _score_section_quality(sections: list[dict], beat_analysis: dict) -> str:
    """Score section detection quality."""
    if not sections or len(sections) < 2:
        return "low"
    
    # Check section duration regularity (real songs have somewhat regular sections)
    durations = [s["end_time"] - s["start_time"] for s in sections]
    
    if len(durations) < 2:
        return "low"
    
    cv = np.std(durations) / np.mean(durations) if np.mean(durations) > 0 else 1.0
    
    # Reasonable number of sections for a typical song (3-12)
    num_sections = len(sections)
    reasonable_count = 3 <= num_sections <= 12
    
    if cv < 0.5 and reasonable_count:
        return "high"
    elif cv < 0.8 and reasonable_count:
        return "medium"
    else:
        return "low"
