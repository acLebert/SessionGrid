"""Waveform Peaks Service — Generate waveform data for frontend rendering."""

import logging
import numpy as np
import librosa
import json
from pathlib import Path

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def generate_waveform_peaks(
    audio_path: str,
    output_path: str | None = None,
    points_per_second: int = 50,
) -> dict:
    """
    Generate downsampled waveform peak data for frontend visualization.
    
    Returns dict with peaks array and metadata.
    """
    logger.info(f"Generating waveform peaks: {audio_path}")
    
    y, sr = librosa.load(audio_path, sr=settings.sample_rate, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)
    
    total_points = int(duration * points_per_second)
    samples_per_point = max(1, len(y) // total_points)
    
    peaks = []
    for i in range(0, len(y), samples_per_point):
        chunk = y[i:i + samples_per_point]
        if len(chunk) > 0:
            peaks.append({
                "min": round(float(np.min(chunk)), 4),
                "max": round(float(np.max(chunk)), 4),
                "rms": round(float(np.sqrt(np.mean(chunk ** 2))), 4),
            })
    
    result = {
        "peaks": peaks,
        "duration": round(duration, 3),
        "sample_rate": sr,
        "points_per_second": points_per_second,
        "total_points": len(peaks),
    }
    
    # Optionally save to file
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result, f)
        logger.info(f"Waveform peaks saved: {output_path}")
    
    return result
