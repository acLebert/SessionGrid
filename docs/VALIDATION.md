# SessionGrid — Validation & Repeatability Strategy

## Core Principle

If the same song is processed 1,000 times with the same pipeline version, the outputs must be identical or within a defined tolerance band.

## What Is Locked Per Job

Every analysis job records:

| Parameter | Example |
|-----------|---------|
| Input file SHA-256 | `a3f2b9c1...` |
| Pipeline version | `0.1.0` |
| Demucs model + version | `htdemucs_ft v4.0.1` |
| librosa version | `0.10.1` |
| madmom version | `0.17.dev0` |
| FFmpeg version | `6.1.1` |
| PyTorch version | `2.2.0` |
| Random seeds | `{"torch": 42, "numpy": 42}` |
| Sample rate | `44100` |
| Config snapshot | Full JSON of all parameters |
| Output files SHA-256 | Per-file hashes |

## Determinism Controls

### Demucs
```python
import torch
torch.manual_seed(42)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
```

### librosa / madmom
- Pin exact versions
- Use consistent hop_length, n_fft, sample rate
- Avoid any randomized parameters

### FFmpeg
- Lock encoding parameters: `-ar 44100 -ac 1 -f wav`
- Pin FFmpeg version in Docker image

### NumPy
```python
import numpy as np
np.random.seed(42)
```

## What Is Measured

| Dimension | Metric | Tolerance |
|-----------|--------|-----------|
| Drum stem | Waveform correlation | > 0.999 |
| Beat timestamps | Max deviation | < 5 ms |
| Downbeat timestamps | Max deviation | < 10 ms |
| Tempo estimate | BPM difference | < 0.1 BPM |
| Section boundaries | Time deviation | < 100 ms |
| Meter per section | Exact match | 100% |
| Click track | Waveform correlation | > 0.999 |
| Output hash | Exact match | 100% (goal) |

## Golden Dataset

Maintain a curated set of test songs across the quality spectrum:

| Category | Count | Description |
|----------|-------|-------------|
| Clean studio | 5 | Clear mix, strong drums, stable tempo |
| Typical demo | 5 | Dense mix, human drift, some ambiguity |
| Difficult | 5 | Phone recordings, heavy compression, rubato, complex meter |

## Validation Process

### Per-Release Regression Test
1. Run every golden-dataset file through the pipeline
2. Compare output hashes to previous release baseline
3. If hashes differ, compute per-dimension deltas
4. Flag regressions that exceed tolerance bands
5. No release ships until regressions are explained and accepted

### Determinism Smoke Test
1. Pick 3 songs (clean, medium, difficult)
2. Run each 10 times through the same pipeline
3. Assert output hashes are identical across all runs
4. If non-deterministic, investigate and add controls

### Accuracy Benchmark
1. Manually annotate beat positions, downbeats, sections, and meter for golden dataset
2. Compare pipeline output against ground-truth annotations
3. Track accuracy metrics over time
4. Target: >85% beat accuracy, >75% section accuracy

## CI Integration

```yaml
# .github/workflows/validation.yml
- name: Determinism test
  run: python -m pytest tests/validation/test_determinism.py -v

- name: Regression test
  run: python -m pytest tests/validation/test_regression.py -v

- name: Accuracy benchmark
  run: python -m pytest tests/validation/test_accuracy.py -v --benchmark
```

## Confidence Scoring Algorithm

Each dimension gets a confidence score based on signal-quality heuristics:

### Stem Quality
- Spectral contrast between stem and residual
- Signal-to-noise ratio of the stem
- Presence of bleed from other instruments

### Beat Grid
- Onset strength variance (consistent onsets = high confidence)
- Tempo stability over time
- Agreement between multiple beat-tracking algorithms

### Downbeat
- Agreement between madmom and librosa downbeat estimates
- Consistency of bar-length patterns

### Meter
- Regularity of bar lengths
- Agreement with common meter patterns (4/4, 3/4, 6/8)
- Deviation from expected bar duration

### Section Detection
- Spectral change magnitude at boundaries
- Repetition detection confidence
- Regularity of section lengths
