"""
Separation Stage — Audio extraction + Demucs stem isolation.

Key v2 changes vs v1:
  - Extract STEREO for Demucs (not mono). Mono only produced for analysis.
  - Resample ALL stems to target SR (not just drums).
  - Compute per-stem spectral SNR (replaces crude RMS ratio).
  - Return raw waveform arrays alongside file paths for downstream stages.
"""

import subprocess
import hashlib
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torchaudio

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_audio(input_path: str, output_dir: str) -> dict:
    """
    Extract audio from any media container via FFmpeg.

    Produces TWO files:
      - audio_stereo.wav  — native stereo (or duplicated mono) for Demucs
      - audio_mono.wav    — 44.1 kHz mono 16-bit PCM for analysis

    Returns:
      {
        stereo_path, mono_path, duration_seconds,
        file_hash_sha256, sample_rate, channels
      }
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stereo_path = output_dir / "audio_stereo.wav"
    mono_path = output_dir / "audio_mono.wav"

    # --- Stereo extraction (preserve original channel layout, or pad mono→stereo)
    _ffmpeg_extract(input_path, stereo_path, channels=2)

    # --- Mono extraction for analysis
    _ffmpeg_extract(input_path, mono_path, channels=1)

    duration = _get_duration(stereo_path)
    file_hash = _compute_hash(mono_path)

    logger.info(
        f"Extraction complete: stereo={stereo_path.name}, mono={mono_path.name}, "
        f"{duration:.1f}s, hash={file_hash[:12]}…"
    )

    return {
        "stereo_path": str(stereo_path),
        "mono_path": str(mono_path),
        "duration_seconds": duration,
        "file_hash_sha256": file_hash,
        "sample_rate": settings.sample_rate,
        "channels": 2,
    }


def separate_stems(
    stereo_path: str,
    output_dir: str,
    model_name: Optional[str] = None,
) -> dict:
    """
    Run Demucs v4 stem separation on STEREO input.

    Returns:
      {
        stem_paths: {drums: path, bass: path, vocals: path, other: path},
        stem_waveforms: {drums: np.ndarray, ...},   # float32, mono, target SR
        quality_scores: {drums: float, ...},         # spectral SNR per stem
        model_name, model_samplerate, source_names
      }
    """
    from demucs.pretrained import get_model
    from demucs.apply import apply_model

    _set_deterministic_seeds()

    model_name = model_name or settings.demucs_model
    stereo_path = Path(stereo_path)
    if not stereo_path.exists():
        raise FileNotFoundError(f"Audio file not found: {stereo_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading Demucs model: {model_name}")
    model = get_model(model_name)
    model.eval()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    # Load stereo audio
    waveform, sr = torchaudio.load(str(stereo_path))

    # Resample to model's expected rate
    if sr != model.samplerate:
        resampler = torchaudio.transforms.Resample(sr, model.samplerate)
        waveform = resampler(waveform)

    # Ensure exactly 2 channels
    if waveform.shape[0] == 1:
        waveform = waveform.repeat(2, 1)
    elif waveform.shape[0] > 2:
        waveform = waveform[:2]

    waveform_batch = waveform.unsqueeze(0).to(device)

    logger.info("Running Demucs stem separation…")
    with torch.no_grad():
        sources = apply_model(model, waveform_batch, device=device)

    # sources: (1, num_sources, 2, samples)
    sources = sources.squeeze(0).cpu()

    source_names = list(model.sources)  # ['drums', 'bass', 'other', 'vocals']
    stem_paths = {}
    stem_waveforms = {}  # mono float32 numpy at target SR
    quality_scores = {}

    target_sr = settings.sample_rate
    mix_mono = waveform.mean(dim=0)  # mono mixdown for SNR reference

    for i, name in enumerate(source_names):
        stem_stereo = sources[i]  # (2, samples)

        # Save stereo WAV at model rate
        stem_path = output_dir / f"{name}.wav"
        torchaudio.save(str(stem_path), stem_stereo, model.samplerate)
        stem_paths[name] = str(stem_path)

        # Produce mono + resample for analysis pipeline
        stem_mono = stem_stereo.mean(dim=0)  # (samples,)
        if model.samplerate != target_sr:
            resampler = torchaudio.transforms.Resample(model.samplerate, target_sr)
            stem_mono = resampler(stem_mono.unsqueeze(0)).squeeze(0)

        stem_np = stem_mono.numpy().astype(np.float32)
        stem_waveforms[name] = stem_np

        # Spectral SNR: ratio of stem energy in key bands vs residual
        quality_scores[name] = _spectral_snr(stem_np, target_sr, name)

        logger.info(f"  {name}: saved, SNR={quality_scores[name]:.2f} dB")

    return {
        "stem_paths": stem_paths,
        "stem_waveforms": stem_waveforms,
        "quality_scores": quality_scores,
        "model_name": model_name,
        "model_samplerate": model.samplerate,
        "source_names": source_names,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ffmpeg_extract(input_path: Path, output_path: Path, channels: int):
    """Run FFmpeg to extract audio at target sample rate."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(settings.sample_rate),
        "-ac", str(channels),
        "-f", "wav",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[:500]}")


def _get_duration(file_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def _compute_hash(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _set_deterministic_seeds():
    seed = settings.random_seed
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def _spectral_snr(stem_mono: np.ndarray, sr: int, stem_name: str) -> float:
    """
    Compute a spectral signal-to-noise ratio for a stem.

    Uses band-specific energy: e.g. drums should have high energy in
    40-200 Hz (kick) and 5-16 kHz (cymbals) relative to mid-range bleed.
    Returns dB value (higher = cleaner separation).
    """
    import librosa

    n_fft = 2048
    S = np.abs(librosa.stft(stem_mono, n_fft=n_fft))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    # Define expected energy bands per stem type
    bands = {
        "drums": [(40, 200), (2000, 5000), (5000, 16000)],
        "bass": [(30, 250)],
        "vocals": [(200, 4000)],
        "other": [(200, 8000)],
    }

    target_bands = bands.get(stem_name, [(20, 20000)])
    in_band_energy = 0.0
    total_energy = np.sum(S ** 2) + 1e-12

    for lo, hi in target_bands:
        mask = (freqs >= lo) & (freqs <= hi)
        in_band_energy += np.sum(S[mask, :] ** 2)

    out_of_band_energy = total_energy - in_band_energy + 1e-12
    snr_db = 10 * np.log10(in_band_energy / out_of_band_energy)

    return round(float(snr_db), 2)
