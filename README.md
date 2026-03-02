# SessionGrid

**Turn demos into musician-ready arrangement maps.**

SessionGrid is a web-first music-analysis platform that starts with a drummer-focused workflow. Upload a song or demo, isolate the drum stem, analyze tempo and structure, and get back a rehearsal-ready guide with click track support, section mapping, confidence indicators, and exportable outputs.

---

## Why It Exists

Musicians receive rough demos and need to learn them fast. SessionGrid reduces prep time by converting raw audio into a guided rehearsal system — not notation software, but a **rehearsal translator**.

## What It Does

- **Upload** any audio file (MP3, WAV, FLAC) or video (MP4, MOV)
- **Extract** audio from video containers via FFmpeg
- **Separate** drums stem using Demucs v4
- **Analyze** tempo, beats, downbeats, sections, and time signatures
- **Infer meter** via multi-resolution periodicity detection and hypothesis tracking
- **Detect** metric modulations, polyrhythms, and ambiguous sections
- **Classify** individual drum hits (kick, snare, hat, tom, cymbal)
- **Profile** groove — swing ratio, microtiming, accent patterns
- **Score** confidence on every analysis dimension (continuous 0–1 vector)
- **Generate** a click track aligned to the real beat grid
- **Export** MIDI (multi-track, quantization control), click WAV, JSON, waveform peaks
- **Display** a waveform timeline with section markers and loopable playback

---

## System Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌──────────────┐
│   Next.js App   │────▶│   FastAPI API    │────▶│  PostgreSQL  │
│   (Port 3000)   │     │   (Port 8000)    │     │  (Port 5432) │
└─────────────────┘     └────────┬─────────┘     └──────────────┘
                                 │
                          ┌──────▼──────┐
                          │    Redis     │
                          │  (Port 6379) │
                          └──────┬──────┘
                                 │
                     ┌───────────▼───────────┐
                     │    Celery Worker(s)    │
                     │                        │
                     │  Engine v2 Pipeline    │
                     │  ┌──────────────────┐  │
                     │  │ 1. Separation    │  │
                     │  │ 2. Signal        │  │
                     │  │ 3. Temporal      │  │
                     │  │ 3b. Metrical     │  │
                     │  │     Inference    │  │
                     │  │ 4. Groove        │  │
                     │  │ 5. Hit Class.    │  │
                     │  │ 6. Export        │  │
                     │  └──────────────────┘  │
                     └───────────┬───────────┘
                                 │
                     ┌───────────▼───────────┐
                     │    File Storage       │
                     │  (Local / S3-compat)  │
                     └───────────────────────┘
```

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Backend API | FastAPI (async, PostgreSQL via SQLAlchemy) |
| Task Queue | Celery + Redis |
| Audio Engine | Engine v2 (see below) |
| Stem Separation | Demucs v4 (htdemucs) |
| Beat Analysis | librosa + madmom |
| Meter Inference | Custom multi-resolution periodicity + hypothesis tracking |
| Audio Extraction | FFmpeg |
| Database | PostgreSQL 16 |
| Waveform UI | Custom Canvas renderer |

---

## Engine v2 — Pipeline Architecture

The analysis engine (`apps/api/engine/`) is a pure-function pipeline with zero database or Celery dependencies. The Celery task calls into it and handles persistence.

### Pipeline Stages

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Engine v2 Pipeline                             │
│                                                                      │
│  ┌────────────┐   ┌────────────┐   ┌─────────────┐                  │
│  │ 1. Sepa-   │──▶│ 2. Signal  │──▶│ 3. Temporal │                  │
│  │ ration     │   │            │   │             │                  │
│  │            │   │ Onset det. │   │ Beat track  │                  │
│  │ FFmpeg     │   │ + sample-  │   │ Downbeats   │                  │
│  │ extract    │   │ level      │   │ Tempo corr. │                  │
│  │ Demucs     │   │ refinement │   │ Sections    │                  │
│  │ stems      │   │            │   │             │                  │
│  └────────────┘   └────────────┘   └──────┬──────┘                  │
│                                           │                          │
│                                    ┌──────▼──────┐                  │
│                                    │3b. Metrical │                  │
│                                    │  Inference   │                  │
│                                    │              │                  │
│                                    │ Periodicity  │                  │
│                                    │ Hypotheses   │                  │
│                                    │ Tracking     │                  │
│                                    └──────┬──────┘                  │
│                                           │                          │
│  ┌────────────┐   ┌────────────┐   ┌──────▼──────┐                  │
│  │ 6. Export  │◀──│ 5. Hits    │◀──│ 4. Groove  │                  │
│  │            │   │            │   │            │                  │
│  │ MIDI       │   │ Drum hit   │   │ Swing      │                  │
│  │ Click      │   │ classif.   │   │ Microtiming│                  │
│  │ Waveforms  │   │ (k/s/h/t/c)│   │ Accents    │                  │
│  └────────────┘   └────────────┘   └────────────┘                  │
│                                                                      │
│  Cross-cutting: confidence.py (metric vector) │ versioning.py       │
└──────────────────────────────────────────────────────────────────────┘
```

| Stage | Module | Purpose |
|-------|--------|---------|
| 1. Separation | `stages/separation.py` | FFmpeg audio extraction, Demucs v4 stem isolation, spectral SNR |
| 2. Signal | `stages/signal.py` | Frame-level onset detection + sample-level transient refinement (sub-ms) |
| 3. Temporal | `stages/temporal.py` | Beat tracking, downbeat detection, tempo octave correction, section segmentation |
| 3b. Metrical Inference | `stages/metrical_inference.py` | Multi-resolution periodicity → hypothesis generation → scoring → temporal tracking |
| 4. Groove | `stages/groove.py` | Swing detection, microtiming analysis, accent profiling, groove-type classification |
| 5. Hits | `stages/hits.py` | Multi-feature drum hit classification (kick/snare/hat/tom/cymbal) |
| 6. Export | `stages/export.py` | MIDI export (multi-track, quantization control), click track, waveform peaks |
| Confidence | `confidence.py` | Continuous [0,1] metric-vector scoring (replaces heuristic bins) |
| Versioning | `versioning.py` | Engine version tracking, artifact caching, stale-stage invalidation |

### Metrical Inference Engine (Stage 3b)

The metrical inference module (`stages/metrical_inference.py`, ~2400 lines) is the analytical core for rhythm intelligence. It handles complex rhythmic structures including math rock, polymeter, tempo changes, and metric modulations.

**Sub-stages:**

```
Onset Impulse Train
       │
       ▼
Multi-Resolution Periodicity Analysis
  (autocorrelation + spectral, sliding windows at 4 resolutions)
       │
       ▼
Periodicity Peak Extraction
  (bounds filter, energy floor, prominence, separation)
       │
       ▼
Hypothesis Generator
  (period × beat_count × grouping → MeterHypothesis candidates)
       │
       ▼
Hypothesis Scorer
  (accent alignment, IOI consistency, prediction error,
   structural repetition, harmonic penalty → confidence)
       │
       ▼
Hypothesis Tracker
  (EMA smoothing, dominant tracking, modulation detection,
   ambiguity flagging, polyrhythm buffer)
       │
       ▼
InferenceResult
  ├── window_inferences[]  (per-window dominant + competing hypotheses)
  ├── detected_modulations[]  (time, from/to hypothesis, confidence delta)
  ├── persistent_polyrhythms[]  (co-occurring non-harmonic layers)
  └── global_dominant  (best overall hypothesis across all windows)
```

**Key data structures:**

| Type | Description |
|------|-------------|
| `PeriodicityCandidate` | A raw periodicity peak (period, strength, source) |
| `MeterHypothesis` | Structured meter guess (period, beat_count, grouping_vector, phase, confidence, sub-scores) |
| `WindowInferenceResult` | Per-window output (dominant, competing, ambiguity, modulation flags) |
| `ModulationEvent` | Detected metric change (time, from/to hypotheses, confidence delta) |
| `PolyrhythmLayer` | Persistent co-occurring non-harmonic periodicities |
| `InferenceResult` | Top-level output aggregating all windows, modulations, polyrhythms |

### Evaluation Framework

The evaluation module (`engine/evaluation/`) provides a rigorous testing pipeline for the metrical inference engine:

| Module | Purpose |
|--------|---------|
| `ground_truth.py` | Immutable dataclasses (GroundTruth, MeterSegment, GroundTruthModulation, TempoSegment, PolyrhythmSegment) |
| `transcript_parser.py` | JSON loading and schema validation for ground-truth files |
| `metrics.py` | Side-effect-free metric computation (meter accuracy, grouping accuracy, modulation P/R/timing, polyrhythm recall, ambiguity alignment, confidence calibration) |
| `evaluator.py` | Top-level evaluation pipeline + 5 synthetic test scenarios (no audio required) |

**Metrics computed:**

- **Meter accuracy** — per-window dominant beat_count vs ground truth
- **Grouping accuracy** — exact grouping_vector match
- **Modulation precision/recall** — detected vs ground truth modulations (±2s tolerance)
- **Modulation timing error** — mean |t_detected − t_gt| in ms
- **Polyrhythm recall** — coverage of ground truth polyrhythm segments
- **Ambiguity alignment** — agreement between engine ambiguity flags and ground truth
- **Confidence calibration** — binned confidence vs empirical accuracy

### Confidence Model v2

Replaces heuristic "high/medium/low" bins with continuous [0, 1] metric-vector scoring:

| Dimension | What It Measures |
|-----------|-----------------|
| `tempo_stability_score` | Tempo stability across the song (coefficient of variation) |
| `downbeat_alignment_score` | Downbeat proximity to nearest beat grid point |
| `meter_consistency_score` | Meter consistency across sections |
| `section_contrast_score` | Feature contrast at section boundaries |
| `groove_consistency_score` | Groove pattern consistency |
| `hit_classification_score` | Hit classification confidence |
| `overall_confidence_score` | Weighted geometric mean of all dimensions |

The geometric mean ensures a single bad dimension drags the overall score down significantly.

---

## Project Structure

```
SessionGrid/
├── apps/
│   ├── api/                              # FastAPI backend
│   │   ├── main.py                       # API routes (19 endpoints)
│   │   ├── config.py                     # Settings
│   │   ├── models.py                     # SQLAlchemy models
│   │   ├── schemas.py                    # Pydantic schemas
│   │   ├── database.py                   # DB session management
│   │   ├── engine/                       # Engine v2
│   │   │   ├── __init__.py               # ENGINE_VERSION = "2.0.0"
│   │   │   ├── pipeline.py              # Pipeline orchestrator (pure functions)
│   │   │   ├── confidence.py            # Metric-vector confidence scoring
│   │   │   ├── versioning.py            # Version tracking + artifact caching
│   │   │   ├── stages/
│   │   │   │   ├── separation.py        # FFmpeg + Demucs stem isolation
│   │   │   │   ├── signal.py            # Onset detection + refinement
│   │   │   │   ├── temporal.py          # Beats, downbeats, tempo, sections
│   │   │   │   ├── metrical_inference.py # Periodicity → hypotheses → tracking
│   │   │   │   ├── groove.py            # Swing, microtiming, accents
│   │   │   │   ├── hits.py              # Drum hit classification
│   │   │   │   └── export.py            # MIDI, click, waveform peaks
│   │   │   └── evaluation/
│   │   │       ├── ground_truth.py      # Ground-truth data model
│   │   │       ├── transcript_parser.py # JSON loading + validation
│   │   │       ├── metrics.py           # Evaluation metric computation
│   │   │       └── evaluator.py         # Evaluation pipeline + test scenarios
│   │   ├── services/                     # Legacy service wrappers
│   │   ├── workers/
│   │   │   ├── celery_app.py             # Celery configuration
│   │   │   └── tasks.py                  # Pipeline task + DB persistence
│   │   ├── alembic/                      # Database migrations
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── web/                              # Next.js frontend
│       ├── app/
│       │   ├── page.tsx                   # Home / upload page
│       │   ├── layout.tsx                 # Root layout
│       │   ├── globals.css                # Tailwind + custom styles
│       │   └── projects/
│       │       ├── page.tsx               # Projects list
│       │       └── [id]/page.tsx          # Analysis dashboard
│       ├── components/
│       │   ├── analysis/
│       │   │   ├── ArrangementMap.tsx     # Section arrangement view
│       │   │   ├── ExportPanel.tsx        # Export controls
│       │   │   ├── PracticeDeck.tsx       # Practice mode
│       │   │   ├── ProcessingView.tsx     # Processing status
│       │   │   ├── ProjectSidebar.tsx     # Sidebar navigation
│       │   │   ├── TimelinePanel.tsx      # Timeline visualization
│       │   │   └── RhythmDebugPanel.tsx   # DEBUG: Rhythm engine debug view
│       │   ├── player/
│       │   │   ├── AudioEngine.tsx        # Audio playback engine
│       │   │   └── WaveformDisplay.tsx    # Waveform canvas renderer
│       │   └── ui/
│       │       └── ConfidenceBadge.tsx    # Confidence indicator
│       ├── lib/
│       │   ├── api.ts                     # API client + types
│       │   └── types.ts                   # TypeScript models
│       ├── Dockerfile
│       └── package.json
│
├── docs/
│   ├── PRD.md                            # Product Requirements Document
│   ├── ARCHITECTURE.md                   # System architecture
│   └── VALIDATION.md                     # Repeatability & validation
│
├── storage/                              # Upload/output file storage
├── docker-compose.yml                    # Full stack (5 services)
└── .gitignore
```

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- (Or: Node.js 20+, Python 3.11+, PostgreSQL, Redis, FFmpeg)

### Run with Docker Compose

```bash
# Clone the repo
git clone https://github.com/acLebert/SessionGrid.git
cd SessionGrid

# Start all services
docker compose up --build
```

Services:

| Service | Port | Description |
|---------|------|-------------|
| **web** | 3000 | Next.js frontend |
| **api** | 8000 | FastAPI backend (hot-reload) |
| **worker** | — | Celery worker (concurrency=1) |
| **postgres** | 5432 | PostgreSQL 16 |
| **redis** | 6379 | Redis 7 (task broker) |

- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

Code is volume-mounted — changes to `apps/api/` and `apps/web/` are picked up immediately with a container restart (API/worker) or HMR (web).

### Run Locally (Development)

**Backend:**
```bash
cd apps/api
python -m venv .venv
.venv/Scripts/activate          # Windows
pip install -r requirements.txt

# Start API
uvicorn main:app --reload --port 8000

# Start worker (separate terminal)
celery -A workers.celery_app worker --loglevel=info
```

**Frontend:**
```bash
cd apps/web
npm install
npm run dev
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/projects` | List projects |
| `POST` | `/api/projects` | Create project + upload |
| `GET` | `/api/projects/:id` | Get project details |
| `GET` | `/api/projects/:id/status` | Poll processing status |
| `POST` | `/api/projects/:id/analyze` | Trigger analysis |
| `GET` | `/api/projects/:id/audio` | Stream extracted audio |
| `GET` | `/api/projects/:id/stems/:type` | Download stem |
| `GET` | `/api/projects/:id/click` | Download click track |
| `GET` | `/api/projects/:id/waveform` | Get waveform data |
| `GET` | `/api/projects/:id/midi` | Download MIDI file |
| `POST` | `/api/projects/:id/midi/quantize` | Re-quantize MIDI |
| `GET` | `/api/projects/:id/drum-hits` | Get classified drum hits |
| `GET` | `/api/projects/:id/groove` | Get groove profile |
| `GET` | `/api/projects/:id/confidence` | Get confidence vector |
| `GET` | `/api/projects/:id/rhythm-debug` | DEBUG: Metrical inference data |
| `PATCH` | `/api/projects/:id/sections/:sid` | Edit section |
| `GET` | `/api/projects/:id/export/json` | Export full analysis JSON |
| `DELETE` | `/api/projects/:id` | Delete project + files |

---

## Analysis Pipeline

```
Upload
  │
  ▼
1. Separation ─── FFmpeg extract → Demucs v4 stem isolation
  │
  ▼
2. Signal ─────── Onset detection → sample-level transient refinement
  │
  ▼
3. Temporal ───── Beat tracking → downbeats → tempo octave correction → sections
  │
  ▼
3b. Metrical ──── Periodicity extraction → hypothesis generation →
    Inference      scoring → temporal tracking → modulation detection
  │
  ▼
4. Groove ─────── Swing detection → microtiming → accent profiling
  │
  ▼
5. Hits ──────── Multi-feature drum hit classification (k/s/h/t/c)
  │
  ▼
6. Export ─────── MIDI (multi-track) → click track → waveform peaks
  │
  ▼
Confidence ────── Metric-vector scoring (6 dimensions + overall)
  │
  ▼
Persist ──────── Results → PostgreSQL + file storage
```

Every job records input hash, pipeline version, model versions, random seeds, config snapshot, and output hash for full determinism and repeatability tracking.

---

## Determinism & Versioning

- **Engine version**: `ENGINE_VERSION = "2.0.0"` — semver tracked per analysis run
- **Stage versioning**: Each stage has its own sub-version; only stale stages re-run
- **Artifact caching**: Intermediate results cached as `.npz` in project storage
- **Reproducibility**: Identical input + engine version = identical output (pinned model weights, torch seeds, FFmpeg params)

---

## Rights & Privacy

- Users must confirm rights before uploading
- No streaming-link ingestion (Spotify, YouTube, etc.)
- Outputs are private by default
- No stem redistribution features

---

## Roadmap

- [x] MVP: Drums-focused analysis pipeline
- [x] Click track generation
- [x] Section detection with confidence
- [x] Engine v2: Staged pipeline architecture
- [x] Multi-resolution periodicity detection
- [x] Metrical inference (hypothesis generation, scoring, tracking)
- [x] Metric modulation and polyrhythm detection
- [x] Drum hit classification (kick/snare/hat/tom/cymbal)
- [x] Groove profiling (swing, microtiming, accents)
- [x] MIDI export with quantization control
- [x] Continuous confidence vector (replaces threshold bins)
- [x] Evaluation framework with synthetic test scenarios
- [x] Engine versioning and artifact caching
- [x] Rhythm debug panel (development tool)
- [ ] Speed adjustment for practice
- [ ] Count-in before loop playback
- [ ] Bass/guitar stem analysis
- [ ] Multi-instrument arrangement maps
- [ ] PDF section guide export
- [ ] MIDI map export
- [ ] Manual section boundary editing
- [ ] Bass stem analysis
- [ ] Guitar stem analysis
- [ ] Multi-instrument arrangement maps
- [ ] User accounts & project history

## License

Private — All rights reserved.
