"""Click Track Generator — Creates aligned click tracks from beat grid data."""

import logging
import numpy as np
import soundfile as sf

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def generate_click_track(
    beat_times: list[float],
    downbeat_times: list[float],
    duration_seconds: float,
    output_path: str,
    mode: str = "quarter",
) -> dict:
    """
    Generate a click track WAV aligned to the detected beat grid.
    
    Modes:
    - "quarter": Click on every beat, accented downbeats
    - "eighth": Click on every beat + subdivision
    - "downbeat": Click only on downbeats
    
    Returns dict with path and metadata.
    """
    np.random.seed(settings.random_seed)
    sr = settings.sample_rate
    
    logger.info(f"Generating click track: mode={mode}, {len(beat_times)} beats, {duration_seconds:.1f}s")
    
    # Create output buffer
    total_samples = int(duration_seconds * sr) + sr  # Extra second of buffer
    click_audio = np.zeros(total_samples, dtype=np.float32)
    
    # Generate click sounds
    downbeat_click = _make_click_sound(sr, frequency=1500, duration_ms=15, amplitude=0.9)
    beat_click = _make_click_sound(sr, frequency=1000, duration_ms=10, amplitude=0.6)
    subdivision_click = _make_click_sound(sr, frequency=800, duration_ms=8, amplitude=0.35)
    
    downbeat_set = set(round(t, 3) for t in downbeat_times)
    
    if mode == "downbeat":
        # Only click on downbeats
        for t in downbeat_times:
            _place_click(click_audio, downbeat_click, t, sr)
    
    elif mode == "eighth":
        # Click on every beat + eighth-note subdivisions
        for i, t in enumerate(beat_times):
            is_downbeat = any(abs(t - dt) < 0.05 for dt in downbeat_set)
            
            if is_downbeat:
                _place_click(click_audio, downbeat_click, t, sr)
            else:
                _place_click(click_audio, beat_click, t, sr)
            
            # Add eighth-note subdivision between this beat and next
            if i + 1 < len(beat_times):
                mid_time = (t + beat_times[i + 1]) / 2
                _place_click(click_audio, subdivision_click, mid_time, sr)
    
    else:  # "quarter" (default)
        for t in beat_times:
            is_downbeat = any(abs(t - dt) < 0.05 for dt in downbeat_set)
            
            if is_downbeat:
                _place_click(click_audio, downbeat_click, t, sr)
            else:
                _place_click(click_audio, beat_click, t, sr)
    
    # Trim to actual duration
    actual_samples = min(len(click_audio), int(duration_seconds * sr))
    click_audio = click_audio[:actual_samples]
    
    # Normalize
    peak = np.max(np.abs(click_audio))
    if peak > 0:
        click_audio = click_audio / peak * 0.85
    
    # Save
    sf.write(output_path, click_audio, sr, subtype="PCM_16")
    
    logger.info(f"Click track saved: {output_path}")
    
    return {
        "file_path": output_path,
        "mode": mode,
        "sample_rate": sr,
        "duration_seconds": duration_seconds,
        "num_clicks": len(beat_times),
    }


def _make_click_sound(
    sr: int,
    frequency: float = 1000,
    duration_ms: float = 10,
    amplitude: float = 0.8,
) -> np.ndarray:
    """Generate a short click/tick sound."""
    num_samples = int(sr * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, num_samples, endpoint=False)
    
    # Sine wave with exponential decay
    click = amplitude * np.sin(2 * np.pi * frequency * t)
    envelope = np.exp(-t * 1000 / (duration_ms * 0.3))  # Fast decay
    click *= envelope
    
    return click.astype(np.float32)


def _place_click(audio: np.ndarray, click: np.ndarray, time: float, sr: int):
    """Place a click sound at a specific time position in the audio buffer."""
    start_sample = int(time * sr)
    end_sample = start_sample + len(click)
    
    if start_sample < 0 or start_sample >= len(audio):
        return
    
    end_sample = min(end_sample, len(audio))
    click_trimmed = click[:end_sample - start_sample]
    audio[start_sample:end_sample] += click_trimmed
