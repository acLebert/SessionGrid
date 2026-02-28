"""Section Detection Service — Structural segmentation of audio."""

import logging
import numpy as np
import librosa
from scipy.ndimage import uniform_filter

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Common section name patterns based on position and repetition
SECTION_NAMES = [
    "Intro", "Verse 1", "Pre-Chorus", "Chorus",
    "Verse 2", "Pre-Chorus 2", "Chorus 2",
    "Bridge", "Chorus 3", "Outro"
]


def detect_sections(
    audio_path: str,
    beat_times: list[float],
    downbeat_times: list[float],
    overall_bpm: float,
) -> list[dict]:
    """
    Detect structural sections in audio using spectral features and 
    self-similarity analysis.
    
    Returns list of section dicts with name, timing, bars, meter, confidence.
    """
    np.random.seed(settings.random_seed)
    
    logger.info(f"Detecting sections for: {audio_path}")
    y, sr = librosa.load(audio_path, sr=settings.sample_rate, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)
    
    # ─── Spectral feature extraction ────────────────────────────────────
    # Use CQT-based chromagram and MFCCs for structural analysis
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    
    # ─── Self-similarity and novelty ────────────────────────────────────
    # Combine features
    features = np.vstack([
        librosa.util.normalize(chroma, axis=1),
        librosa.util.normalize(mfcc, axis=1),
    ])
    
    # Compute self-similarity matrix
    rec = librosa.segment.recurrence_matrix(
        features,
        width=3,
        mode="affinity",
        sym=True,
    )
    
    # Compute novelty curve using a checkerboard kernel on the recurrence matrix
    # (librosa.segment.novelty was removed; we compute it manually)
    novelty = _checkerboard_novelty(rec)
    
    # Find peaks in novelty curve → these are section boundaries
    peak_frames = _find_section_peaks(novelty, min_distance_seconds=6.0, sr=sr)
    boundary_times = librosa.frames_to_time(peak_frames, sr=sr).tolist()
    
    # Always include 0.0 as start and duration as end
    boundary_times = [0.0] + sorted([t for t in boundary_times if 0 < t < duration]) + [duration]
    
    # ─── Build sections ─────────────────────────────────────────────────
    sections = []
    for i in range(len(boundary_times) - 1):
        start = boundary_times[i]
        end = boundary_times[i + 1]
        section_duration = end - start
        
        # Estimate bars in this section
        bars, meter, meter_confidence = _estimate_meter_and_bars(
            start, end, beat_times, downbeat_times, overall_bpm
        )
        
        # Estimate local BPM for this section
        section_beats = [t for t in beat_times if start <= t < end]
        if len(section_beats) >= 2:
            iois = np.diff(section_beats)
            local_bpm = round(60.0 / np.median(iois), 1)
        else:
            local_bpm = overall_bpm
        
        # Assign a section name
        name = SECTION_NAMES[i] if i < len(SECTION_NAMES) else f"Section {i + 1}"
        
        # Compute confidence based on boundary clarity
        boundary_confidence = _score_boundary_confidence(
            i, peak_frames, novelty, len(boundary_times) - 2
        )
        
        sections.append({
            "order_index": i,
            "name": name,
            "start_time": round(start, 3),
            "end_time": round(end, 3),
            "bars": bars,
            "bpm": local_bpm,
            "meter": meter,
            "confidence": boundary_confidence,
        })
    
    logger.info(f"Detected {len(sections)} sections")
    return sections


def _checkerboard_novelty(rec: np.ndarray, kernel_size: int = 64) -> np.ndarray:
    """
    Compute a novelty curve from a recurrence/affinity matrix using a
    checkerboard kernel.  This replaces the removed ``librosa.segment.novelty``.

    The checkerboard kernel highlights transitions between self-similar blocks
    along the diagonal, producing peaks at structural boundaries.
    """
    n = rec.shape[0]
    if n < kernel_size:
        kernel_size = max(4, n // 2)

    half = kernel_size // 2

    # Build a ±1 checkerboard kernel of the requested size
    # Top-left and bottom-right quadrants are +1; the other two are -1
    kern = np.ones((kernel_size, kernel_size))
    kern[:half, half:] = -1
    kern[half:, :half] = -1

    # Correlate the kernel along the diagonal of the recurrence matrix
    novelty = np.zeros(n)
    for i in range(half, n - half):
        patch = rec[i - half: i + half, i - half: i + half]
        if patch.shape == kern.shape:
            novelty[i] = np.sum(patch * kern)

    # Half-wave rectify and smooth
    novelty = np.maximum(0, novelty)
    if len(novelty) > 8:
        novelty = uniform_filter(novelty, size=8)

    return novelty


def _find_section_peaks(
    novelty: np.ndarray,
    min_distance_seconds: float = 6.0,
    sr: int = 44100,
    hop_length: int = 512,
) -> np.ndarray:
    """Find significant peaks in novelty curve, respecting minimum distance."""
    min_distance_frames = int(min_distance_seconds * sr / hop_length)
    
    # Normalize novelty
    if novelty.max() > 0:
        novelty_norm = novelty / novelty.max()
    else:
        return np.array([])
    
    # Dynamic threshold: median + 0.5 * std
    threshold = np.median(novelty_norm) + 0.5 * np.std(novelty_norm)
    
    # Find peaks above threshold
    from scipy.signal import find_peaks
    peaks, properties = find_peaks(
        novelty_norm,
        height=threshold,
        distance=min_distance_frames,
        prominence=0.1,
    )
    
    return peaks


def _estimate_meter_and_bars(
    start: float,
    end: float,
    beat_times: list[float],
    downbeat_times: list[float],
    overall_bpm: float,
) -> tuple[int, str, str]:
    """
    Estimate meter (time signature) and bar count for a section.
    Returns (bars, meter_string, confidence).
    """
    section_beats = [t for t in beat_times if start <= t < end]
    section_downbeats = [t for t in downbeat_times if start <= t < end]
    
    if len(section_downbeats) >= 2:
        # Count beats between consecutive downbeats
        beats_per_bar_samples = []
        for i in range(len(section_downbeats) - 1):
            db_start = section_downbeats[i]
            db_end = section_downbeats[i + 1]
            beats_in_bar = len([b for b in section_beats if db_start <= b < db_end])
            if beats_in_bar > 0:
                beats_per_bar_samples.append(beats_in_bar)
        
        if beats_per_bar_samples:
            # Most common beats-per-bar
            from collections import Counter
            counter = Counter(beats_per_bar_samples)
            most_common_bpb = counter.most_common(1)[0][0]
            
            # Determine meter
            if most_common_bpb == 3:
                meter = "3/4"
            elif most_common_bpb == 4:
                meter = "4/4"
            elif most_common_bpb == 6:
                meter = "6/8"
            elif most_common_bpb == 2:
                meter = "2/4"
            else:
                meter = f"{most_common_bpb}/4"
            
            bars = len(section_downbeats)
            
            # Confidence: how consistent are the beats-per-bar?
            consistency = counter.most_common(1)[0][1] / len(beats_per_bar_samples)
            if consistency > 0.85:
                confidence = "high"
            elif consistency > 0.6:
                confidence = "medium"
            else:
                confidence = "low"
            
            return bars, meter, confidence
    
    # Fallback: estimate from duration and BPM
    section_duration = end - start
    beats_in_section = len(section_beats)
    estimated_bars = max(1, round(beats_in_section / 4))
    
    return estimated_bars, "4/4", "low"


def _score_boundary_confidence(
    section_index: int,
    peak_frames: np.ndarray,
    novelty: np.ndarray,
    total_boundaries: int,
) -> str:
    """Score how confident we are in a section boundary."""
    if section_index == 0:
        return "high"  # Start of song is always confident
    
    if section_index > len(peak_frames):
        return "low"
    
    # Check peak prominence relative to overall novelty
    peak_idx = section_index - 1  # First boundary is always t=0
    if peak_idx < len(peak_frames):
        peak_frame = peak_frames[peak_idx]
        if peak_frame < len(novelty):
            peak_value = novelty[peak_frame]
            max_novelty = novelty.max() if novelty.max() > 0 else 1
            relative_strength = peak_value / max_novelty
            
            if relative_strength > 0.7:
                return "high"
            elif relative_strength > 0.4:
                return "medium"
    
    return "low"
