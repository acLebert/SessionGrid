"""
Smoke tests for PersistentSubdivisionGraphBuilder.

Run with:
    cd apps/api && python -m pytest tests/test_subdivision_graph.py -v
"""

import numpy as np
import pytest

from engine.stages.subdivision_graph import (
    PersistentSubdivisionGraphBuilder,
    RhythmGraph,
    SubdivisionLayer,
    PhaseRelation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_beat_times(bpm: float, n_beats: int, start: float = 0.0) -> np.ndarray:
    """Generate evenly spaced beat times."""
    period = 60.0 / bpm
    return np.array([start + i * period for i in range(n_beats)], dtype=np.float64)


def _make_grid_onsets(
    beat_times: np.ndarray,
    ratio: int,
    phase_shift: float = 0.0,
    jitter_std: float = 0.002,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate onsets on a subdivision grid with optional jitter.

    Parameters
    ----------
    beat_times : array of beat timestamps
    ratio : subdivision ratio (2 = 8ths, 3 = triplets, etc.)
    phase_shift : fractional offset in [0, 1) of subdivision period
    jitter_std : standard deviation of random timing jitter (seconds)

    Returns
    -------
    (onset_times, onset_strengths)
    """
    rng = np.random.default_rng(42)
    onsets = []
    for i in range(len(beat_times) - 1):
        b_start = beat_times[i]
        b_end = beat_times[i + 1]
        sub_dur = (b_end - b_start) / ratio
        for s in range(ratio):
            t = b_start + s * sub_dur + phase_shift * sub_dur
            t += rng.normal(0, jitter_std)
            if b_start <= t < b_end:
                onsets.append(t)

    onsets = np.array(sorted(onsets), dtype=np.float64)
    strengths = np.ones_like(onsets)
    return onsets, strengths


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBasicConstruction:
    """Verify the builder runs and produces a valid RhythmGraph."""

    def test_too_few_beats_returns_empty_graph(self):
        """With < window_beats beats, should return empty graph."""
        builder = PersistentSubdivisionGraphBuilder(window_beats=8)
        beat_times = _make_beat_times(120.0, 5)
        onsets = np.array([0.1, 0.3, 0.5])
        strengths = np.ones(3)
        downbeats = beat_times[::4]

        graph = builder.build(onsets, strengths, beat_times, downbeats)

        assert isinstance(graph, RhythmGraph)
        assert graph.total_beats == 5
        assert len(graph.layers) == 0

    def test_empty_onsets_returns_empty_layers(self):
        """No onsets → no layers, but graph is still valid."""
        builder = PersistentSubdivisionGraphBuilder(window_beats=8)
        beat_times = _make_beat_times(120.0, 20)
        onsets = np.array([], dtype=np.float64)
        strengths = np.array([], dtype=np.float64)
        downbeats = beat_times[::4]

        graph = builder.build(onsets, strengths, beat_times, downbeats)

        assert isinstance(graph, RhythmGraph)
        assert len(graph.layers) == 0
        assert graph.total_beats == 20


class TestEighthNotesRock:
    """4/4 rock pattern with straight 8th notes (ratio=2)."""

    def setup_method(self):
        self.bpm = 120.0
        self.n_beats = 32
        self.beat_times = _make_beat_times(self.bpm, self.n_beats)
        self.downbeats = self.beat_times[::4]
        self.onsets, self.strengths = _make_grid_onsets(
            self.beat_times, ratio=2, jitter_std=0.003,
        )

    def test_finds_ratio_2(self):
        builder = PersistentSubdivisionGraphBuilder(window_beats=8)
        graph = builder.build(
            self.onsets, self.strengths,
            self.beat_times, self.downbeats,
        )

        assert len(graph.layers) > 0
        ratios = {l.ratio for l in graph.layers}
        assert 2 in ratios, f"Expected ratio 2 in layers, got {ratios}"

    def test_ratio_2_has_highest_persistence(self):
        builder = PersistentSubdivisionGraphBuilder(window_beats=8)
        graph = builder.build(
            self.onsets, self.strengths,
            self.beat_times, self.downbeats,
        )

        best = graph.layers[0]  # sorted by persistence descending
        # ratio=2 or ratio=4 are both valid (4 subdivides to 2)
        assert best.ratio in (2, 4), (
            f"Expected highest-persistence layer to be ratio 2 or 4, "
            f"got {best.ratio}"
        )

    def test_to_dict_roundtrip(self):
        builder = PersistentSubdivisionGraphBuilder(window_beats=8)
        graph = builder.build(
            self.onsets, self.strengths,
            self.beat_times, self.downbeats,
        )
        d = graph.to_dict()

        assert "pulse_period" in d
        assert "layers" in d
        assert "phase_relations" in d
        assert "total_beats" in d
        assert isinstance(d["layers"], list)
        assert d["total_beats"] == self.n_beats


class TestTriplets:
    """Triplet pattern (ratio=3)."""

    def setup_method(self):
        self.bpm = 100.0
        self.n_beats = 24
        self.beat_times = _make_beat_times(self.bpm, self.n_beats)
        self.downbeats = self.beat_times[::4]
        self.onsets, self.strengths = _make_grid_onsets(
            self.beat_times, ratio=3, jitter_std=0.003,
        )

    def test_finds_ratio_3(self):
        builder = PersistentSubdivisionGraphBuilder(window_beats=8)
        graph = builder.build(
            self.onsets, self.strengths,
            self.beat_times, self.downbeats,
        )

        ratios = {l.ratio for l in graph.layers}
        assert 3 in ratios, f"Expected ratio 3 in layers, got {ratios}"

    def test_ratio_3_is_dominant(self):
        builder = PersistentSubdivisionGraphBuilder(window_beats=8)
        graph = builder.build(
            self.onsets, self.strengths,
            self.beat_times, self.downbeats,
        )

        # ratio 3 should be among top layers
        top_ratios = [l.ratio for l in graph.layers[:3]]
        assert 3 in top_ratios


class TestFiveTuplets:
    """5-tuplet pattern (ratio=5) — less common but must be detected."""

    def setup_method(self):
        self.bpm = 90.0
        self.n_beats = 24
        self.beat_times = _make_beat_times(self.bpm, self.n_beats)
        self.downbeats = self.beat_times[::4]
        self.onsets, self.strengths = _make_grid_onsets(
            self.beat_times, ratio=5, jitter_std=0.003,
        )

    def test_finds_ratio_5(self):
        builder = PersistentSubdivisionGraphBuilder(window_beats=8)
        graph = builder.build(
            self.onsets, self.strengths,
            self.beat_times, self.downbeats,
        )

        ratios = {l.ratio for l in graph.layers}
        assert 5 in ratios, f"Expected ratio 5 in layers, got {ratios}"


class TestNestedPatterns:
    """Pattern with both 8th notes and triplets overlaid."""

    def setup_method(self):
        self.bpm = 120.0
        self.n_beats = 32
        self.beat_times = _make_beat_times(self.bpm, self.n_beats)
        self.downbeats = self.beat_times[::4]

        # Mix 8ths and triplets (first half 8ths, second half triplets)
        mid = self.n_beats // 2
        o1, s1 = _make_grid_onsets(
            self.beat_times[:mid + 1], ratio=2, jitter_std=0.003,
        )
        o2, s2 = _make_grid_onsets(
            self.beat_times[mid:], ratio=3, jitter_std=0.003,
        )
        self.onsets = np.concatenate([o1, o2])
        self.strengths = np.concatenate([s1, s2])

    def test_finds_both_ratios(self):
        builder = PersistentSubdivisionGraphBuilder(window_beats=8)
        graph = builder.build(
            self.onsets, self.strengths,
            self.beat_times, self.downbeats,
        )

        ratios = {l.ratio for l in graph.layers}
        assert 2 in ratios or 4 in ratios, f"Expected 8ths in {ratios}"
        assert 3 in ratios, f"Expected triplets in {ratios}"


class TestPhaseRelations:
    """Verify phase relations are computed between different-ratio layers."""

    def test_has_phase_relations(self):
        bpm = 120.0
        n_beats = 32
        beat_times = _make_beat_times(bpm, n_beats)
        downbeats = beat_times[::4]

        # Combine 8ths and triplets across the full track
        o1, s1 = _make_grid_onsets(beat_times, ratio=2, jitter_std=0.002)
        o2, s2 = _make_grid_onsets(beat_times, ratio=3, jitter_std=0.002)
        onsets = np.sort(np.concatenate([o1, o2]))
        strengths = np.concatenate([s1, s2])

        builder = PersistentSubdivisionGraphBuilder(window_beats=8)
        graph = builder.build(onsets, strengths, beat_times, downbeats)

        # Should have phase relations between the 2 and 3 layers
        assert len(graph.phase_relations) > 0
        pair_ratios = {(pr.ratio_a, pr.ratio_b) for pr in graph.phase_relations}
        # At least one cross-ratio pair should exist
        for pr in graph.phase_relations:
            assert pr.ratio_a != pr.ratio_b


class TestPulse:
    """Verify pulse_period is correctly estimated."""

    def test_pulse_period_120bpm(self):
        beat_times = _make_beat_times(120.0, 20)
        downbeats = beat_times[::4]
        onsets, strengths = _make_grid_onsets(beat_times, ratio=2)

        builder = PersistentSubdivisionGraphBuilder()
        graph = builder.build(onsets, strengths, beat_times, downbeats)

        expected_pulse = 60.0 / 120.0  # 0.5s
        assert abs(graph.pulse_period - expected_pulse) < 0.01

    def test_pulse_period_90bpm(self):
        beat_times = _make_beat_times(90.0, 20)
        downbeats = beat_times[::4]
        onsets, strengths = _make_grid_onsets(beat_times, ratio=2)

        builder = PersistentSubdivisionGraphBuilder()
        graph = builder.build(onsets, strengths, beat_times, downbeats)

        expected_pulse = 60.0 / 90.0
        assert abs(graph.pulse_period - expected_pulse) < 0.01
