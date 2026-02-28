"""Stem Separation Service — Demucs-based drum stem isolation."""

import logging
from pathlib import Path
import torch
import numpy as np

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _set_deterministic_seeds():
    """Lock all random seeds for reproducible stem separation."""
    seed = settings.random_seed
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def separate_stems(audio_path: str, output_dir: str | None = None) -> dict:
    """
    Separate audio into stems using Demucs v4.
    
    Returns dict with paths to each stem file and quality metrics.
    Primary focus is on the drums stem.
    """
    # Import here to avoid slow startup for non-worker processes
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    import torchaudio

    _set_deterministic_seeds()
    
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    if output_dir is None:
        output_dir = settings.stems_dir / audio_path.stem
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Loading Demucs model: {settings.demucs_model}")
    
    # Load model
    model = get_model(settings.demucs_model)
    model.eval()
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    
    # Load audio
    waveform, sr = torchaudio.load(str(audio_path))
    
    # Resample if necessary
    if sr != model.samplerate:
        resampler = torchaudio.transforms.Resample(sr, model.samplerate)
        waveform = resampler(waveform)
    
    # Ensure stereo (Demucs expects 2 channels)
    if waveform.shape[0] == 1:
        waveform = waveform.repeat(2, 1)
    elif waveform.shape[0] > 2:
        waveform = waveform[:2]
    
    # Add batch dimension: (batch, channels, samples)
    waveform = waveform.unsqueeze(0).to(device)
    
    # Run separation
    logger.info("Running stem separation...")
    with torch.no_grad():
        sources = apply_model(model, waveform, device=device)
    
    # sources shape: (batch, num_sources, channels, samples)
    sources = sources.squeeze(0).cpu()
    
    # Save stems — Demucs v4 sources: drums, bass, other, vocals
    source_names = model.sources  # ['drums', 'bass', 'other', 'vocals']
    stem_paths = {}
    quality_scores = {}
    
    for i, name in enumerate(source_names):
        stem_path = output_dir / f"{name}.wav"
        stem_audio = sources[i]
        
        # Save as WAV
        torchaudio.save(str(stem_path), stem_audio, model.samplerate)
        stem_paths[name] = str(stem_path)
        
        # Compute basic quality score (RMS energy ratio)
        stem_rms = torch.sqrt(torch.mean(stem_audio ** 2)).item()
        mix_rms = torch.sqrt(torch.mean(waveform.squeeze(0).cpu() ** 2)).item()
        quality_scores[name] = min(stem_rms / (mix_rms + 1e-8), 1.0)
        
        logger.info(f"  Saved {name} stem: {stem_path.name} (quality: {quality_scores[name]:.3f})")
    
    # Re-export drums stem to target sample rate if needed
    drums_path = stem_paths.get("drums")
    if drums_path and model.samplerate != settings.sample_rate:
        _resample_file(drums_path, settings.sample_rate)
    
    return {
        "stem_paths": stem_paths,
        "quality_scores": quality_scores,
        "model_name": settings.demucs_model,
        "model_samplerate": model.samplerate,
        "source_names": list(source_names),
    }


def _resample_file(file_path: str, target_sr: int):
    """Resample a WAV file in-place to target sample rate."""
    import torchaudio
    
    waveform, sr = torchaudio.load(file_path)
    if sr != target_sr:
        resampler = torchaudio.transforms.Resample(sr, target_sr)
        waveform = resampler(waveform)
        torchaudio.save(file_path, waveform, target_sr)
