"""
Hit Stage — Multi-feature drum hit classification.

For each detected onset on the isolated drum stem, extract a feature vector
and classify the hit as kick, snare, hi-hat (closed/open), tom, or cymbal.

Feature extraction per transient:
  - Spectral centroid (brightness)
  - Spectral bandwidth (spread)
  - Zero-crossing rate (noisiness)
  - Low/mid/high band energy ratios
  - 13-coefficient MFCC snapshot

Classification approach:
  1. Heuristic fallback (band-energy rules) — always available.
  2. Logistic regression / random forest — when a trained model exists.

The heuristic fallback is musically grounded:
  - Kick: dominant energy 40-200 Hz, low centroid
  - Snare: mid energy 200-5kHz + high-freq noise (snare wires)
  - Hi-hat closed: high centroid, narrow bandwidth, very short
  - Hi-hat open: high centroid, wider bandwidth, longer sustain
  - Tom: mid-low energy 80-400 Hz, moderate centroid
  - Cymbal (crash/ride): high centroid, wide bandwidth, long sustain
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

import numpy as np
import librosa

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums + Data Types
# ---------------------------------------------------------------------------


class HitType(str, Enum):
    KICK = "kick"
    SNARE = "snare"
    HIHAT_CLOSED = "hihat_closed"
    HIHAT_OPEN = "hihat_open"
    TOM = "tom"
    CYMBAL = "cymbal"
    UNKNOWN = "unknown"


# GM Drum Map MIDI note numbers
GM_DRUM_MAP = {
    HitType.KICK: 36,
    HitType.SNARE: 38,
    HitType.HIHAT_CLOSED: 42,
    HitType.HIHAT_OPEN: 46,
    HitType.TOM: 47,         # Mid tom (low=41, mid=47, high=50)
    HitType.CYMBAL: 49,      # Crash
    HitType.UNKNOWN: 38,     # Default to snare
}


@dataclass
class HitFeatures:
    """Raw feature vector for one drum hit."""
    spectral_centroid: float = 0.0
    spectral_bandwidth: float = 0.0
    zero_crossing_rate: float = 0.0
    energy_low: float = 0.0       # 20-200 Hz
    energy_mid: float = 0.0       # 200-3000 Hz
    energy_high: float = 0.0      # 3000-20000 Hz
    energy_ratio_low: float = 0.0
    energy_ratio_mid: float = 0.0
    energy_ratio_high: float = 0.0
    mfcc: list[float] = field(default_factory=list)  # 13 coefficients
    rms: float = 0.0
    duration_ms: float = 0.0

    def to_vector(self) -> np.ndarray:
        """Convert to flat numpy array for ML classifiers."""
        return np.array([
            self.spectral_centroid,
            self.spectral_bandwidth,
            self.zero_crossing_rate,
            self.energy_ratio_low,
            self.energy_ratio_mid,
            self.energy_ratio_high,
            self.rms,
            self.duration_ms,
        ] + self.mfcc)


@dataclass
class DrumHit:
    """A classified drum hit."""
    time: float                   # seconds (sample-level precision)
    sample_index: int
    hit_type: HitType
    confidence: float             # 0–1
    velocity: int                 # MIDI velocity 0–127
    midi_note: int
    features: Optional[HitFeatures] = None

    def to_dict(self) -> dict:
        return {
            "time": self.time,
            "sample_index": self.sample_index,
            "hit_type": self.hit_type.value,
            "confidence": round(self.confidence, 3),
            "velocity": self.velocity,
            "midi_note": self.midi_note,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_hits(
    y_drums: np.ndarray,
    sr: int,
    onset_times: list[float],
    onset_sample_indices: list[int],
    onset_strengths: list[float],
    window_ms: float = 50.0,
    model_path: Optional[str] = None,
) -> list[DrumHit]:
    """
    Classify each detected onset into a drum hit type.

    Parameters
    ----------
    y_drums : np.ndarray
        Mono drum stem waveform.
    sr : int
        Sample rate.
    onset_times : list[float]
        Onset timestamps (seconds).
    onset_sample_indices : list[int]
        Onset sample indices.
    onset_strengths : list[float]
        Onset strength values.
    window_ms : float
        Analysis window around each onset (ms).
    model_path : str, optional
        Path to a trained sklearn classifier (joblib).
        If None, uses heuristic fallback.

    Returns
    -------
    list[DrumHit]
    """
    window_samples = int(sr * window_ms / 1000)
    hits: list[DrumHit] = []

    # Try to load ML classifier
    classifier = None
    if model_path:
        classifier = _load_classifier(model_path)

    # Global onset strength stats for velocity mapping
    if onset_strengths:
        str_arr = np.array(onset_strengths)
        str_max = float(str_arr.max()) if str_arr.max() > 0 else 1.0
    else:
        str_max = 1.0

    for i, (t, si, strength) in enumerate(
        zip(onset_times, onset_sample_indices, onset_strengths)
    ):
        # Extract analysis window
        start = max(0, si)
        end = min(len(y_drums), si + window_samples)

        if end - start < 32:
            continue

        segment = y_drums[start:end]

        # Extract features
        features = _extract_features(segment, sr)

        # Classify
        if classifier is not None:
            hit_type, conf = _classify_ml(features, classifier)
        else:
            hit_type, conf = _classify_heuristic(features)

        # Map onset strength → MIDI velocity (1–127)
        velocity = max(1, min(127, int((strength / str_max) * 127)))

        midi_note = GM_DRUM_MAP.get(hit_type, 38)

        hits.append(DrumHit(
            time=t,
            sample_index=si,
            hit_type=hit_type,
            confidence=conf,
            velocity=velocity,
            midi_note=midi_note,
            features=features,
        ))

    logger.info(
        f"Hit classification: {len(hits)} hits "
        f"({_summarize_hits(hits)})"
    )
    return hits


# ---------------------------------------------------------------------------
# Feature Extraction
# ---------------------------------------------------------------------------


def _extract_features(segment: np.ndarray, sr: int) -> HitFeatures:
    """
    Extract multi-dimensional feature vector from a single onset window.
    """
    n_fft = min(2048, len(segment))
    if n_fft < 64:
        return HitFeatures()

    # Spectral features
    S = np.abs(librosa.stft(segment, n_fft=n_fft))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    # Spectral centroid
    centroid = float(librosa.feature.spectral_centroid(
        S=S, sr=sr
    ).mean())

    # Spectral bandwidth
    bandwidth = float(librosa.feature.spectral_bandwidth(
        S=S, sr=sr
    ).mean())

    # Zero-crossing rate
    zcr = float(librosa.feature.zero_crossing_rate(segment).mean())

    # Band energy decomposition
    S_power = S ** 2
    total_energy = np.sum(S_power) + 1e-12

    low_mask = (freqs >= 20) & (freqs < 200)
    mid_mask = (freqs >= 200) & (freqs < 3000)
    high_mask = (freqs >= 3000)

    energy_low = float(np.sum(S_power[low_mask, :]))
    energy_mid = float(np.sum(S_power[mid_mask, :]))
    energy_high = float(np.sum(S_power[high_mask, :]))

    ratio_low = energy_low / total_energy
    ratio_mid = energy_mid / total_energy
    ratio_high = energy_high / total_energy

    # MFCCs (13 coefficients)
    try:
        mfcc = librosa.feature.mfcc(
            S=librosa.power_to_db(S ** 2),
            sr=sr,
            n_mfcc=13
        ).mean(axis=1).tolist()
    except Exception:
        mfcc = [0.0] * 13

    # RMS
    rms = float(np.sqrt(np.mean(segment ** 2)))

    # Effective duration (time above 10% of peak)
    peak_amp = np.max(np.abs(segment))
    if peak_amp > 0:
        above_threshold = np.where(np.abs(segment) > 0.1 * peak_amp)[0]
        if len(above_threshold) > 0:
            duration_samples = above_threshold[-1] - above_threshold[0]
            duration_ms = (duration_samples / sr) * 1000
        else:
            duration_ms = 0.0
    else:
        duration_ms = 0.0

    return HitFeatures(
        spectral_centroid=centroid,
        spectral_bandwidth=bandwidth,
        zero_crossing_rate=zcr,
        energy_low=energy_low,
        energy_mid=energy_mid,
        energy_high=energy_high,
        energy_ratio_low=ratio_low,
        energy_ratio_mid=ratio_mid,
        energy_ratio_high=ratio_high,
        mfcc=mfcc,
        rms=rms,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Heuristic Classification
# ---------------------------------------------------------------------------


def _classify_heuristic(f: HitFeatures) -> tuple[HitType, float]:
    """
    Rule-based drum hit classification using spectral features.

    Returns (HitType, confidence 0–1).

    Decision tree:
      1. Low energy dominant (ratio_low > 0.55) + centroid < 300 → KICK
      2. High energy dominant (ratio_high > 0.5) + centroid > 5000:
         a. duration < 15ms → HIHAT_CLOSED
         b. duration >= 15ms → HIHAT_OPEN or CYMBAL
      3. Mid energy dominant + ratio_high > 0.15 (snare wires) → SNARE
      4. Low-mid energy + centroid 100-600 → TOM
      5. Fallback → UNKNOWN
    """
    scores = {}

    # --- KICK ---
    kick_score = 0.0
    if f.energy_ratio_low > 0.45:
        kick_score += 0.4
    if f.spectral_centroid < 400:
        kick_score += 0.3
    if f.energy_ratio_high < 0.2:
        kick_score += 0.2
    if f.duration_ms > 15:
        kick_score += 0.1
    scores[HitType.KICK] = kick_score

    # --- SNARE ---
    snare_score = 0.0
    if f.energy_ratio_mid > 0.3:
        snare_score += 0.3
    if f.energy_ratio_high > 0.15:  # snare wire contribution
        snare_score += 0.25
    if 300 < f.spectral_centroid < 5000:
        snare_score += 0.25
    if f.zero_crossing_rate > 0.05:  # noise-like component
        snare_score += 0.2
    scores[HitType.SNARE] = snare_score

    # --- HIHAT CLOSED ---
    hh_closed_score = 0.0
    if f.energy_ratio_high > 0.5:
        hh_closed_score += 0.35
    if f.spectral_centroid > 5000:
        hh_closed_score += 0.25
    if f.duration_ms < 20:
        hh_closed_score += 0.25
    if f.zero_crossing_rate > 0.1:
        hh_closed_score += 0.15
    scores[HitType.HIHAT_CLOSED] = hh_closed_score

    # --- HIHAT OPEN ---
    hh_open_score = 0.0
    if f.energy_ratio_high > 0.4:
        hh_open_score += 0.3
    if f.spectral_centroid > 4000:
        hh_open_score += 0.2
    if 20 <= f.duration_ms < 80:
        hh_open_score += 0.3
    if f.zero_crossing_rate > 0.08:
        hh_open_score += 0.2
    scores[HitType.HIHAT_OPEN] = hh_open_score

    # --- TOM ---
    tom_score = 0.0
    if f.energy_ratio_low > 0.2 and f.energy_ratio_mid > 0.3:
        tom_score += 0.35
    if 100 < f.spectral_centroid < 800:
        tom_score += 0.3
    if f.energy_ratio_high < 0.25:
        tom_score += 0.2
    if f.duration_ms > 20:
        tom_score += 0.15
    scores[HitType.TOM] = tom_score

    # --- CYMBAL ---
    cymbal_score = 0.0
    if f.energy_ratio_high > 0.45:
        cymbal_score += 0.3
    if f.spectral_centroid > 4000:
        cymbal_score += 0.25
    if f.duration_ms > 60:
        cymbal_score += 0.3
    if f.spectral_bandwidth > 3000:
        cymbal_score += 0.15
    scores[HitType.CYMBAL] = cymbal_score

    # Pick winner
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    # Confidence: margin between best and second-best
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) >= 2:
        margin = sorted_scores[0] - sorted_scores[1]
        confidence = min(1.0, best_score * (0.5 + margin))
    else:
        confidence = best_score

    # If best score is too low, mark as unknown
    if best_score < 0.3:
        return HitType.UNKNOWN, round(best_score, 3)

    return best_type, round(confidence, 3)


# ---------------------------------------------------------------------------
# ML Classification (optional)
# ---------------------------------------------------------------------------


def _load_classifier(model_path: str):
    """Load a trained sklearn classifier from a joblib file."""
    try:
        import joblib
        return joblib.load(model_path)
    except Exception as e:
        logger.warning(f"Failed to load classifier from {model_path}: {e}")
        return None


def _classify_ml(features: HitFeatures, classifier) -> tuple[HitType, float]:
    """
    Classify using a trained ML model (logistic regression or random forest).
    Falls back to heuristic if prediction fails.
    """
    try:
        X = features.to_vector().reshape(1, -1)
        prediction = classifier.predict(X)[0]
        probabilities = classifier.predict_proba(X)[0]
        confidence = float(np.max(probabilities))

        # Map string label → HitType
        try:
            hit_type = HitType(prediction)
        except ValueError:
            hit_type = HitType.UNKNOWN

        return hit_type, round(confidence, 3)

    except Exception as e:
        logger.warning(f"ML classification failed: {e}, using heuristic fallback")
        return _classify_heuristic(features)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _summarize_hits(hits: list[DrumHit]) -> str:
    """Generate a brief summary string of hit type counts."""
    from collections import Counter
    counts = Counter(h.hit_type.value for h in hits)
    parts = [f"{v}×{k}" for k, v in counts.most_common()]
    return ", ".join(parts) if parts else "none"
