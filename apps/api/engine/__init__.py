"""
SessionGrid Audio Engine v2 — Elite Drum Intelligence Engine

Staged pipeline architecture:
  1. separation_stage  — Stereo extraction + Demucs stem isolation
  2. signal_stage      — Frame-level onset detection + sample-level refinement
  3. temporal_stage    — Beat tracking, downbeat detection, tempo octave correction
  4. groove_stage      — Swing detection, microtiming, accent profiling
  5. hit_stage         — Drum hit classification via multi-feature extraction
  6. export_stage      — MIDI export with quantization control, click generation

Cross-cutting:
  - confidence.py      — Metric-vector confidence (replaces threshold bins)
  - versioning.py      — Analysis engine versioning + artifact caching
"""

ENGINE_VERSION = "2.0.0"
