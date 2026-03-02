"""
Transcript Parser — Load and validate ground truth JSON.

Expected JSON schema::

    {
        "song_id": "Track01",
        "duration_seconds": 180.0,
        "meter_timeline": [
            {
                "start_time": 0.0,
                "end_time": 60.0,
                "meter": "4/4",
                "grouping": [4],          // optional
                "is_ambiguous": false      // optional, default false
            },
            ...
        ],
        "modulations": [
            {
                "time": 60.0,
                "from_meter": "4/4",
                "to_meter": "7/8"
            }
        ],
        "tempo_map": [                     // optional
            {
                "start_time": 0.0,
                "end_time": 180.0,
                "bpm": 120.0
            }
        ],
        "polyrhythm_segments": [           // optional
            {
                "start_time": 30.0,
                "end_time": 60.0,
                "meter_a": "4/4",
                "meter_b": "7/8"
            }
        ],
        "metadata": {}                     // optional
    }

Validation rules
~~~~~~~~~~~~~~~~
1. ``meter`` must match ``N/D`` where N, D are positive integers.
2. If ``grouping`` is provided, elements must sum to the numerator.
3. Meter segments must be sorted by ``start_time``, non-overlapping.
4. Segments must cover the full ``[0, duration_seconds]`` range.
5. Modulations must be sorted chronologically.
6. Tempo segments (if present) must be sorted, non-overlapping.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.evaluation.ground_truth import (
    GroundTruth,
    GroundTruthModulation,
    MeterSegment,
    PolyrhythmSegment,
    TempoSegment,
)

logger = logging.getLogger(__name__)

_METER_RE = re.compile(r"^(\d+)/(\d+)$")

# ---------------------------------------------------------------------------
# Parsing errors
# ---------------------------------------------------------------------------


class TranscriptValidationError(ValueError):
    """Raised when ground truth JSON fails validation."""
    pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_ground_truth(json_path: str) -> GroundTruth:
    """Load and validate a ground truth transcript from a JSON file.

    Parameters
    ----------
    json_path : str
        Filesystem path to the JSON transcript.

    Returns
    -------
    GroundTruth
        Validated ground truth object.

    Raises
    ------
    FileNotFoundError
        If *json_path* does not exist.
    TranscriptValidationError
        If the JSON content fails any validation rule.
    json.JSONDecodeError
        If the file is not valid JSON.

    Time complexity
    ---------------
    O(N + M + T) where N = meter segments, M = modulations,
    T = tempo segments.  All validation passes are linear.
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Transcript file not found: {json_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return parse_ground_truth(data)


def parse_ground_truth(data: Dict[str, Any]) -> GroundTruth:
    """Parse and validate a ground truth dict (already loaded from JSON).

    This is the core validation function — ``load_ground_truth`` delegates
    to it after reading the file.

    Parameters
    ----------
    data : dict
        Raw JSON-decoded dict.

    Returns
    -------
    GroundTruth

    Raises
    ------
    TranscriptValidationError
        On any validation failure.

    Time complexity: O(N + M + T), linear in input size.
    """
    song_id = str(data.get("song_id", "unknown"))
    duration = _require_float(data, "duration_seconds")
    if duration <= 0:
        raise TranscriptValidationError(
            f"duration_seconds must be positive, got {duration}"
        )

    # --- Meter timeline ---
    raw_meters = data.get("meter_timeline")
    if not raw_meters or not isinstance(raw_meters, list):
        raise TranscriptValidationError(
            "meter_timeline must be a non-empty list"
        )
    meter_timeline = _parse_meter_timeline(raw_meters, duration)

    # --- Modulations ---
    raw_mods = data.get("modulations", [])
    modulations = _parse_modulations(raw_mods)

    # --- Tempo map (optional) ---
    raw_tempo = data.get("tempo_map")
    tempo_map: Optional[List[TempoSegment]] = None
    if raw_tempo is not None:
        tempo_map = _parse_tempo_map(raw_tempo)

    # --- Polyrhythm segments (optional) ---
    raw_poly = data.get("polyrhythm_segments", [])
    polyrhythm_segments = _parse_polyrhythm_segments(raw_poly)

    # --- Metadata ---
    metadata = data.get("metadata", {})

    gt = GroundTruth(
        song_id=song_id,
        duration_seconds=duration,
        meter_timeline=meter_timeline,
        modulations=modulations,
        tempo_map=tempo_map,
        polyrhythm_segments=polyrhythm_segments,
        metadata=metadata if isinstance(metadata, dict) else {},
    )

    logger.info(
        f"Ground truth loaded: {song_id}, {duration:.1f}s, "
        f"{len(meter_timeline)} segments, {len(modulations)} modulations"
    )
    return gt


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------


def _require_float(data: dict, key: str) -> float:
    """Extract a required float field."""
    val = data.get(key)
    if val is None:
        raise TranscriptValidationError(f"Missing required field: {key}")
    try:
        return float(val)
    except (TypeError, ValueError):
        raise TranscriptValidationError(
            f"Field {key} must be numeric, got {type(val).__name__}"
        )


def _parse_meter_string(meter: str) -> tuple:
    """Parse ``'N/D'`` → (numerator, denominator).

    Raises TranscriptValidationError on bad format.
    """
    m = _METER_RE.match(meter.strip())
    if not m:
        raise TranscriptValidationError(
            f"Invalid meter format: '{meter}' — expected 'N/D' "
            f"(e.g. '7/8', '4/4')"
        )
    num, den = int(m.group(1)), int(m.group(2))
    if num <= 0 or den <= 0:
        raise TranscriptValidationError(
            f"Meter numerator and denominator must be positive: '{meter}'"
        )
    return num, den


def _parse_meter_timeline(
    raw: List[dict],
    duration: float,
) -> List[MeterSegment]:
    """Parse and validate the meter timeline.

    Validation
    ----------
    1. Each segment has start_time, end_time, meter.
    2. Meter format is valid.
    3. If grouping provided, it sums to the numerator.
    4. Segments are sorted, non-overlapping, contiguous.
    5. Timeline covers [0, duration].

    Time complexity: O(N).
    """
    segments: List[MeterSegment] = []

    for i, entry in enumerate(raw):
        # Required fields
        if "start_time" not in entry:
            raise TranscriptValidationError(
                f"meter_timeline[{i}]: missing 'start_time'"
            )
        if "end_time" not in entry:
            raise TranscriptValidationError(
                f"meter_timeline[{i}]: missing 'end_time'"
            )
        if "meter" not in entry:
            raise TranscriptValidationError(
                f"meter_timeline[{i}]: missing 'meter'"
            )

        start = float(entry["start_time"])
        end = float(entry["end_time"])
        meter = str(entry["meter"])
        numerator, denominator = _parse_meter_string(meter)

        if end <= start:
            raise TranscriptValidationError(
                f"meter_timeline[{i}]: end_time ({end}) must be > "
                f"start_time ({start})"
            )

        # Grouping validation
        grouping = entry.get("grouping")
        if grouping is not None:
            if not isinstance(grouping, list) or len(grouping) == 0:
                raise TranscriptValidationError(
                    f"meter_timeline[{i}]: grouping must be a non-empty "
                    f"list, got {grouping}"
                )
            if not all(isinstance(g, int) and g > 0 for g in grouping):
                raise TranscriptValidationError(
                    f"meter_timeline[{i}]: grouping elements must be "
                    f"positive integers, got {grouping}"
                )
            if sum(grouping) != numerator:
                raise TranscriptValidationError(
                    f"meter_timeline[{i}]: grouping {grouping} sums to "
                    f"{sum(grouping)}, expected numerator {numerator}"
                )

        is_ambiguous = bool(entry.get("is_ambiguous", False))

        segments.append(MeterSegment(
            start_time=start,
            end_time=end,
            meter=meter,
            numerator=numerator,
            denominator=denominator,
            grouping=grouping,
            is_ambiguous=is_ambiguous,
        ))

    # Sort and validate ordering / contiguity
    segments.sort(key=lambda s: s.start_time)

    for i in range(len(segments) - 1):
        gap = segments[i + 1].start_time - segments[i].end_time
        if gap < -0.001:
            raise TranscriptValidationError(
                f"meter_timeline: segments {i} and {i+1} overlap "
                f"({segments[i].end_time:.3f} > {segments[i+1].start_time:.3f})"
            )
        if gap > 0.1:
            raise TranscriptValidationError(
                f"meter_timeline: gap of {gap:.3f}s between segments "
                f"{i} ({segments[i].end_time:.3f}) and "
                f"{i+1} ({segments[i+1].start_time:.3f})"
            )

    # Coverage check (allow small tolerance)
    if segments:
        if segments[0].start_time > 0.1:
            raise TranscriptValidationError(
                f"meter_timeline: first segment starts at "
                f"{segments[0].start_time:.3f}, expected ≤ 0.1"
            )
        if segments[-1].end_time < duration - 0.1:
            raise TranscriptValidationError(
                f"meter_timeline: last segment ends at "
                f"{segments[-1].end_time:.3f}, expected ≥ "
                f"{duration - 0.1:.3f} (duration={duration})"
            )

    return segments


def _parse_modulations(
    raw: List[dict],
) -> List[GroundTruthModulation]:
    """Parse and validate modulation events.

    Validation
    ----------
    1. Each event has time, from_meter, to_meter.
    2. Meters are valid format.
    3. Events are sorted chronologically.

    Time complexity: O(M).
    """
    mods: List[GroundTruthModulation] = []

    for i, entry in enumerate(raw):
        if "time" not in entry:
            raise TranscriptValidationError(
                f"modulations[{i}]: missing 'time'"
            )
        if "from_meter" not in entry:
            raise TranscriptValidationError(
                f"modulations[{i}]: missing 'from_meter'"
            )
        if "to_meter" not in entry:
            raise TranscriptValidationError(
                f"modulations[{i}]: missing 'to_meter'"
            )

        time = float(entry["time"])
        from_meter = str(entry["from_meter"])
        to_meter = str(entry["to_meter"])

        _parse_meter_string(from_meter)  # validate format
        _parse_meter_string(to_meter)

        mods.append(GroundTruthModulation(
            time=time,
            from_meter=from_meter,
            to_meter=to_meter,
        ))

    mods.sort(key=lambda m: m.time)

    for i in range(len(mods) - 1):
        if mods[i + 1].time < mods[i].time:
            raise TranscriptValidationError(
                f"modulations: events not sorted at index {i}"
            )

    return mods


def _parse_tempo_map(
    raw: List[dict],
) -> List[TempoSegment]:
    """Parse and validate tempo segments.

    Time complexity: O(T).
    """
    segments: List[TempoSegment] = []

    for i, entry in enumerate(raw):
        start = float(entry.get("start_time", 0))
        end = float(entry.get("end_time", 0))
        bpm = float(entry.get("bpm", 0))

        if end <= start:
            raise TranscriptValidationError(
                f"tempo_map[{i}]: end ({end}) must be > start ({start})"
            )
        if bpm <= 0:
            raise TranscriptValidationError(
                f"tempo_map[{i}]: bpm must be positive, got {bpm}"
            )

        segments.append(TempoSegment(
            start_time=start, end_time=end, bpm=bpm,
        ))

    segments.sort(key=lambda s: s.start_time)

    for i in range(len(segments) - 1):
        if segments[i + 1].start_time < segments[i].end_time - 0.001:
            raise TranscriptValidationError(
                f"tempo_map: segments {i} and {i+1} overlap"
            )

    return segments


def _parse_polyrhythm_segments(
    raw: List[dict],
) -> List[PolyrhythmSegment]:
    """Parse polyrhythm segments.

    Time complexity: O(P).
    """
    segments: List[PolyrhythmSegment] = []

    for i, entry in enumerate(raw):
        start = float(entry.get("start_time", 0))
        end = float(entry.get("end_time", 0))
        meter_a = str(entry.get("meter_a", ""))
        meter_b = str(entry.get("meter_b", ""))

        if end <= start:
            raise TranscriptValidationError(
                f"polyrhythm_segments[{i}]: end ({end}) must be > "
                f"start ({start})"
            )

        _parse_meter_string(meter_a)
        _parse_meter_string(meter_b)

        segments.append(PolyrhythmSegment(
            start_time=start, end_time=end,
            meter_a=meter_a, meter_b=meter_b,
        ))

    return segments
