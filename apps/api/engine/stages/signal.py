"""
Signal Stage — Onset detection with sample-level transient refinement.

The frame-based onset detection in librosa operates at ~11.6ms resolution
(hop_length=512 at 44.1kHz).  For drum intelligence, we need sub-millisecond
accuracy.  This module:

  1. Runs librosa onset detection to get rough frame-level onsets.
  2. Converts each frame index → sample index.
  3. Searches ±search_radius samples around each onset for the true
     amplitude peak (maximum absolute value in the waveform).
  4. Stores refined timestamps at sample-level precision (1/44100 ≈ 22.7μs).

Computational cost:
  - The refinement pass is O(N_onsets × search_radius).
  - With ~500 onsets and search_radius=512, that's 512K sample lookups — trivial.
  - The dominant cost remains the initial STFT-based onset detection.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import librosa

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Onset:
    """A single detected onset event."""
    time: float              # seconds, sample-level precision
    sample_index: int        # absolute sample index in the waveform
    frame_index: int         # original librosa frame index
    strength: float          # onset strength at this frame
    refined: bool = False    # True if sample-level refinement was applied


@dataclass
class SignalResult:
    """Output of the signal stage."""
    onsets: list[Onset] = field(default_factory=list)
    onset_envelope: Optional[np.ndarray] = None  # full onset strength envelope
    sample_rate: int = 44100
    hop_length: int = 512
    duration_seconds: float = 0.0
    num_raw_onsets: int = 0     # before refinement / dedup
    num_refined_onsets: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_onsets(
    y: np.ndarray,
    sr: int,
    hop_length: int = 512,
    search_radius: int = 512,
    backtrack: bool = True,
    dedup_samples: int = 256,
) -> SignalResult:
    """
    Two-pass onset detection: frame-level → sample-level refinement.

    Parameters
    ----------
    y : np.ndarray
        Mono audio waveform (float32).
    sr : int
        Sample rate.
    hop_length : int
        STFT hop for onset detection (default 512 → 11.6ms at 44.1k).
    search_radius : int
        Number of samples to search in each direction for the true peak.
        512 samples ≈ ±11.6ms at 44.1kHz — covers the full frame.
    backtrack : bool
        If True, librosa backtracks onsets to the nearest preceding
        energy minimum (better for transient attack times).
    dedup_samples : int
        Minimum distance between refined onsets (avoid double-triggers).
        256 samples ≈ 5.8ms at 44.1kHz — no real drum hit is faster.

    Returns
    -------
    SignalResult with sample-level onset timestamps.
    """
    duration = len(y) / sr

    # --- Pass 1: frame-level onset detection ---
    onset_env = librosa.onset.onset_strength(
        y=y, sr=sr, hop_length=hop_length,
        aggregate=np.median,  # more robust to broadband noise
    )

    onset_frames = librosa.onset.onset_detect(
        y=y, sr=sr,
        onset_envelope=onset_env,
        hop_length=hop_length,
        backtrack=backtrack,
        units="frames",
    )

    num_raw = len(onset_frames)
    logger.info(f"Frame-level onset detection: {num_raw} raw onsets")

    # --- Pass 2: sample-level refinement ---
    onsets: list[Onset] = []
    prev_sample = -dedup_samples - 1

    for frame_idx in onset_frames:
        # Frame → sample center
        center_sample = int(frame_idx * hop_length)

        # Search window
        lo = max(0, center_sample - search_radius)
        hi = min(len(y), center_sample + search_radius)
        window = y[lo:hi]

        if len(window) == 0:
            continue

        # Find the true amplitude peak within the window
        peak_offset = int(np.argmax(np.abs(window)))
        refined_sample = lo + peak_offset

        # Dedup: skip if too close to previous onset
        if refined_sample - prev_sample < dedup_samples:
            continue

        refined_time = refined_sample / sr
        strength = float(onset_env[frame_idx]) if frame_idx < len(onset_env) else 0.0

        onsets.append(Onset(
            time=refined_time,
            sample_index=refined_sample,
            frame_index=int(frame_idx),
            strength=strength,
            refined=True,
        ))
        prev_sample = refined_sample

    logger.info(
        f"Sample-level refinement: {num_raw} → {len(onsets)} onsets "
        f"(search_radius={search_radius}, dedup={dedup_samples})"
    )

    return SignalResult(
        onsets=onsets,
        onset_envelope=onset_env,
        sample_rate=sr,
        hop_length=hop_length,
        duration_seconds=duration,
        num_raw_onsets=num_raw,
        num_refined_onsets=len(onsets),
    )


def onset_times_from_result(result: SignalResult) -> list[float]:
    """Extract plain float timestamps from a SignalResult."""
    return [o.time for o in result.onsets]


def onset_strengths_from_result(result: SignalResult) -> list[float]:
    """Extract onset strengths for velocity estimation."""
    return [o.strength for o in result.onsets]
