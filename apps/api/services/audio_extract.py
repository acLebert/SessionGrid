"""Audio Extraction Service — FFmpeg-based audio extraction from video/audio containers."""

import subprocess
import hashlib
import logging
from pathlib import Path
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def extract_audio(input_path: str, output_path: str | None = None) -> dict:
    """
    Extract audio from any media file using FFmpeg.
    
    Normalizes to: WAV, 44.1kHz, mono, 16-bit PCM.
    Returns metadata dict with output_path, duration, and file hash.
    """
    input_path = Path(input_path)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    if output_path is None:
        output_path = input_path.with_suffix(".wav")
    else:
        output_path = Path(output_path)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # FFmpeg command — deterministic, consistent output
    cmd = [
        "ffmpeg",
        "-y",                       # Overwrite
        "-i", str(input_path),      # Input
        "-vn",                      # No video
        "-acodec", "pcm_s16le",     # 16-bit PCM
        "-ar", str(settings.sample_rate),  # 44100 Hz
        "-ac", "1",                 # Mono
        "-f", "wav",                # WAV format
        str(output_path),
    ]
    
    logger.info(f"Extracting audio: {input_path.name} → {output_path.name}")
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,  # 5 minute timeout
    )
    
    if result.returncode != 0:
        logger.error(f"FFmpeg error: {result.stderr}")
        raise RuntimeError(f"Audio extraction failed: {result.stderr[:500]}")
    
    # Get duration from ffprobe
    duration = _get_duration(output_path)
    
    # Compute file hash for determinism tracking
    file_hash = _compute_hash(output_path)
    
    logger.info(f"Extraction complete: {duration:.1f}s, hash={file_hash[:12]}...")
    
    return {
        "output_path": str(output_path),
        "duration_seconds": duration,
        "file_hash_sha256": file_hash,
        "sample_rate": settings.sample_rate,
    }


def _get_duration(file_path: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    
    return float(result.stdout.strip())


def _compute_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
