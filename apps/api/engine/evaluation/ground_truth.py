"""
Ground Truth Data Structures for Evaluation.

Canonical data model for drum transcription ground truth.
All structures are immutable dataclasses with serialisation
support.  Used by the transcript parser and evaluator.

These structures are deliberately independent of the inference
engine's internal types to maintain evaluation isolation — the
evaluator maps between them during comparison.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class MeterSegment:
    """A contiguous region of constant meter in the ground truth.

    Attributes
    ----------
    start_time : float
        Segment start in seconds.
    end_time : float
        Segment end in seconds.
    meter : str
        Time signature string, e.g. ``"7/8"``, ``"4/4"``, ``"5/4"``.
    numerator : int
        Beats per bar (parsed from ``meter``).
    denominator : int
        Beat unit (parsed from ``meter``).
    grouping : list[int] or None
        Additive grouping vector, e.g. ``[2, 2, 3]`` for 7/8.
        If ``None``, no grouping assertion is made for this segment.
    is_ambiguous : bool
        If ``True``, this segment is intentionally ambiguous in the
        source material (e.g., free time, rubato).  The evaluator
        treats ambiguous segments specially.
    """
    start_time: float
    end_time: float
    meter: str
    numerator: int
    denominator: int
    grouping: Optional[List[int]] = None
    is_ambiguous: bool = False

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


@dataclass(frozen=True)
class GroundTruthModulation:
    """A meter change event in the ground truth.

    Attributes
    ----------
    time : float
        Exact modulation timestamp in seconds.
    from_meter : str
        Meter before modulation (e.g. ``"4/4"``).
    to_meter : str
        Meter after modulation (e.g. ``"7/8"``).
    """
    time: float
    from_meter: str
    to_meter: str


@dataclass(frozen=True)
class TempoSegment:
    """A contiguous region of constant tempo.

    Attributes
    ----------
    start_time : float
        Segment start in seconds.
    end_time : float
        Segment end in seconds.
    bpm : float
        Tempo in beats per minute.
    """
    start_time: float
    end_time: float
    bpm: float


@dataclass(frozen=True)
class PolyrhythmSegment:
    """A region where two independent meters coexist.

    Attributes
    ----------
    start_time : float
        Segment start.
    end_time : float
        Segment end.
    meter_a : str
        First meter layer.
    meter_b : str
        Second meter layer.
    """
    start_time: float
    end_time: float
    meter_a: str
    meter_b: str


@dataclass
class GroundTruth:
    """Complete ground truth for a single song.

    Attributes
    ----------
    song_id : str
        Identifier for the song (filename, title, etc.).
    duration_seconds : float
        Total song duration.
    meter_timeline : list[MeterSegment]
        Ordered, non-overlapping meter segments covering the full
        song duration.
    modulations : list[GroundTruthModulation]
        Explicit meter change events.
    tempo_map : list[TempoSegment] or None
        Optional tempo map for BPM-aware evaluation.
    polyrhythm_segments : list[PolyrhythmSegment]
        Regions of simultaneous independent meters.
    metadata : dict
        Arbitrary metadata (genre, source, annotator, etc.).
    """
    song_id: str = ""
    duration_seconds: float = 0.0
    meter_timeline: List[MeterSegment] = field(default_factory=list)
    modulations: List[GroundTruthModulation] = field(default_factory=list)
    tempo_map: Optional[List[TempoSegment]] = None
    polyrhythm_segments: List[PolyrhythmSegment] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def meter_at_time(self, t: float) -> Optional[MeterSegment]:
        """Return the MeterSegment active at time *t*.

        Binary search over the sorted timeline.

        Time complexity: O(log N) where N = number of segments.
        """
        lo, hi = 0, len(self.meter_timeline) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            seg = self.meter_timeline[mid]
            if t < seg.start_time:
                hi = mid - 1
            elif t >= seg.end_time:
                lo = mid + 1
            else:
                return seg
        return None

    def is_polyrhythm_at_time(self, t: float) -> bool:
        """Check if time *t* falls within a polyrhythm region."""
        for seg in self.polyrhythm_segments:
            if seg.start_time <= t < seg.end_time:
                return True
        return False

    def to_dict(self) -> dict:
        return {
            "song_id": self.song_id,
            "duration_seconds": self.duration_seconds,
            "meter_timeline": [
                {
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "meter": s.meter,
                    "numerator": s.numerator,
                    "denominator": s.denominator,
                    "grouping": s.grouping,
                    "is_ambiguous": s.is_ambiguous,
                }
                for s in self.meter_timeline
            ],
            "modulations": [
                {
                    "time": m.time,
                    "from_meter": m.from_meter,
                    "to_meter": m.to_meter,
                }
                for m in self.modulations
            ],
            "tempo_map": (
                [
                    {
                        "start_time": t.start_time,
                        "end_time": t.end_time,
                        "bpm": t.bpm,
                    }
                    for t in self.tempo_map
                ]
                if self.tempo_map
                else None
            ),
            "polyrhythm_segments": [
                {
                    "start_time": p.start_time,
                    "end_time": p.end_time,
                    "meter_a": p.meter_a,
                    "meter_b": p.meter_b,
                }
                for p in self.polyrhythm_segments
            ],
            "metadata": self.metadata,
        }
