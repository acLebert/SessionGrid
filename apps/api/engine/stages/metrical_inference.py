"""
Metrical Inference Stage — Multi-Resolution Periodicity Detection.

This module computes periodic structure from an onset impulse train to enable
rhythmic inference in complex music (math rock, polymeter, tempo changes).

It does NOT infer meter or assign probabilities.  It extracts raw periodicity
candidates at multiple time-scales, preserving ambiguity for downstream
hypothesis testing.

Architecture
------------
1. **Onset Impulse Train** — Converts onset timestamps into a discrete signal
   suitable for autocorrelation and spectral analysis.
2. **Multi-Resolution Periodicity Analysis** — Computes autocorrelation and
   spectral periodicity over sliding windows at configurable resolutions.
3. **Periodicity Peak Extraction** — Detects prominent periodicity peaks with
   aggressive filtering (bounds, energy, separation).
4. **Hypothesis Generator** — (Stub) Future module for probabilistic meter
   inference from periodicity evidence.

Design decisions
~~~~~~~~~~~~~~~~
- The impulse train is built at the caller's sample rate but the analyzer
  internally downsamples to an *analysis sample rate* (default 1000 Hz) for
  FFT efficiency.  1 ms resolution is well above Nyquist for the minimum
  detectable period of 100 ms.
- Autocorrelation uses the Wiener-Khinchin theorem (FFT → |X|² → IFFT) which
  is O(N log N) regardless of lag range.
- Spectral periodicity uses the same FFT but reads the magnitude spectrum in
  the period domain (1/f), giving a complementary view that is better at
  resolving closely-spaced periodicities when the signal is long.
- Sliding-window analysis captures *local* periodicity shifts (tempo ramps,
  section changes, polymeter transitions).

Bounds
------
Only periodicities satisfying ALL of the following are retained:

  - period ≥ 0.1 s  (avoids micro-noise / flamming artifacts)
  - period ≤ 16 beats at estimated tempo  (if tempo unknown, absolute cap
    of 16 s)
  - strength ≥ 5 % of the window-local maximum peak

These filters discard a large fraction of candidates — intentionally.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.signal import find_peaks

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_PERIOD_SECONDS: float = 0.1
"""Absolute floor — 100 ms ≈ 600 BPM.  Nothing musically meaningful is faster."""

MAX_PERIOD_SECONDS_FALLBACK: float = 16.0
"""Used when no estimated tempo is available."""

ENERGY_FLOOR_RATIO: float = 0.05
"""Discard peaks below 5 % of window-local max."""

DEFAULT_ANALYSIS_SR: int = 1000
"""Internal analysis sample rate for FFT efficiency (1 ms bins)."""

# ---------------------------------------------------------------------------
# Hypothesis & Scoring — Tunable Constants
# ---------------------------------------------------------------------------
# These weights control the final confidence via weighted geometric mean.
# They MUST sum to 1.0.  Adjusting them changes how the engine ranks
# competing meter hypotheses.

SCORING_WEIGHT_PERIODICITY: float = 0.20
"""Weight for raw periodicity strength in final confidence."""

SCORING_WEIGHT_ACCENT: float = 0.16
"""Weight for accent alignment score."""

SCORING_WEIGHT_IOI: float = 0.16
"""Weight for inter-onset-interval consistency score."""

SCORING_WEIGHT_PREDICTION: float = 0.16
"""Weight for prediction error inverse score."""

SCORING_WEIGHT_REPETITION: float = 0.12
"""Weight for structural repetition across windows."""

SCORING_WEIGHT_BAR_ACCENT: float = 0.20
"""Weight for bar-level accent periodicity score."""

HARMONIC_PENALTY_FACTOR: float = 0.30
"""Max penalty for hypotheses that are simple harmonic multiples of stronger ones."""

PHASE_SEARCH_RESOLUTION: int = 128
"""Discrete phase offsets tested for grid alignment optimisation."""

MAX_RAW_HYPOTHESES: int = 20
"""Cap on raw hypotheses per window before pruning."""

MAX_SCORED_HYPOTHESES: int = 8
"""Hypotheses retained after pruning by periodicity strength."""

MAX_BEAT_COUNT: int = 16
"""Maximum number of beats per bar hypothesis."""

MAX_PEAKS_PER_WINDOW: int = 6
"""Maximum periodicity peaks considered per window for generation."""

TOP_K_TRACKER: int = 5
"""Number of top hypotheses maintained across windows by the tracker."""

SMOOTHING_ALPHA: float = 0.60
"""EMA coefficient for temporal confidence smoothing.  Higher = more reactive."""

DECAY_RATE: float = 0.85
"""Per-window multiplicative decay for hypotheses not re-detected."""

MODULATION_MARGIN: float = 0.15
"""Confidence gap required for a new dominant to trigger a modulation event."""

AMBIGUITY_DELTA: float = 0.10
"""If top-2 hypotheses are within this margin, window is marked ambiguous."""

POLYRHYTHM_CONFIDENCE_FLOOR: float = 0.30
"""Minimum confidence for a layer to qualify as polyrhythmic."""

POLYRHYTHM_PERSISTENCE_WINDOWS: int = 3
"""Minimum consecutive windows a polyrhythm candidate must survive."""

PREDICTION_ERROR_TOLERANCE: float = 0.025
"""Tolerance (seconds) for exponential decay in prediction error scoring.
25 ms ≈ the just-noticeable difference for rhythm perception."""

IOI_TOLERANCE_RATIO: float = 0.15
"""Fractional tolerance for IOI clustering: IOI within ±15 % of predicted
period is considered consistent."""

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class PeriodicityCandidate:
    """A single periodicity hypothesis from one analysis source.

    Attributes
    ----------
    period_seconds : float
        Detected periodic interval in seconds.
    strength : float
        Normalised strength in [0, 1] where 1.0 is the strongest periodicity
        found within that analysis context (window or global).
    source : str
        ``"autocorrelation"`` or ``"spectrum"`` — which analysis produced this
        candidate.
    """
    period_seconds: float
    strength: float
    source: str  # "autocorrelation" | "spectrum"

    def __repr__(self) -> str:
        return (
            f"PeriodicityCandidate(T={self.period_seconds:.4f}s, "
            f"str={self.strength:.3f}, src={self.source})"
        )


@dataclass
class WindowPeriodicityResult:
    """Periodicity evidence for a single analysis window.

    Attributes
    ----------
    start_time : float
        Window start in seconds.
    end_time : float
        Window end in seconds.
    periodicity_peaks : list[PeriodicityCandidate]
        All candidates that survived bounding / energy filtering in this
        window, from both autocorrelation and spectral sources.
    """
    start_time: float
    end_time: float
    periodicity_peaks: List[PeriodicityCandidate] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"WindowPeriodicityResult([{self.start_time:.2f}–"
            f"{self.end_time:.2f}s], {len(self.periodicity_peaks)} peaks)"
        )


@dataclass
class PeriodicityResult:
    """Top-level output of the metrical inference stage.

    Attributes
    ----------
    impulse_train_sr : int
        Sample rate of the constructed impulse train.
    analysis_sr : int
        Internal analysis sample rate (after downsampling).
    duration_seconds : float
        Duration of the analysed signal.
    global_candidates : list[PeriodicityCandidate]
        Periodicity candidates from the full-duration analysis.
    window_results : list[WindowPeriodicityResult]
        Per-window periodicity evidence at each resolution.
    resolutions_used : list[dict]
        The ``{"window_seconds": …, "hop_seconds": …}`` dicts that were run.
    """
    impulse_train_sr: int = 44100
    analysis_sr: int = DEFAULT_ANALYSIS_SR
    duration_seconds: float = 0.0
    global_candidates: List[PeriodicityCandidate] = field(default_factory=list)
    window_results: List[WindowPeriodicityResult] = field(default_factory=list)
    resolutions_used: List[dict] = field(default_factory=list)


@dataclass
class MeterHypothesis:
    """A structured meter hypothesis derived from periodicity evidence.

    Attributes
    ----------
    base_period_seconds : float
        The fundamental beat period in seconds.
    beat_count : int
        Number of beats in one full bar cycle.
    grouping_vector : list[int]
        Additive grouping (e.g. [2,2,3] for 7/8).  Elements sum to
        ``beat_count``.
    phase_offset : float
        Optimal alignment offset in seconds.
    periodicity_strength : float
        Raw periodicity evidence strength from extraction layer.
    accent_alignment_score : float
        Correlation between predicted accents and onset velocities.
    prediction_error_score : float
        Inverse distance of onsets from predicted grid (exp-decay).
    ioi_consistency_score : float
        Fraction of IOIs that cluster at grid subdivisions.
    structural_repetition_score : float
        Reward for recurring grouping patterns across windows.
    harmonic_penalty : float
        Penalty for being a simple harmonic multiple of a stronger
        candidate.
    stability_score : float
        EMA-smoothed confidence from the temporal tracker.
    confidence : float
        Final weighted geometric mean score.
    bar_accent_periodicity_score : float
        Correlation of accent energy repeating at the hypothesis
        beat_count period across the analysis window.
    structural_preferred : bool
        True if promoted by HierarchicalResolver as the structurally
        preferred meter in a harmonic family.
    promoted_from_subdivision : bool
        True if this hypothesis was promoted over a shorter-period
        subdivision during hierarchical resolution.
    """
    base_period_seconds: float = 0.0
    beat_count: int = 4
    grouping_vector: List[int] = field(default_factory=lambda: [4])
    phase_offset: float = 0.0
    periodicity_strength: float = 0.0
    accent_alignment_score: float = 0.0
    prediction_error_score: float = 0.0
    ioi_consistency_score: float = 0.0
    structural_repetition_score: float = 0.0
    harmonic_penalty: float = 0.0
    stability_score: float = 0.0
    confidence: float = 0.0
    bar_accent_periodicity_score: float = 0.0
    structural_preferred: bool = False
    promoted_from_subdivision: bool = False

    @property
    def cycle_seconds(self) -> float:
        """Total bar duration in seconds."""
        return self.base_period_seconds * self.beat_count

    @property
    def hypothesis_key(self) -> str:
        """Unique string key for tracking identity across windows."""
        gv = ",".join(map(str, self.grouping_vector))
        return f"{self.beat_count}:{gv}:{self.base_period_seconds:.4f}"

    def to_dict(self) -> dict:
        return {
            "base_period_seconds": round(self.base_period_seconds, 6),
            "beat_count": self.beat_count,
            "grouping_vector": self.grouping_vector,
            "phase_offset": round(self.phase_offset, 6),
            "periodicity_strength": round(self.periodicity_strength, 4),
            "accent_alignment_score": round(self.accent_alignment_score, 4),
            "prediction_error_score": round(self.prediction_error_score, 4),
            "ioi_consistency_score": round(self.ioi_consistency_score, 4),
            "structural_repetition_score": round(self.structural_repetition_score, 4),
            "harmonic_penalty": round(self.harmonic_penalty, 4),
            "stability_score": round(self.stability_score, 4),
            "confidence": round(self.confidence, 4),
            "bar_accent_periodicity_score": round(self.bar_accent_periodicity_score, 4),
            "cycle_seconds": round(self.cycle_seconds, 6),
            "structural_preferred": self.structural_preferred,
            "promoted_from_subdivision": self.promoted_from_subdivision,
        }


@dataclass
class ModulationEvent:
    """A detected metric modulation (dominant hypothesis change)."""
    time: float
    from_hypothesis: Optional[MeterHypothesis]
    to_hypothesis: MeterHypothesis
    confidence_delta: float = 0.0

    def to_dict(self) -> dict:
        return {
            "time": round(self.time, 4),
            "from": self.from_hypothesis.to_dict() if self.from_hypothesis else None,
            "to": self.to_hypothesis.to_dict(),
            "confidence_delta": round(self.confidence_delta, 4),
        }


@dataclass
class PolyrhythmLayer:
    """A persistent polyrhythmic layer detected across windows."""
    period_a_seconds: float = 0.0
    period_b_seconds: float = 0.0
    period_ratio: float = 0.0
    first_window_time: float = 0.0
    last_window_time: float = 0.0
    window_count: int = 0
    mean_confidence_a: float = 0.0
    mean_confidence_b: float = 0.0

    def to_dict(self) -> dict:
        return {
            "period_a_seconds": round(self.period_a_seconds, 6),
            "period_b_seconds": round(self.period_b_seconds, 6),
            "period_ratio": round(self.period_ratio, 4),
            "first_window_time": round(self.first_window_time, 4),
            "last_window_time": round(self.last_window_time, 4),
            "window_count": self.window_count,
            "mean_confidence_a": round(self.mean_confidence_a, 4),
            "mean_confidence_b": round(self.mean_confidence_b, 4),
        }


@dataclass
class WindowInferenceResult:
    """Inference output for a single analysis window."""
    start_time: float = 0.0
    end_time: float = 0.0
    dominant_hypothesis: Optional[MeterHypothesis] = None
    competing_hypotheses: List[MeterHypothesis] = field(default_factory=list)
    ambiguity_flag: bool = False
    modulation_flag: bool = False

    def to_dict(self) -> dict:
        return {
            "start_time": round(self.start_time, 4),
            "end_time": round(self.end_time, 4),
            "dominant": self.dominant_hypothesis.to_dict() if self.dominant_hypothesis else None,
            "competing": [h.to_dict() for h in self.competing_hypotheses],
            "ambiguous": self.ambiguity_flag,
            "modulation": self.modulation_flag,
        }


@dataclass
class InferenceResult:
    """Top-level output of the full metrical inference pipeline."""
    window_inferences: List[WindowInferenceResult] = field(default_factory=list)
    detected_modulations: List[ModulationEvent] = field(default_factory=list)
    persistent_polyrhythms: List[PolyrhythmLayer] = field(default_factory=list)
    global_dominant: Optional[MeterHypothesis] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "window_inferences": [w.to_dict() for w in self.window_inferences],
            "detected_modulations": [m.to_dict() for m in self.detected_modulations],
            "persistent_polyrhythms": [p.to_dict() for p in self.persistent_polyrhythms],
            "global_dominant": self.global_dominant.to_dict() if self.global_dominant else None,
            "duration_seconds": round(self.duration_seconds, 4),
        }


# ---------------------------------------------------------------------------
# Stage 1 — Onset Impulse Train
# ---------------------------------------------------------------------------


def build_onset_impulse_train(
    onset_times: List[float],
    duration_seconds: float,
    sr: int,
    weight_by_velocity: Optional[List[float]] = None,
) -> np.ndarray:
    """Convert onset timestamps into a discrete impulse signal.

    Each onset is placed at the nearest sample index.  The impulse value is
    either 1.0 (unweighted) or the normalised velocity.

    Parameters
    ----------
    onset_times : list[float]
        Onset positions in seconds.
    duration_seconds : float
        Total signal duration in seconds (defines output length).
    sr : int
        Sample rate of the output impulse train.
    weight_by_velocity : list[float] or None
        Optional per-onset velocity values.  If provided, values are
        min-max normalised to [0.1, 1.0] (floor at 0.1 to avoid silent
        impulses).

    Returns
    -------
    np.ndarray
        Float32 impulse train of length ``ceil(duration_seconds * sr)``.

    Time complexity
    ---------------
    O(N) where N = number of onsets.  The array allocation is O(L) where
    L = duration × sr, but numpy zeros is near-instant (virtual memory).

    Numerical stability
    -------------------
    - Sample indices are clamped to [0, L-1] to prevent out-of-bounds.
    - Velocity normalisation guards against division by zero (constant
      velocity → all 1.0).
    """
    length = int(np.ceil(duration_seconds * sr))
    impulse = np.zeros(length, dtype=np.float32)

    if len(onset_times) == 0:
        logger.warning("build_onset_impulse_train called with 0 onsets")
        return impulse

    # Prepare velocity weights
    velocities: Optional[np.ndarray] = None
    if weight_by_velocity is not None:
        v = np.asarray(weight_by_velocity, dtype=np.float32)
        if len(v) != len(onset_times):
            raise ValueError(
                f"velocity length ({len(v)}) ≠ onset count ({len(onset_times)})"
            )
        v_min, v_max = v.min(), v.max()
        if v_max - v_min > 1e-9:
            # Normalise to [0.1, 1.0]
            velocities = 0.1 + 0.9 * (v - v_min) / (v_max - v_min)
        else:
            velocities = np.ones_like(v)

    # Place impulses
    for i, t in enumerate(onset_times):
        idx = int(round(t * sr))
        idx = max(0, min(idx, length - 1))
        val = velocities[i] if velocities is not None else 1.0
        # If two onsets map to the same sample, keep the larger value
        if val > impulse[idx]:
            impulse[idx] = val

    logger.debug(
        f"Impulse train: {len(onset_times)} onsets → {length} samples "
        f"({duration_seconds:.2f}s @ {sr} Hz)"
    )
    return impulse


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _downsample_impulse_train(
    impulse: np.ndarray,
    source_sr: int,
    target_sr: int,
) -> np.ndarray:
    """Downsample by summing bins.

    Each output bin accumulates impulse energy from ``factor`` input samples.
    This preserves periodic structure while reducing signal length for FFT
    efficiency.

    Time complexity: O(N) — single reshape + sum.

    Parameters
    ----------
    impulse : np.ndarray
        Input impulse train.
    source_sr : int
        Sample rate of *impulse*.
    target_sr : int
        Desired analysis sample rate.

    Returns
    -------
    np.ndarray (float32)
        Downsampled impulse train at *target_sr*.
    """
    if target_sr >= source_sr:
        return impulse.copy()

    factor = source_sr // target_sr
    if factor <= 1:
        return impulse.copy()

    # Trim to exact multiple of factor
    trimmed_len = (len(impulse) // factor) * factor
    trimmed = impulse[:trimmed_len]

    # Reshape and sum each bin
    downsampled = trimmed.reshape(-1, factor).sum(axis=1).astype(np.float32)

    logger.debug(
        f"Downsampled impulse: {len(impulse)} → {len(downsampled)} samples "
        f"(factor {factor}, {source_sr} → {target_sr} Hz)"
    )
    return downsampled


def _next_fast_fft_size(n: int) -> int:
    """Return the smallest FFT-friendly size ≥ n.

    Uses powers of 2 for maximum np.fft performance.  For very large n
    (>2^22 ≈ 4M) this avoids pathological prime factors.

    Time complexity: O(log n).
    """
    power = 1
    while power < n:
        power <<= 1
    return power


def _max_period_from_tempo(
    estimated_bpm: Optional[float],
    max_beats: float = 16.0,
) -> float:
    """Compute the upper period bound from an estimated tempo.

    Parameters
    ----------
    estimated_bpm : float or None
        If None, returns ``MAX_PERIOD_SECONDS_FALLBACK``.
    max_beats : float
        Maximum number of beat periods to allow (default 16).

    Returns
    -------
    float
        Upper period bound in seconds.
    """
    if estimated_bpm is None or estimated_bpm <= 0:
        return MAX_PERIOD_SECONDS_FALLBACK
    beat_period = 60.0 / estimated_bpm
    return beat_period * max_beats


# ---------------------------------------------------------------------------
# Stage 2 — Multi-Resolution Periodicity Analysis
# ---------------------------------------------------------------------------


class MultiResolutionAnalyzer:
    """FFT-based periodicity analysis at multiple time scales.

    The analyzer operates on an onset impulse train (as built by
    :func:`build_onset_impulse_train`).  Internally, the signal is
    downsampled to ``analysis_sr`` (default 1000 Hz) for FFT efficiency.

    Parameters
    ----------
    analysis_sr : int
        Internal analysis sample rate.  1000 Hz gives 1 ms resolution,
        which is 50× above Nyquist for the minimum detectable period
        (100 ms).
    estimated_bpm : float or None
        If known, used to compute the upper period bound (16 beats).
    min_period_sec : float
        Absolute minimum detectable period.
    energy_floor : float
        Discard peaks below this fraction of the window-local max.

    Default resolutions for multi-resolution sweep
    -----------------------------------------------
    ====  ==============  ==========  ============================
    Idx   window_seconds  hop_seconds Purpose
    ====  ==============  ==========  ============================
    0     2.0             0.5         Fine — catches quick changes
    1     4.0             1.0         Medium — standard bar view
    2     8.0             2.0         Coarse — phrase-level
    3     16.0            4.0         Wide — section-level
    ====  ==============  ==========  ============================
    """

    DEFAULT_RESOLUTIONS: List[dict] = [
        {"window_seconds": 2.0,  "hop_seconds": 0.5},
        {"window_seconds": 4.0,  "hop_seconds": 1.0},
        {"window_seconds": 8.0,  "hop_seconds": 2.0},
        {"window_seconds": 16.0, "hop_seconds": 4.0},
    ]

    def __init__(
        self,
        analysis_sr: int = DEFAULT_ANALYSIS_SR,
        estimated_bpm: Optional[float] = None,
        min_period_sec: float = MIN_PERIOD_SECONDS,
        energy_floor: float = ENERGY_FLOOR_RATIO,
    ) -> None:
        self.analysis_sr = analysis_sr
        self.estimated_bpm = estimated_bpm
        self.min_period_sec = min_period_sec
        self.energy_floor = energy_floor
        self._max_period_sec = _max_period_from_tempo(estimated_bpm)

    # ------------------------------------------------------------------
    # A) Autocorrelation
    # ------------------------------------------------------------------

    def compute_autocorrelation(
        self,
        impulse_train: np.ndarray,
        min_period_samples: int,
        max_period_samples: int,
    ) -> np.ndarray:
        """FFT-based autocorrelation of the impulse train.

        Uses the Wiener-Khinchin theorem:

            R(τ) = IFFT( |FFT(x)|² )

        where the FFT is zero-padded to ≥ 2N to yield the *linear* (not
        circular) autocorrelation.

        Parameters
        ----------
        impulse_train : np.ndarray
            Discrete impulse signal (1-D, float).
        min_period_samples : int
            Smallest lag to return (corresponds to shortest period).
        max_period_samples : int
            Largest lag to return (corresponds to longest period).

        Returns
        -------
        np.ndarray
            Normalised autocorrelation for lags in
            ``[min_period_samples, max_period_samples]``.  Length =
            ``max_period_samples - min_period_samples + 1``.
            Normalised so that lag-0 autocorrelation = 1.0.

        Time complexity
        ---------------
        O(N log N) where N is the padded FFT size (≤ 4 × signal length).

        Numerical stability
        -------------------
        - If the signal is all-zero (no onsets), returns a zero array to
          avoid division by zero during normalisation.
        - Uses float64 internally for FFT to prevent precision loss in
          large transforms.

        Why autocorrelation detects periodic structure
        -----------------------------------------------
        The autocorrelation R(τ) measures the self-similarity of the
        signal at lag τ.  For a strictly periodic signal with period T,
        R(T) ≈ R(0).  For a noisy signal with approximate period T,
        R(T) will show a local peak.  Peaks in R(τ) directly correspond
        to candidate periodicities.
        """
        n = len(impulse_train)

        # Clamp lag range
        max_period_samples = min(max_period_samples, n - 1)
        if min_period_samples > max_period_samples:
            return np.zeros(0, dtype=np.float64)

        output_len = max_period_samples - min_period_samples + 1

        # Zero-energy guard
        energy = np.dot(impulse_train.astype(np.float64),
                        impulse_train.astype(np.float64))
        if energy < 1e-12:
            return np.zeros(output_len, dtype=np.float64)

        # FFT-based autocorrelation (Wiener-Khinchin)
        fft_size = _next_fast_fft_size(2 * n)
        X = np.fft.rfft(impulse_train.astype(np.float64), n=fft_size)
        power_spectrum = X.real ** 2 + X.imag ** 2  # |X|², avoids complex mul
        autocorr_full = np.fft.irfft(power_spectrum, n=fft_size)

        # Normalise by zero-lag (total energy)
        r0 = autocorr_full[0]
        if r0 > 1e-12:
            autocorr_full /= r0

        # Slice to requested lag range
        result = autocorr_full[min_period_samples:max_period_samples + 1]
        return result.copy()

    # ------------------------------------------------------------------
    # B) Spectral Periodicity
    # ------------------------------------------------------------------

    def compute_periodicity_spectrum(
        self,
        impulse_train: np.ndarray,
        sr: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Frequency-domain periodicity analysis.

        Computes the magnitude spectrum of the impulse train and converts
        the frequency axis to *period* in seconds, giving a complementary
        view to autocorrelation that is better at resolving closely-spaced
        periodicities when the signal is long (high frequency resolution).

        Parameters
        ----------
        impulse_train : np.ndarray
            Discrete impulse signal.
        sr : int
            Sample rate of *impulse_train*.

        Returns
        -------
        periods_seconds : np.ndarray
            Period values in seconds (descending order — long periods first).
        magnitude_spectrum : np.ndarray
            Corresponding magnitude values, normalised to [0, 1].

        Time complexity
        ---------------
        O(N log N) for the FFT, O(K) for the frequency → period conversion
        where K = N/2 is the number of positive-frequency bins.

        Numerical stability
        -------------------
        - The DC bin (f = 0) is excluded to avoid division by zero in the
          1/f conversion.
        - Frequencies outside the detectable period range are masked out,
          reducing the returned array size and preventing numerical noise
          at extreme periods.

        Why spectral analysis complements autocorrelation
        -------------------------------------------------
        Autocorrelation is sensitive to *integer-lag* periodicities and
        can miss fractional-period relationships in short windows.  The
        spectral approach resolves periodicities via frequency peaks
        whose resolution improves with signal length (Δf = sr/N).  The
        two views reinforce strong candidates and disambiguate borderline
        ones.
        """
        n = len(impulse_train)
        if n < 2:
            return np.array([], dtype=np.float64), np.array([], dtype=np.float64)

        fft_size = _next_fast_fft_size(n)
        X = np.fft.rfft(impulse_train.astype(np.float64), n=fft_size)
        magnitudes = np.abs(X)

        freqs = np.fft.rfftfreq(fft_size, d=1.0 / sr)

        # Exclude DC and frequencies outside the detectable period range
        min_freq = 1.0 / self._max_period_sec       # longest period → lowest freq
        max_freq = 1.0 / self.min_period_sec         # shortest period → highest freq

        mask = (freqs > 0) & (freqs >= min_freq) & (freqs <= max_freq)

        freqs_valid = freqs[mask]
        mags_valid = magnitudes[mask]

        if len(freqs_valid) == 0:
            return np.array([], dtype=np.float64), np.array([], dtype=np.float64)

        # Convert frequency → period
        periods = 1.0 / freqs_valid  # seconds

        # Normalise magnitudes
        mag_max = mags_valid.max()
        if mag_max > 1e-12:
            mags_valid = mags_valid / mag_max
        else:
            mags_valid = np.zeros_like(mags_valid)

        # Sort by period descending (long periods first) for readability
        order = np.argsort(-periods)
        return periods[order].copy(), mags_valid[order].copy()

    # ------------------------------------------------------------------
    # C) Sliding Window Analysis
    # ------------------------------------------------------------------

    def analyze_sliding_windows(
        self,
        impulse_train: np.ndarray,
        sr: int,
        window_seconds: float,
        hop_seconds: float,
    ) -> List[WindowPeriodicityResult]:
        """Local periodicity analysis via overlapping windows.

        For each window position, computes both autocorrelation and spectral
        periodicity, extracts peaks using :class:`PeriodicityExtractor`, and
        returns the surviving candidates with time-stamped context.

        Parameters
        ----------
        impulse_train : np.ndarray
            Full impulse train (at *sr*).
        sr : int
            Sample rate of the impulse train.
        window_seconds : float
            Window duration.
        hop_seconds : float
            Hop between successive windows.

        Returns
        -------
        list[WindowPeriodicityResult]
            One result per window position.

        Time complexity
        ---------------
        O(W × L log L) where W = number of windows and L = window length
        in samples.  For a 5-min song at analysis_sr=1000, window=4s,
        hop=1s: W≈297, L=4000, total ≈ 297 × 4000 × 12 ≈ 14M ops — under
        50 ms on modern hardware.

        Numerical stability
        -------------------
        - Windows with zero energy (no onsets) are skipped — an empty
          ``WindowPeriodicityResult`` is recorded.
        - The extractor's energy floor is applied window-locally, so a
          quiet window does not suppress peaks relative to a loud window.

        Why sliding windows reveal local periodicity
        ---------------------------------------------
        Global autocorrelation smears time-varying rhythmic structure
        (e.g., a half-time bridge).  Short windows isolate sections where
        the periodicity is locally stable, enabling downstream inference
        to detect meter changes and polymeter.
        """
        window_samples = int(round(window_seconds * sr))
        hop_samples = int(round(hop_seconds * sr))
        total_samples = len(impulse_train)

        if window_samples < 1 or hop_samples < 1:
            logger.warning(
                f"analyze_sliding_windows: degenerate params "
                f"(win={window_samples}, hop={hop_samples})"
            )
            return []

        min_period_samples = max(1, int(round(self.min_period_sec * sr)))
        max_period_samples = min(
            window_samples - 1,
            int(round(self._max_period_sec * sr)),
        )

        extractor = PeriodicityExtractor(
            min_period_sec=self.min_period_sec,
            max_period_sec=self._max_period_sec,
            energy_floor=self.energy_floor,
        )

        results: List[WindowPeriodicityResult] = []
        start = 0
        while start + window_samples <= total_samples:
            end = start + window_samples
            segment = impulse_train[start:end]

            start_time = start / sr
            end_time = end / sr

            # Zero-energy guard
            if segment.sum() < 1e-12:
                results.append(WindowPeriodicityResult(
                    start_time=start_time,
                    end_time=end_time,
                ))
                start += hop_samples
                continue

            # Autocorrelation for this window
            autocorr = self.compute_autocorrelation(
                segment, min_period_samples, max_period_samples,
            )

            # Spectral periodicity for this window
            periods_spec, mags_spec = self.compute_periodicity_spectrum(
                segment, sr,
            )

            # Extract candidates
            candidates = extractor.extract_candidates(
                autocorrelation=autocorr,
                min_lag=min_period_samples,
                sr=sr,
                periods_seconds=periods_spec,
                magnitude_spectrum=mags_spec,
            )

            results.append(WindowPeriodicityResult(
                start_time=start_time,
                end_time=end_time,
                periodicity_peaks=candidates,
            ))
            start += hop_samples

        logger.info(
            f"Sliding window analysis: {len(results)} windows "
            f"(win={window_seconds}s, hop={hop_seconds}s)"
        )
        return results

    # ------------------------------------------------------------------
    # Convenience: multi-resolution sweep
    # ------------------------------------------------------------------

    def analyze_multi_resolution(
        self,
        impulse_train: np.ndarray,
        sr: int,
        resolutions: Optional[List[dict]] = None,
    ) -> List[WindowPeriodicityResult]:
        """Run sliding-window analysis at multiple resolutions.

        Parameters
        ----------
        impulse_train : np.ndarray
            Full impulse train.
        sr : int
            Sample rate.
        resolutions : list[dict] or None
            Each dict has ``window_seconds`` and ``hop_seconds``.
            Defaults to :attr:`DEFAULT_RESOLUTIONS`.

        Returns
        -------
        list[WindowPeriodicityResult]
            Concatenated results from all resolutions, chronologically
            ordered within each resolution tier.

        Time complexity
        ---------------
        Sum over resolutions of O(W_i × L_i log L_i).  With defaults
        and a 5-min song at 1 kHz analysis SR:
          - 2s/0.5s  → ~598 windows × 2K FFT ≈ 6.6M ops
          - 4s/1.0s  → ~297 windows × 4K FFT ≈ 14.2M ops
          - 8s/2.0s  → ~147 windows × 8K FFT ≈ 15.3M ops
          - 16s/4.0s → ~72 windows × 16K FFT ≈ 16.6M ops
        Total ≈ 53M ops — well under 200 ms.
        """
        if resolutions is None:
            resolutions = self.DEFAULT_RESOLUTIONS

        all_results: List[WindowPeriodicityResult] = []
        for res in resolutions:
            window_results = self.analyze_sliding_windows(
                impulse_train,
                sr,
                window_seconds=res["window_seconds"],
                hop_seconds=res["hop_seconds"],
            )
            all_results.extend(window_results)

        logger.info(
            f"Multi-resolution analysis complete: {len(resolutions)} "
            f"resolutions, {len(all_results)} total windows"
        )
        return all_results


# ---------------------------------------------------------------------------
# Stage 3 — Periodicity Peak Extraction
# ---------------------------------------------------------------------------


class PeriodicityExtractor:
    """Detects prominent periodicity peaks from autocorrelation and spectral
    analysis results.

    Uses ``scipy.signal.find_peaks`` with prominence, relative height, and
    minimum separation constraints, then applies the global bounds filter.

    Parameters
    ----------
    min_period_sec : float
        Minimum detectable period (default 0.1 s).
    max_period_sec : float
        Maximum detectable period.
    energy_floor : float
        Discard peaks below this fraction of the local max.
    prominence_threshold : float
        Minimum prominence for ``find_peaks`` (relative to normalised
        signal).  Lower = more sensitive, higher = fewer false positives.
    min_separation_sec : float
        Minimum separation between adjacent peaks in the period domain.
        Prevents two candidates from being too close in period.  Default
        0.02 s (20 ms).
    """

    def __init__(
        self,
        min_period_sec: float = MIN_PERIOD_SECONDS,
        max_period_sec: float = MAX_PERIOD_SECONDS_FALLBACK,
        energy_floor: float = ENERGY_FLOOR_RATIO,
        prominence_threshold: float = 0.05,
        min_separation_sec: float = 0.02,
    ) -> None:
        self.min_period_sec = min_period_sec
        self.max_period_sec = max_period_sec
        self.energy_floor = energy_floor
        self.prominence_threshold = prominence_threshold
        self.min_separation_sec = min_separation_sec

    # ------------------------------------------------------------------

    def extract_from_autocorrelation(
        self,
        autocorrelation: np.ndarray,
        min_lag: int,
        sr: int,
    ) -> List[PeriodicityCandidate]:
        """Extract periodicity candidates from an autocorrelation array.

        Parameters
        ----------
        autocorrelation : np.ndarray
            Normalised autocorrelation for lags ``[min_lag, min_lag + len - 1]``.
        min_lag : int
            The lag (in samples) corresponding to index 0 of the array.
        sr : int
            Sample rate (for converting lag → seconds).

        Returns
        -------
        list[PeriodicityCandidate]
            Filtered candidates sorted by strength descending.

        Time complexity
        ---------------
        O(K) where K = len(autocorrelation).  ``find_peaks`` is linear.

        Numerical stability
        -------------------
        - Empty or all-zero input returns an empty list.
        - ``find_peaks`` with prominence handles plateaus gracefully.

        How peaks in autocorrelation map to periodicities
        -------------------------------------------------
        A peak at lag τ in the normalised autocorrelation means the onset
        pattern repeats itself τ samples later.  The peak height indicates
        how closely the repetition matches: 1.0 = perfect repetition,
        0.0 = no correlation.
        """
        if len(autocorrelation) == 0:
            return []

        # Minimum separation in lag samples
        min_sep_samples = max(1, int(round(self.min_separation_sec * sr)))

        peak_indices, properties = find_peaks(
            autocorrelation,
            prominence=self.prominence_threshold,
            distance=min_sep_samples,
            height=0.0,  # accept any positive peak, filter by energy floor later
        )

        if len(peak_indices) == 0:
            return []

        heights = properties["peak_heights"]
        max_height = heights.max()

        candidates: List[PeriodicityCandidate] = []
        for idx, h in zip(peak_indices, heights):
            # Energy floor
            if max_height > 1e-12 and h / max_height < self.energy_floor:
                continue

            lag_samples = min_lag + idx
            period_sec = lag_samples / sr

            # Bounds check
            if period_sec < self.min_period_sec:
                continue
            if period_sec > self.max_period_sec:
                continue

            candidates.append(PeriodicityCandidate(
                period_seconds=period_sec,
                strength=float(h),
                source="autocorrelation",
            ))

        # Sort by strength descending
        candidates.sort(key=lambda c: c.strength, reverse=True)
        return candidates

    # ------------------------------------------------------------------

    def extract_from_spectrum(
        self,
        periods_seconds: np.ndarray,
        magnitude_spectrum: np.ndarray,
    ) -> List[PeriodicityCandidate]:
        """Extract periodicity candidates from the spectral periodicity.

        Parameters
        ----------
        periods_seconds : np.ndarray
            Period axis in seconds.
        magnitude_spectrum : np.ndarray
            Corresponding normalised magnitudes.

        Returns
        -------
        list[PeriodicityCandidate]
            Filtered candidates sorted by strength descending.

        Time complexity
        ---------------
        O(K) where K = len(periods_seconds).

        Numerical stability
        -------------------
        - The spectrum is expected to already be normalised to [0, 1].
        - ``find_peaks`` handles non-uniform spacing poorly, so we
          operate on the *index* domain and convert back to seconds.
          The minimum separation is computed as the number of indices
          spanning ``min_separation_sec`` at the local period resolution.

        How spectral peaks map to periodicities
        ----------------------------------------
        A peak at period T in the magnitude spectrum indicates that the
        impulse train contains a strong sinusoidal component with period T.
        This is more robust to phase jitter than autocorrelation for
        long signals, but less sensitive to transient patterns in
        short windows.
        """
        if len(periods_seconds) == 0 or len(magnitude_spectrum) == 0:
            return []

        # Apply bounds mask first
        mask = (
            (periods_seconds >= self.min_period_sec)
            & (periods_seconds <= self.max_period_sec)
        )
        periods_valid = periods_seconds[mask]
        mags_valid = magnitude_spectrum[mask]

        if len(mags_valid) == 0:
            return []

        # Estimate minimum separation in indices
        if len(periods_valid) > 1:
            mean_period_spacing = np.abs(np.diff(periods_valid)).mean()
            if mean_period_spacing > 1e-9:
                min_sep_idx = max(
                    1, int(round(self.min_separation_sec / mean_period_spacing))
                )
            else:
                min_sep_idx = 1
        else:
            min_sep_idx = 1

        peak_indices, properties = find_peaks(
            mags_valid,
            prominence=self.prominence_threshold,
            distance=min_sep_idx,
            height=0.0,
        )

        if len(peak_indices) == 0:
            return []

        heights = properties["peak_heights"]
        max_height = heights.max()

        candidates: List[PeriodicityCandidate] = []
        for idx, h in zip(peak_indices, heights):
            # Energy floor
            if max_height > 1e-12 and h / max_height < self.energy_floor:
                continue

            candidates.append(PeriodicityCandidate(
                period_seconds=float(periods_valid[idx]),
                strength=float(h),
                source="spectrum",
            ))

        candidates.sort(key=lambda c: c.strength, reverse=True)
        return candidates

    # ------------------------------------------------------------------

    def extract_candidates(
        self,
        autocorrelation: np.ndarray,
        min_lag: int,
        sr: int,
        periods_seconds: np.ndarray,
        magnitude_spectrum: np.ndarray,
    ) -> List[PeriodicityCandidate]:
        """Extract and merge candidates from both autocorrelation and
        spectral sources.

        Parameters
        ----------
        autocorrelation : np.ndarray
            Normalised autocorrelation array.
        min_lag : int
            Lag offset for the autocorrelation array.
        sr : int
            Sample rate.
        periods_seconds : np.ndarray
            Period axis from spectral analysis.
        magnitude_spectrum : np.ndarray
            Corresponding magnitudes.

        Returns
        -------
        list[PeriodicityCandidate]
            Combined candidates from both sources, sorted by strength
            descending.  Ambiguity is preserved — candidates from
            different sources with similar periods are NOT merged.

        Time complexity
        ---------------
        O(K_auto + K_spec) for extraction, O(M log M) for sorting where
        M = total candidate count.
        """
        ac_candidates = self.extract_from_autocorrelation(
            autocorrelation, min_lag, sr,
        )
        sp_candidates = self.extract_from_spectrum(
            periods_seconds, magnitude_spectrum,
        )

        combined = ac_candidates + sp_candidates
        combined.sort(key=lambda c: c.strength, reverse=True)
        return combined


# ---------------------------------------------------------------------------
# Stage 4 — Hypothesis Helpers
# ---------------------------------------------------------------------------


def _generate_groupings(n: int) -> List[List[int]]:
    """Generate all additive meter groupings of *n* beats.

    Groupings consist of ordered sequences from {2, 3} that sum to *n*,
    plus the trivial grouping [n] itself.  These represent standard aksak /
    additive meter patterns used in non-Western and complex Western music.

    Examples::

        >>> _generate_groupings(4)
        [[4], [2, 2]]
        >>> _generate_groupings(7)
        [[7], [2, 2, 3], [2, 3, 2], [3, 2, 2]]

    Time complexity
    ---------------
    O(f(n)) where f(n) = f(n-2) + f(n-3) ≈ O(1.32^n).
    For n ≤ 16, max 37 compositions — negligible.

    Parameters
    ----------
    n : int
        Number of beats to partition.

    Returns
    -------
    list[list[int]]
        All valid groupings, starting with [n].
    """
    if n <= 0:
        return []

    result: List[List[int]] = [[n]]  # trivial grouping always included

    if n < 2:
        return result

    def _compose(remaining: int, current: List[int]) -> None:
        if remaining == 0:
            result.append(current[:])
            return
        if remaining >= 2:
            current.append(2)
            _compose(remaining - 2, current)
            current.pop()
        if remaining >= 3:
            current.append(3)
            _compose(remaining - 3, current)
            current.pop()

    _compose(n, [])
    return result


def _estimate_phase_offset(
    onset_times: np.ndarray,
    period: float,
    resolution: int = PHASE_SEARCH_RESOLUTION,
) -> float:
    """Find the phase offset that minimises total distance to a periodic grid.

    Tests ``resolution`` evenly-spaced phase offsets in [0, period) and
    returns the one that minimises:

        sum_i  min( |t_i - phi| mod T,  T - |t_i - phi| mod T )

    Time complexity
    ---------------
    O(R × N) where R = resolution, N = len(onset_times).
    Fully vectorised via numpy broadcasting — typically < 0.1 ms.

    Numerical stability
    -------------------
    Phase is clamped to [0, T).  Empty onset list returns 0.0.

    Why this finds the best grid alignment
    --------------------------------------
    A periodic grid at phase phi has grid points at phi + k*T.  The
    cost function measures total "off-grid" deviation.  The minimum-cost
    phase aligns the grid as closely as possible with the observed
    onsets.  This is equivalent to finding the circular mean in some
    formulations, but the brute-force approach handles multi-modal
    distributions robustly.
    """
    if len(onset_times) == 0 or period <= 0:
        return 0.0

    phases = np.linspace(0, period, resolution, endpoint=False)
    # (resolution, n_onsets) broadcasting
    residuals = (onset_times[np.newaxis, :] - phases[:, np.newaxis]) % period
    distances = np.minimum(residuals, period - residuals)
    costs = distances.sum(axis=1)
    best_idx = int(np.argmin(costs))
    return float(phases[best_idx])


def _is_harmonic_multiple(
    period_a: float,
    period_b: float,
    tolerance: float = 0.05,
    max_ratio: int = 8,
) -> bool:
    """Check if two periods are related by a simple integer ratio.

    Returns True if period_a / period_b (or vice versa) is within
    *tolerance × k* of an integer k in [2, max_ratio].

    Time complexity: O(max_ratio) — negligible.
    """
    if period_a <= 0 or period_b <= 0:
        return False
    ratio = period_a / period_b if period_a > period_b else period_b / period_a
    for k in range(2, max_ratio + 1):
        if abs(ratio - k) < tolerance * k:
            return True
    return False


# ---------------------------------------------------------------------------
# Stage 4a — Hypothesis Generator
# ---------------------------------------------------------------------------


class HypothesisGenerator:
    """Generates structured meter hypotheses from periodicity candidates.

    For each periodicity peak in a window:

    1. Treat the peak period as a potential beat period.
    2. Test integer multiples 2× through ``MAX_BEAT_COUNT`` as potential
       bar lengths.
    3. Generate all additive grouping vectors ({2,3}-compositions) for
       each beat count.
    4. Estimate optimal phase offset for each hypothesis.
    5. Prune to ``MAX_RAW_HYPOTHESES`` by periodicity strength, then to
       ``MAX_SCORED_HYPOTHESES`` for downstream scoring.

    Parameters
    ----------
    max_period_sec : float
        Upper bound on full-cycle duration.

    Time complexity
    ---------------
    Per window: O(P × B × G × R) where P = peaks, B = beat counts,
    G = groupings per beat count, R = phase resolution.
    With defaults P=6, B≤16, G≤37, R=128, worst case ~455K phase tests.
    In practice the early-termination cap (3 × MAX_RAW) brings this
    down to < 5 ms per window.
    """

    def __init__(
        self,
        max_period_sec: float = MAX_PERIOD_SECONDS_FALLBACK,
    ) -> None:
        self.max_period_sec = max_period_sec

    def generate_for_window(
        self,
        candidates: List[PeriodicityCandidate],
        onset_times: np.ndarray,
        onset_strengths: Optional[np.ndarray] = None,
    ) -> List[MeterHypothesis]:
        """Generate meter hypotheses from periodicity candidates.

        Parameters
        ----------
        candidates : list[PeriodicityCandidate]
            Periodicity peaks for this window (from extraction layer).
        onset_times : np.ndarray
            Onset timestamps (seconds) within this window.
        onset_strengths : np.ndarray or None
            Onset velocities.

        Returns
        -------
        list[MeterHypothesis]
            Up to ``MAX_SCORED_HYPOTHESES`` hypotheses, sorted by
            periodicity_strength descending.

        Time complexity
        ---------------
        O(P × B_eff × G_eff × R + H_raw × log H_raw) where H_raw ≤
        3 × MAX_RAW_HYPOTHESES.  See class docstring.
        """
        if len(candidates) == 0:
            return []

        # Take top peaks by strength
        top_candidates = sorted(
            candidates, key=lambda c: c.strength, reverse=True,
        )[:MAX_PEAKS_PER_WINDOW]

        cap = MAX_RAW_HYPOTHESES * 3  # hard ceiling on raw generation
        raw: List[MeterHypothesis] = []

        for cand in top_candidates:
            period = cand.period_seconds

            for beat_count in range(2, MAX_BEAT_COUNT + 1):
                cycle = period * beat_count
                if cycle > self.max_period_sec:
                    break  # higher beat_counts only make it longer

                groupings = _generate_groupings(beat_count)

                for grouping in groupings:
                    # Phase estimation (vectorised over phase offsets)
                    phase = _estimate_phase_offset(onset_times, period)

                    raw.append(MeterHypothesis(
                        base_period_seconds=period,
                        beat_count=beat_count,
                        grouping_vector=grouping,
                        phase_offset=phase,
                        periodicity_strength=cand.strength,
                    ))

                    if len(raw) >= cap:
                        break
                if len(raw) >= cap:
                    break
            if len(raw) >= cap:
                break

        # Prune: sort by (-strength, simpler meters first)
        raw.sort(key=lambda h: (-h.periodicity_strength, h.beat_count))
        pruned = raw[:MAX_RAW_HYPOTHESES]

        logger.debug(
            f"HypothesisGenerator: {len(raw)} raw → "
            f"{min(len(pruned), MAX_SCORED_HYPOTHESES)} scored"
        )
        return pruned[:MAX_SCORED_HYPOTHESES]


# ---------------------------------------------------------------------------
# Stage 4b — Hypothesis Scorer
# ---------------------------------------------------------------------------


class HypothesisScorer:
    """Probabilistic scoring of meter hypotheses.

    Computes five sub-scores for each hypothesis:

    1. **Accent alignment** — correlation of onset strength with
       predicted strong-beat positions from the grouping vector.
    2. **IOI consistency** — fraction of inter-onset intervals that
       cluster at integer subdivisions of the beat period.
    3. **Prediction error** — mean exponential-decay distance from each
       onset to the nearest predicted grid point.
    4. **Structural repetition** — reward for grouping patterns that
       recur across multiple analysis windows.
    5. **Harmonic penalty** — suppress hypotheses whose period is a
       simple integer multiple of a stronger candidate.

    Final confidence is the weighted geometric mean of sub-scores 1-4
    multiplied by the periodicity strength, with harmonic penalty
    applied as a multiplicative reduction.

    Sub-score 6 (bar accent periodicity) measures whether accent energy
    repeats at the hypothesis beat_count period across the window.

    All sub-scores are normalised to [0, 1].
    """

    def score_hypotheses(
        self,
        hypotheses: List[MeterHypothesis],
        onset_times: np.ndarray,
        onset_strengths: Optional[np.ndarray] = None,
        previous_groupings: Optional[List[List[int]]] = None,
        window_start: float = 0.0,
        window_end: float = 0.0,
    ) -> List[MeterHypothesis]:
        """Score and rank hypotheses.

        Mutates each hypothesis in-place by populating its score fields,
        then returns the list sorted by confidence descending.

        Parameters
        ----------
        hypotheses : list[MeterHypothesis]
            Hypotheses to score.
        onset_times : np.ndarray
            Onset timestamps in the current window.
        onset_strengths : np.ndarray or None
            Onset velocity/strength values.
        previous_groupings : list[list[int]] or None
            Grouping vectors from recent windows (for repetition scoring).
        window_start : float
            Window start time in seconds.
        window_end : float
            Window end time in seconds.

        Returns
        -------
        list[MeterHypothesis]
            Sorted by ``.confidence`` descending.

        Time complexity
        ---------------
        O(H × N) where H = hypotheses, N = onsets.  With H=8, N≈100:
        ~4000 ops total — negligible.
        """
        if len(hypotheses) == 0 or len(onset_times) == 0:
            return hypotheses

        for h in hypotheses:
            h.accent_alignment_score = self._accent_alignment(
                h, onset_times, onset_strengths,
            )
            h.ioi_consistency_score = self._ioi_consistency(
                h, onset_times,
            )
            h.prediction_error_score = self._prediction_error(
                h, onset_times,
            )
            h.structural_repetition_score = self._structural_repetition(
                h, previous_groupings,
            )
            h.bar_accent_periodicity_score = self._bar_accent_periodicity(
                h, onset_times, onset_strengths,
                window_start, window_end,
            )

        # Harmonic penalty requires cross-hypothesis comparison
        self._apply_harmonic_penalties(hypotheses)

        # Final confidence
        for h in hypotheses:
            h.confidence = self._compute_confidence(h)

        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return hypotheses

    # ---- Sub-score implementations ----------------------------------

    def _accent_alignment(
        self,
        h: MeterHypothesis,
        onset_times: np.ndarray,
        onset_strengths: Optional[np.ndarray],
    ) -> float:
        """Correlate hypothesis accent pattern with onset velocity.

        Builds an expected accent template from the grouping vector:
        group boundaries are accented (1.0), internal beats are weak
        (0.4).  For each onset, finds the nearest grid beat and computes
        the product expected × actual, normalised by the maximum possible
        product.

        Time complexity: O(N) per hypothesis.

        Why this works
        --------------
        Strong beats in additive meters carry louder percussive hits.
        If a hypothesis correctly predicts the meter, loud onsets align
        with group boundaries and the normalised product is high.

        Numerical stability
        -------------------
        If all onsets have equal strength (no velocity data), the score
        degrades gracefully to a uniform measure of beat proximity.
        """
        period = h.base_period_seconds
        phase = h.phase_offset
        grouping = h.grouping_vector

        if period <= 0 or len(onset_times) == 0:
            return 0.0

        # Build accent template: group starts = 1.0, others = 0.4
        beat_accents: List[float] = []
        for g in grouping:
            beat_accents.append(1.0)        # group boundary (accented)
            for _ in range(g - 1):
                beat_accents.append(0.4)   # weak beat
        beat_accents[0] = 1.0  # downbeat always strongest

        n_beats = len(beat_accents)
        cycle = period * n_beats
        if cycle <= 0:
            return 0.0

        strengths = (
            onset_strengths
            if onset_strengths is not None
            else np.ones(len(onset_times))
        )

        # Vectorised: position within cycle → nearest beat index
        positions_in_cycle = ((onset_times - phase) % cycle) / period
        nearest_beats = np.round(positions_in_cycle).astype(int) % n_beats

        expected = np.array([beat_accents[b] for b in nearest_beats])

        alignment = float(np.sum(expected * strengths))
        max_possible = float(np.sum(strengths))  # all onsets on strong beats

        if max_possible < 1e-12:
            return 0.0
        return float(np.clip(alignment / max_possible, 0.0, 1.0))

    def _ioi_consistency(
        self,
        h: MeterHypothesis,
        onset_times: np.ndarray,
    ) -> float:
        """Measure how well IOIs cluster around predicted beat period.

        For each inter-onset interval, checks whether it falls within
        ±IOI_TOLERANCE_RATIO of an integer subdivision or multiple of
        the beat period (P/3, P/2, P, 2P, 3P).  Score = fraction of
        IOIs that are consistent.

        Time complexity: O(N) where N = number of onsets.

        Numerical stability
        -------------------
        Short IOIs (< 50 ms) are excluded to avoid flamming / noise.

        Why this detects meter
        ---------------------
        If onsets follow a regular meter, their intervals cluster at
        integer subdivisions of the beat period.  High consistency is
        strong evidence for the hypothesis.
        """
        period = h.base_period_seconds
        if period <= 0 or len(onset_times) < 2:
            return 0.0

        iois = np.diff(onset_times)
        iois = iois[iois > 0.05]  # exclude micro-IOIs
        if len(iois) == 0:
            return 0.0

        # Grid ratios: 1/3, 1/2, 1, 2, 3 of beat period
        grid_periods = period * np.array([1.0 / 3, 0.5, 1.0, 2.0, 3.0])
        tol = IOI_TOLERANCE_RATIO

        # Vectorised: (n_iois, n_grids)
        ratios = iois[:, np.newaxis] / grid_periods[np.newaxis, :]
        fractional_error = np.abs(ratios - np.round(ratios))
        consistent = np.any(fractional_error < tol, axis=1)

        return float(np.mean(consistent))

    def _prediction_error(
        self,
        h: MeterHypothesis,
        onset_times: np.ndarray,
    ) -> float:
        """Score based on proximity of onsets to predicted grid points.

        For each onset, computes the minimum distance to grid point
        (phase + k × period) and applies exponential decay::

            s_i = exp(-d_i / PREDICTION_ERROR_TOLERANCE)

        Returns the mean across onsets.  Higher = onsets are tighter
        to the grid.

        Time complexity: O(N) per hypothesis.

        Why this works
        --------------
        A correct meter hypothesis places grid points near observed
        onsets.  Exponential decay penalises large deviations sharply
        while being tolerant of natural micro-timing.

        Numerical stability
        -------------------
        Distances are non-negative.  exp(0) = 1 for perfect alignment.
        exp(-large) → 0 for gross misalignment.  No overflow risk.
        """
        period = h.base_period_seconds
        phase = h.phase_offset
        if period <= 0 or len(onset_times) == 0:
            return 0.0

        residuals = (onset_times - phase) % period
        distances = np.minimum(residuals, period - residuals)
        scores = np.exp(-distances / PREDICTION_ERROR_TOLERANCE)
        return float(np.mean(scores))

    def _structural_repetition(
        self,
        h: MeterHypothesis,
        previous_groupings: Optional[List[List[int]]],
    ) -> float:
        """Reward grouping patterns that recur across windows.

        Score = fraction of previous windows whose dominant grouping
        matches this hypothesis's grouping vector.

        Time complexity: O(K) where K = number of previous windows.

        Why this works
        --------------
        Real meter rarely changes every bar.  A grouping that persists
        across multiple windows is more likely correct than a transient
        artefact.

        Numerical stability
        -------------------
        Returns 0.5 (neutral prior) when no history is available.
        """
        if previous_groupings is None or len(previous_groupings) == 0:
            return 0.5  # neutral when no history

        matches = sum(
            1 for g in previous_groupings if g == h.grouping_vector
        )
        return float(matches / len(previous_groupings))

    def _bar_accent_periodicity(
        self,
        h: MeterHypothesis,
        onset_times: np.ndarray,
        onset_strengths: Optional[np.ndarray],
        window_start: float,
        window_end: float,
    ) -> float:
        """Measure whether accent energy repeats at the bar period.

        Quantises each onset to the nearest beat index using the
        hypothesis period/phase, builds a per-beat accent strength
        sequence, then computes the Pearson auto-correlation at the
        hypothesis beat_count lag.

        High correlation means accent energy is periodic at the bar
        level — strong evidence for that meter grouping.

        Parameters
        ----------
        h : MeterHypothesis
            The hypothesis whose bar-level periodicity to evaluate.
        onset_times : np.ndarray
            Onset timestamps (may extend beyond window — filtered here).
        onset_strengths : np.ndarray or None
            Per-onset velocity weights.
        window_start : float
            Window start time in seconds.
        window_end : float
            Window end time in seconds.

        Returns
        -------
        float
            Score in [0, 1].  0 if insufficient data.

        Time complexity
        ---------------
        O(N) where N = onsets in window.

        Why this works
        --------------
        In 4/4 time, accent energy peaks every 4 beats (bar boundaries).
        In 2/4, every 2 beats.  The auto-correlation at the bar lag
        captures this periodicity without hardcoding any preference —
        whichever beat_count genuinely repeats its accent pattern wins.
        """
        period = h.base_period_seconds
        if period <= 0 or h.beat_count < 2:
            return 0.0

        # Filter to window
        mask = (onset_times >= window_start) & (onset_times < window_end)
        times = onset_times[mask]
        if onset_strengths is not None:
            strengths = onset_strengths[mask]
        else:
            strengths = np.ones(len(times), dtype=np.float64)

        if len(times) < 4:
            return 0.0

        phase = h.phase_offset

        # Total number of beats spanning the window
        window_dur = window_end - window_start
        n_beats = int(np.ceil(window_dur / period)) + 1
        if n_beats < h.beat_count + 1:
            return 0.0

        # Accumulate accent strength per quantised beat
        beat_accents = np.zeros(n_beats, dtype=np.float64)
        beat_counts_arr = np.zeros(n_beats, dtype=np.float64)

        for t, s in zip(times, strengths):
            bi = (t - window_start - phase) / period
            bi_int = int(round(bi))
            if 0 <= bi_int < n_beats:
                beat_accents[bi_int] += s
                beat_counts_arr[bi_int] += 1.0

        # Normalise: average strength per beat (avoid div by zero)
        for i in range(n_beats):
            if beat_counts_arr[i] > 0:
                beat_accents[i] /= beat_counts_arr[i]

        lag = h.beat_count
        if len(beat_accents) <= lag:
            return 0.0

        a = beat_accents[:-lag]
        b = beat_accents[lag:]

        # Need non-zero variance in both halves
        var_a = np.var(a)
        var_b = np.var(b)
        if var_a < 1e-12 or var_b < 1e-12:
            return 0.0

        corr_matrix = np.corrcoef(a, b)
        corr = float(corr_matrix[0, 1])

        if np.isnan(corr) or corr < 0:
            corr = 0.0

        return min(corr, 1.0)

    def _apply_harmonic_penalties(
        self,
        hypotheses: List[MeterHypothesis],
    ) -> None:
        """Penalise hypotheses whose period is a harmonic of a stronger one.

        For each pair (h_weak, h_strong) where h_strong has higher
        periodicity_strength, if h_weak's period is approximately
        k × h_strong's period (integer k ≥ 2), a penalty proportional
        to ``HARMONIC_PENALTY_FACTOR`` is applied.

        Operates in-place on the ``.harmonic_penalty`` field.

        Time complexity: O(H²) — with H ≤ 8, that's 64 comparisons.

        Why this works
        --------------
        If a strong periodicity exists at period P, autocorrelation also
        peaks at 2P, 3P, 4P.  These are artefactual harmonics, not
        independent evidence.  Penalising them prevents the inference
        from being dominated by echoes.
        """
        by_strength = sorted(
            hypotheses,
            key=lambda h: h.periodicity_strength,
            reverse=True,
        )

        for i, h_weak in enumerate(by_strength):
            max_penalty = 0.0
            for h_strong in by_strength[:i]:
                if _is_harmonic_multiple(
                    h_weak.base_period_seconds,
                    h_strong.base_period_seconds,
                ):
                    if h_weak.periodicity_strength > 1e-12:
                        ratio = (
                            h_strong.periodicity_strength
                            / h_weak.periodicity_strength
                        )
                        penalty = HARMONIC_PENALTY_FACTOR * min(ratio, 1.0)
                        max_penalty = max(max_penalty, penalty)
            h_weak.harmonic_penalty = max_penalty

    def _compute_confidence(
        self,
        h: MeterHypothesis,
    ) -> float:
        """Weighted geometric mean of sub-scores.

        ::

            confidence = prod(s_i ^ w_i)  ×  (1 - harmonic_penalty)

        where w_i are the tunable weights and s_i are the sub-scores.
        Scores are floored at 1e-6 to prevent a single zero from
        collapsing the entire product.

        Time complexity: O(1).

        Numerical stability
        -------------------
        Computed in log-space to prevent underflow::

            log(confidence) = sum(w_i × log(max(s_i, floor)))
        """
        floor = 1e-6
        scores_weights = [
            (max(h.periodicity_strength, floor), SCORING_WEIGHT_PERIODICITY),
            (max(h.accent_alignment_score, floor), SCORING_WEIGHT_ACCENT),
            (max(h.ioi_consistency_score, floor), SCORING_WEIGHT_IOI),
            (max(h.prediction_error_score, floor), SCORING_WEIGHT_PREDICTION),
            (max(h.structural_repetition_score, floor), SCORING_WEIGHT_REPETITION),
            (max(h.bar_accent_periodicity_score, floor), SCORING_WEIGHT_BAR_ACCENT),
        ]

        log_product = sum(w * np.log(s) for s, w in scores_weights)
        raw_confidence = float(np.exp(log_product))

        penalised = raw_confidence * (1.0 - h.harmonic_penalty)
        return float(np.clip(penalised, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Stage 4c — Hypothesis Tracker
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Stage 4b — Hierarchical Resolver
# ---------------------------------------------------------------------------


class HierarchicalResolver:
    """Promote structurally meaningful meters over harmonic subdivisions.

    After hypothesis scoring and before dominance tracking, this stage
    groups hypotheses into harmonic families and promotes longer-period
    hypotheses when they are structurally consistent and nearly as
    confident as their shorter-period relatives.

    Musical principle: if 2/4 and 4/4 both explain the data well, the
    4/4 grouping is structurally richer (phrase-level structure) and
    should be preferred.  But only if the evidence supports it — no
    forced promotion.

    This stage does NOT re-run scoring or modify scoring weights.  It
    applies a one-pass structural adjustment only.
    """

    # Harmonic ratio tolerance
    RATIO_TOLERANCE: float = 0.05
    # Allowed integer ratios for harmonic family membership
    ALLOWED_RATIOS: tuple = (2, 3, 4)

    # Promotion thresholds
    CONFIDENCE_RATIO: float = 0.85
    ACCENT_RATIO: float = 0.9
    PROMOTION_BOOST: float = 1.05
    SUBDIVISION_DAMPEN: float = 0.90

    def resolve(
        self, hypotheses: List[MeterHypothesis],
    ) -> List[MeterHypothesis]:
        """Apply hierarchical promotion to a list of scored hypotheses.

        Parameters
        ----------
        hypotheses : list[MeterHypothesis]
            Scored hypotheses for a single window (confidence already set).

        Returns
        -------
        list[MeterHypothesis]
            Same list with confidence adjusted for promoted hypotheses.
            No hypotheses are added or removed.
        """
        if len(hypotheses) < 2:
            return hypotheses

        families = self._group_harmonic_families(hypotheses)

        for family in families:
            if len(family) < 2:
                continue
            self._promote_within_family(family)

        # Re-sort by confidence descending after adjustments
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return hypotheses

    def _group_harmonic_families(
        self, hypotheses: List[MeterHypothesis],
    ) -> List[List[MeterHypothesis]]:
        """Group hypotheses into harmonic families by period relationship.

        Two hypotheses belong to the same family if the ratio of their
        cycle durations is close to an integer in {2, 3, 4}.

        Uses union-find grouping: if A~B and B~C then {A,B,C} are one
        family.

        Returns
        -------
        list[list[MeterHypothesis]]
            Each inner list contains ≥1 harmony-related hypotheses,
            sorted by cycle_seconds ascending (shortest first).
        """
        n = len(hypotheses)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(n):
            for j in range(i + 1, n):
                ci = hypotheses[i].cycle_seconds
                cj = hypotheses[j].cycle_seconds
                if ci <= 0 or cj <= 0:
                    continue
                larger = max(ci, cj)
                smaller = min(ci, cj)
                ratio = larger / smaller
                rounded = round(ratio)
                if (
                    rounded in self.ALLOWED_RATIOS
                    and abs(ratio - rounded) < self.RATIO_TOLERANCE
                ):
                    union(i, j)

        # Collect groups
        groups: Dict[int, List[MeterHypothesis]] = {}
        for i, h in enumerate(hypotheses):
            root = find(i)
            groups.setdefault(root, []).append(h)

        # Sort each family by cycle_seconds ascending
        for g in groups.values():
            g.sort(key=lambda h: h.cycle_seconds)

        return list(groups.values())

    def _promote_within_family(
        self, family: List[MeterHypothesis],
    ) -> None:
        """Apply structural promotion within a harmonic family.

        For each pair (shorter, longer) where longer.cycle is an
        integer multiple of shorter.cycle, promote the longer if:

        1. longer.confidence >= shorter.confidence * 0.85
        2. longer.structural_repetition_score >= shorter.structural_repetition_score
        3. longer.accent_alignment_score >= shorter.accent_alignment_score * 0.9

        On promotion:
        - longer.confidence *= 1.05 (capped at 1.0)
        - shorter.confidence *= 0.90
        - longer.structural_preferred = True
        - longer.promoted_from_subdivision = True
        """
        # The family is sorted by cycle_seconds ascending.
        # Try promoting from smallest to largest.
        for i in range(len(family)):
            shorter = family[i]
            for j in range(i + 1, len(family)):
                longer = family[j]

                # Verify they are actually in harmonic relationship
                if shorter.cycle_seconds <= 0:
                    continue
                ratio = longer.cycle_seconds / shorter.cycle_seconds
                rounded = round(ratio)
                if (
                    rounded not in self.ALLOWED_RATIOS
                    or abs(ratio - rounded) >= self.RATIO_TOLERANCE
                ):
                    continue

                # Check promotion criteria
                if longer.confidence < shorter.confidence * self.CONFIDENCE_RATIO:
                    continue
                if longer.structural_repetition_score < shorter.structural_repetition_score:
                    continue
                if longer.accent_alignment_score < shorter.accent_alignment_score * self.ACCENT_RATIO:
                    continue

                # Promote
                longer.confidence = min(
                    1.0, longer.confidence * self.PROMOTION_BOOST,
                )
                shorter.confidence *= self.SUBDIVISION_DAMPEN
                longer.structural_preferred = True
                longer.promoted_from_subdivision = True

                logger.debug(
                    f"Hierarchical promotion: {longer.beat_count}/{longer.grouping_vector} "
                    f"promoted over {shorter.beat_count}/{shorter.grouping_vector} "
                    f"(ratio={rounded}x, conf={longer.confidence:.3f} vs {shorter.confidence:.3f})"
                )


class HypothesisTracker:
    """Temporal tracking of meter hypotheses across sliding windows.

    Maintains a running state of top-K hypotheses with exponential
    moving average (EMA) confidence smoothing, multiplicative decay for
    absent hypotheses, modulation detection, ambiguity flagging, and
    polyrhythm identification.

    State is maintained internally — call :meth:`process_window` for
    each successive window in chronological order.

    Parameters
    ----------
    top_k : int
        Number of top hypotheses to maintain.
    alpha : float
        EMA smoothing coefficient (higher = more reactive to current
        window, lower = more stable).
    decay : float
        Per-window multiplicative confidence decay for non-detected
        hypotheses.
    modulation_margin : float
        Confidence gap required for a new dominant to trigger a
        modulation event.
    ambiguity_delta : float
        If top-2 hypotheses are within this margin, the window is
        marked ambiguous.

    Time complexity
    ---------------
    :meth:`process_window` is O(H + K + P²) per call where H = scored
    hypotheses, K = tracked keys, P = strong hypotheses for polyrhythm
    checking.  All O(1) for typical sizes.
    """

    # Modulation must persist for this many consecutive windows
    MODULATION_PERSISTENCE_WINDOWS: int = 2

    def __init__(
        self,
        top_k: int = TOP_K_TRACKER,
        alpha: float = SMOOTHING_ALPHA,
        decay: float = DECAY_RATE,
        modulation_margin: float = MODULATION_MARGIN,
        ambiguity_delta: float = AMBIGUITY_DELTA,
    ) -> None:
        self.top_k = top_k
        self.alpha = alpha
        self.decay = decay
        self.modulation_margin = modulation_margin
        self.ambiguity_delta = ambiguity_delta

        # Internal state
        self._smoothed: Dict[str, float] = {}       # key → smoothed confidence
        self._prev_dominant_key: Optional[str] = None
        self._prev_dominant: Optional[MeterHypothesis] = None
        self._modulation_events: List[ModulationEvent] = []
        self._grouping_history: List[List[int]] = []
        # (key_a, key_b) → tracking dict
        self._poly_buffer: Dict[Tuple[str, str], dict] = {}
        # Modulation persistence: require new dominant to hold for N windows
        self._candidate_modulation_key: Optional[str] = None
        self._candidate_modulation_hyp: Optional[MeterHypothesis] = None
        self._candidate_modulation_counter: int = 0
        self._candidate_modulation_time: float = 0.0
        self._candidate_modulation_delta: float = 0.0

    @property
    def grouping_history(self) -> List[List[int]]:
        """Read-only access to recent dominant grouping vectors."""
        return self._grouping_history

    @property
    def modulation_events(self) -> List[ModulationEvent]:
        """Accumulated modulation events."""
        return self._modulation_events

    def process_window(
        self,
        window_start: float,
        window_end: float,
        scored_hypotheses: List[MeterHypothesis],
    ) -> WindowInferenceResult:
        """Process a single window's scored hypotheses.

        1. Apply EMA smoothing to confidence values.
        2. Decay absent hypotheses.
        3. Determine dominant hypothesis (highest smoothed confidence).
        4. Detect modulation events (dominant change with margin).
        5. Flag ambiguous windows (top-2 within delta).
        6. Update polyrhythm tracking buffer.
        7. Append dominant grouping to history.

        Parameters
        ----------
        window_start : float
            Window start time in seconds.
        window_end : float
            Window end time in seconds.
        scored_hypotheses : list[MeterHypothesis]
            Hypotheses sorted by confidence descending (from scorer).

        Returns
        -------
        WindowInferenceResult

        Time complexity
        ---------------
        O(H + K) where H = len(scored_hypotheses), K = tracked keys.
        Polyrhythm buffer update is O(H²) but H ≤ 8.
        """
        # --- Step 1: EMA smoothing ---
        current_keys: set = set()
        for h in scored_hypotheses:
            key = h.hypothesis_key
            current_keys.add(key)
            prev = self._smoothed.get(key, h.confidence)
            smoothed = self.alpha * h.confidence + (1 - self.alpha) * prev
            self._smoothed[key] = smoothed
            h.stability_score = smoothed

        # --- Step 2: Decay absent hypotheses ---
        for key in list(self._smoothed.keys()):
            if key not in current_keys:
                self._smoothed[key] *= self.decay
                if self._smoothed[key] < 0.01:
                    del self._smoothed[key]

        # --- Step 3: Determine dominant ---
        if scored_hypotheses:
            scored_hypotheses.sort(
                key=lambda h: h.stability_score, reverse=True,
            )
            dominant = scored_hypotheses[0]
        else:
            dominant = None

        # --- Step 4: Modulation detection with persistence ---
        modulation_flag = False
        if dominant is not None:
            dom_key = dominant.hypothesis_key
            if (
                self._prev_dominant_key is not None
                and dom_key != self._prev_dominant_key
            ):
                prev_smoothed = self._smoothed.get(
                    self._prev_dominant_key, 0.0,
                )
                delta = dominant.stability_score - prev_smoothed
                if delta > self.modulation_margin:
                    # New candidate for modulation — require persistence
                    if self._candidate_modulation_key == dom_key:
                        self._candidate_modulation_counter += 1
                    else:
                        # New candidate, reset counter
                        self._candidate_modulation_key = dom_key
                        self._candidate_modulation_hyp = dominant
                        self._candidate_modulation_counter = 1
                        self._candidate_modulation_time = window_start
                        self._candidate_modulation_delta = delta

                    # Only emit modulation after persistence threshold
                    if self._candidate_modulation_counter >= self.MODULATION_PERSISTENCE_WINDOWS:
                        modulation_flag = True
                        self._modulation_events.append(ModulationEvent(
                            time=self._candidate_modulation_time,
                            from_hypothesis=self._prev_dominant,
                            to_hypothesis=self._candidate_modulation_hyp or dominant,
                            confidence_delta=self._candidate_modulation_delta,
                        ))
                        logger.info(
                            f"Modulation at {self._candidate_modulation_time:.2f}s: "
                            f"{self._prev_dominant_key} -> {dom_key} "
                            f"(delta={self._candidate_modulation_delta:.3f}, "
                            f"persisted {self._candidate_modulation_counter} windows)"
                        )
                        # Reset candidate after emission
                        self._candidate_modulation_key = None
                        self._candidate_modulation_hyp = None
                        self._candidate_modulation_counter = 0
                else:
                    # Delta below margin — reset candidate
                    self._candidate_modulation_key = None
                    self._candidate_modulation_counter = 0
            else:
                # Same dominant — reset candidate
                self._candidate_modulation_key = None
                self._candidate_modulation_counter = 0

            self._prev_dominant_key = dom_key
            self._prev_dominant = dominant

        # --- Step 5: Ambiguity check ---
        ambiguity_flag = False
        if len(scored_hypotheses) >= 2:
            top2_delta = abs(
                scored_hypotheses[0].stability_score
                - scored_hypotheses[1].stability_score
            )
            if top2_delta < self.ambiguity_delta:
                ambiguity_flag = True

        # --- Step 6: Polyrhythm tracking ---
        self._update_polyrhythm_buffer(
            scored_hypotheses, window_start, window_end,
        )

        # --- Step 7: Update grouping history ---
        if dominant is not None:
            self._grouping_history.append(dominant.grouping_vector)
            if len(self._grouping_history) > 20:
                self._grouping_history = self._grouping_history[-20:]

        competing = (
            scored_hypotheses[1:self.top_k]
            if len(scored_hypotheses) > 1
            else []
        )

        return WindowInferenceResult(
            start_time=window_start,
            end_time=window_end,
            dominant_hypothesis=dominant,
            competing_hypotheses=competing,
            ambiguity_flag=ambiguity_flag,
            modulation_flag=modulation_flag,
        )

    def _update_polyrhythm_buffer(
        self,
        hypotheses: List[MeterHypothesis],
        window_start: float,
        window_end: float,
    ) -> None:
        """Track pairs of non-harmonic hypotheses exceeding confidence floor.

        Two hypotheses form a polyrhythm candidate if:

        - Their periods are NOT related by an integer ratio.
        - Both exceed ``POLYRHYTHM_CONFIDENCE_FLOOR``.
        - They co-occur in multiple consecutive windows.

        Time complexity: O(H²) per window — with H ≤ 8, that's 28 pairs.
        """
        strong = [
            h for h in hypotheses
            if h.stability_score >= POLYRHYTHM_CONFIDENCE_FLOOR
        ]

        active_pairs: set = set()
        for i in range(len(strong)):
            for j in range(i + 1, len(strong)):
                a, b = strong[i], strong[j]
                # Skip pairs with nearly equal periods (same periodicity,
                # different interpretation — not a true polyrhythm)
                if abs(a.base_period_seconds - b.base_period_seconds) < 0.02:
                    continue
                if not _is_harmonic_multiple(
                    a.base_period_seconds, b.base_period_seconds,
                ):
                    pair_key = tuple(
                        sorted([a.hypothesis_key, b.hypothesis_key])
                    )
                    active_pairs.add(pair_key)

                    if pair_key not in self._poly_buffer:
                        self._poly_buffer[pair_key] = {
                            "period_a": a.base_period_seconds,
                            "period_b": b.base_period_seconds,
                            "conf_a_sum": 0.0,
                            "conf_b_sum": 0.0,
                            "count": 0,
                            "first_time": window_start,
                            "last_time": window_end,
                            "consecutive": 0,
                        }

                    buf = self._poly_buffer[pair_key]
                    buf["conf_a_sum"] += a.stability_score
                    buf["conf_b_sum"] += b.stability_score
                    buf["count"] += 1
                    buf["last_time"] = window_end
                    buf["consecutive"] += 1

        # Reset consecutive counter for pairs not seen this window
        for key in list(self._poly_buffer.keys()):
            if key not in active_pairs:
                self._poly_buffer[key]["consecutive"] = 0

    def get_polyrhythms(self) -> List[PolyrhythmLayer]:
        """Extract confirmed polyrhythmic layers.

        A pair qualifies if it has been observed in at least
        ``POLYRHYTHM_PERSISTENCE_WINDOWS`` consecutive windows at some
        point during tracking.

        Returns
        -------
        list[PolyrhythmLayer]
            Sorted by combined mean confidence descending.
        """
        layers: List[PolyrhythmLayer] = []
        for (_key_a, _key_b), buf in self._poly_buffer.items():
            if buf["count"] >= POLYRHYTHM_PERSISTENCE_WINDOWS:
                pa = buf["period_a"]
                pb = buf["period_b"]
                ratio = (
                    max(pa, pb) / min(pa, pb) if min(pa, pb) > 0 else 0.0
                )
                layers.append(PolyrhythmLayer(
                    period_a_seconds=pa,
                    period_b_seconds=pb,
                    period_ratio=ratio,
                    first_window_time=buf["first_time"],
                    last_window_time=buf["last_time"],
                    window_count=buf["count"],
                    mean_confidence_a=buf["conf_a_sum"] / buf["count"],
                    mean_confidence_b=buf["conf_b_sum"] / buf["count"],
                ))

        layers.sort(
            key=lambda l: l.mean_confidence_a + l.mean_confidence_b,
            reverse=True,
        )
        return layers


# ---------------------------------------------------------------------------
# Top-level public API
# ---------------------------------------------------------------------------


def analyze_periodicity(
    onset_times: List[float],
    duration_seconds: float,
    sr: int,
    estimated_bpm: Optional[float] = None,
    onset_strengths: Optional[List[float]] = None,
    analysis_sr: int = DEFAULT_ANALYSIS_SR,
    resolutions: Optional[List[dict]] = None,
) -> PeriodicityResult:
    """Full periodicity extraction pipeline.

    This is the primary entry point for the metrical inference stage.
    It builds the impulse train, downsamples for efficiency, runs global
    analysis and multi-resolution sliding windows, and returns the
    complete set of periodicity candidates.

    Parameters
    ----------
    onset_times : list[float]
        Onset timestamps in seconds (sample-level precision from the
        signal stage).
    duration_seconds : float
        Total audio duration.
    sr : int
        Original sample rate (for the impulse train).
    estimated_bpm : float or None
        If known, constrains the maximum detectable period.
    onset_strengths : list[float] or None
        Optional velocity weighting for impulses.
    analysis_sr : int
        Internal FFT sample rate (default 1000 Hz).
    resolutions : list[dict] or None
        Sliding-window resolutions (default: 4 tiers from 2 s to 16 s).

    Returns
    -------
    PeriodicityResult
        Contains global candidates and per-window candidates at all
        resolutions.

    Computational complexity (5-min song, 500 onsets, sr=44100)
    -----------------------------------------------------------
    - Impulse train construction: O(500) — negligible
    - Downsampling 44100→1000: O(13.2M) — ~10 ms
    - Global autocorrelation: O(600K log 600K) — ~30 ms
    - Global spectrum: O(300K log 300K) — ~20 ms
    - Sliding windows (4 resolutions): O(53M) — ~150 ms
    - Total: ~200 ms

    Potential failure modes
    ----------------------
    - **Rubato / ad-lib sections**: No stable periodicity exists.  All
      candidates will be low-strength.  Downstream must interpret weak
      evidence as absence of meter, not wrong meter.
    - **Blast beats (> 300 BPM)**: At 300 BPM, the beat period is 0.2 s.
      The 0.1 s floor allows detection but the autocorrelation may show
      a flat ridge rather than a sharp peak due to near-continuous onsets.
    - **Polymeter (e.g. 4/4 vs 7/8)**: Both periodicities should appear
      as peaks in the autocorrelation and spectrum.  The sliding window
      captures which period dominates locally.
    - **Very sparse sections (< 4 onsets in a window)**: Autocorrelation
      is noisy with few impulses.  The energy floor filter handles this
      gracefully — few or no candidates survive.
    """
    if len(onset_times) == 0:
        logger.warning("analyze_periodicity called with 0 onsets")
        return PeriodicityResult(
            impulse_train_sr=sr,
            analysis_sr=analysis_sr,
            duration_seconds=duration_seconds,
        )

    # --- Step 1: Build impulse train at full SR ---
    impulse_full = build_onset_impulse_train(
        onset_times=onset_times,
        duration_seconds=duration_seconds,
        sr=sr,
        weight_by_velocity=onset_strengths,
    )

    # --- Step 2: Downsample for analysis ---
    impulse_analysis = _downsample_impulse_train(
        impulse_full, source_sr=sr, target_sr=analysis_sr,
    )

    logger.info(
        f"Periodicity analysis: {len(onset_times)} onsets, "
        f"{duration_seconds:.1f}s, analysis signal {len(impulse_analysis)} "
        f"samples @ {analysis_sr} Hz"
    )

    # --- Step 3: Analyzer ---
    analyzer = MultiResolutionAnalyzer(
        analysis_sr=analysis_sr,
        estimated_bpm=estimated_bpm,
    )

    # Global autocorrelation
    min_lag_global = max(1, int(round(MIN_PERIOD_SECONDS * analysis_sr)))
    max_lag_global = min(
        len(impulse_analysis) - 1,
        int(round(_max_period_from_tempo(estimated_bpm) * analysis_sr)),
    )

    autocorr_global = analyzer.compute_autocorrelation(
        impulse_analysis, min_lag_global, max_lag_global,
    )

    # Global spectral periodicity
    periods_global, mags_global = analyzer.compute_periodicity_spectrum(
        impulse_analysis, analysis_sr,
    )

    # --- Step 4: Global peak extraction ---
    extractor = PeriodicityExtractor(
        min_period_sec=MIN_PERIOD_SECONDS,
        max_period_sec=_max_period_from_tempo(estimated_bpm),
    )

    global_candidates = extractor.extract_candidates(
        autocorrelation=autocorr_global,
        min_lag=min_lag_global,
        sr=analysis_sr,
        periods_seconds=periods_global,
        magnitude_spectrum=mags_global,
    )

    logger.info(
        f"Global periodicity: {len(global_candidates)} candidates "
        f"(autocorrelation + spectrum)"
    )

    # --- Step 5: Multi-resolution sliding windows ---
    used_resolutions = resolutions or analyzer.DEFAULT_RESOLUTIONS
    window_results = analyzer.analyze_multi_resolution(
        impulse_analysis, analysis_sr, resolutions=used_resolutions,
    )

    return PeriodicityResult(
        impulse_train_sr=sr,
        analysis_sr=analysis_sr,
        duration_seconds=duration_seconds,
        global_candidates=global_candidates,
        window_results=window_results,
        resolutions_used=used_resolutions,
    )


def run_metrical_inference(
    onset_times: List[float],
    duration_seconds: float,
    sr: int,
    estimated_bpm: Optional[float] = None,
    onset_strengths: Optional[List[float]] = None,
    analysis_sr: int = DEFAULT_ANALYSIS_SR,
    inference_window_seconds: float = 4.0,
    inference_hop_seconds: float = 1.0,
) -> InferenceResult:
    """Full metrical inference pipeline: periodicity -> hypotheses -> tracking.

    This is the primary entry point for structured meter inference.
    It runs periodicity extraction at the specified inference resolution,
    generates and scores meter hypotheses for each window, tracks
    them temporally, and detects modulations and polyrhythms.

    Parameters
    ----------
    onset_times : list[float]
        Onset timestamps in seconds (sample-level precision from the
        signal stage).
    duration_seconds : float
        Total audio duration.
    sr : int
        Original sample rate.
    estimated_bpm : float or None
        If known, constrains the period search space.
    onset_strengths : list[float] or None
        Per-onset velocity weighting.
    analysis_sr : int
        Internal FFT sample rate (default 1000 Hz).
    inference_window_seconds : float
        Window duration for the inference-resolution tier (default 4 s).
    inference_hop_seconds : float
        Hop duration for the inference-resolution tier (default 1 s).

    Returns
    -------
    InferenceResult
        Complete inference output with per-window results, modulation
        events, and polyrhythm layers.

    Computational complexity (5-min song, 500 onsets)
    -------------------------------------------------
    - Periodicity extraction at 1 resolution: ~80 ms
    - Hypothesis generation: ~5 ms x 297 windows = ~1.5 s
    - Scoring: ~2 ms x 297 = ~0.6 s
    - Tracking: O(W) negligible
    - Total: ~2-3 s

    Potential failure modes
    ----------------------
    - **No dominant meter**: All hypotheses low-confidence ->
      ``global_dominant`` is the best available (may be weak).
    - **Blast beat section**: Dense onsets -> many weak candidates,
      similar strength.  Tracker ambiguity flag will be True.
    - **Metric modulation**: New dominant overtakes previous ->
      ``ModulationEvent`` recorded.  Previous dominant decays.
    - **Polymeter**: Two non-harmonic candidates persist ->
      ``PolyrhythmLayer`` detected and stored separately.
    - **Very sparse data**: Few onsets per window -> few/no hypotheses
      generated.  ``WindowInferenceResult.dominant_hypothesis = None``.
    """
    if len(onset_times) == 0:
        return InferenceResult(duration_seconds=duration_seconds)

    ot = np.asarray(onset_times, dtype=np.float64)
    os_arr = (
        np.asarray(onset_strengths, dtype=np.float64)
        if onset_strengths is not None
        else None
    )

    # --- Step 1: Periodicity extraction at inference resolution ---
    inference_resolutions = [
        {
            "window_seconds": inference_window_seconds,
            "hop_seconds": inference_hop_seconds,
        },
    ]

    periodicity_result = analyze_periodicity(
        onset_times=onset_times,
        duration_seconds=duration_seconds,
        sr=sr,
        estimated_bpm=estimated_bpm,
        onset_strengths=onset_strengths,
        analysis_sr=analysis_sr,
        resolutions=inference_resolutions,
    )

    # --- Step 2: Setup ---
    max_period = _max_period_from_tempo(estimated_bpm)
    generator = HypothesisGenerator(max_period_sec=max_period)
    scorer = HypothesisScorer()
    resolver = HierarchicalResolver()
    tracker = HypothesisTracker()

    window_inferences: List[WindowInferenceResult] = []

    # --- Step 3: Per-window inference ---
    for wpr in periodicity_result.window_results:
        # Filter onset_times to this window
        mask = (ot >= wpr.start_time) & (ot < wpr.end_time)
        window_onsets = ot[mask]
        window_strengths = os_arr[mask] if os_arr is not None else None

        # Generate hypotheses
        hypotheses = generator.generate_for_window(
            candidates=wpr.periodicity_peaks,
            onset_times=window_onsets,
            onset_strengths=window_strengths,
        )

        # Score hypotheses
        prev_groupings = tracker.grouping_history[-10:] or None
        scored = scorer.score_hypotheses(
            hypotheses=hypotheses,
            onset_times=window_onsets,
            onset_strengths=window_strengths,
            previous_groupings=prev_groupings,
            window_start=wpr.start_time,
            window_end=wpr.end_time,
        )

        # Hierarchical resolution — promote structural meters
        scored = resolver.resolve(scored)

        # Track
        win_result = tracker.process_window(
            window_start=wpr.start_time,
            window_end=wpr.end_time,
            scored_hypotheses=scored,
        )

        window_inferences.append(win_result)

    # --- Step 4: Global dominant ---
    global_dominant: Optional[MeterHypothesis] = None
    best_stability = 0.0
    for wi in window_inferences:
        if (
            wi.dominant_hypothesis is not None
            and wi.dominant_hypothesis.stability_score > best_stability
        ):
            best_stability = wi.dominant_hypothesis.stability_score
            global_dominant = wi.dominant_hypothesis

    # --- Step 5: Polyrhythms ---
    polyrhythms = tracker.get_polyrhythms()

    logger.info(
        f"Metrical inference complete: {len(window_inferences)} windows, "
        f"{len(tracker.modulation_events)} modulations, "
        f"{len(polyrhythms)} polyrhythm layers"
    )

    return InferenceResult(
        window_inferences=window_inferences,
        detected_modulations=tracker.modulation_events,
        persistent_polyrhythms=polyrhythms,
        global_dominant=global_dominant,
        duration_seconds=duration_seconds,
    )
