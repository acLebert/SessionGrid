# SessionGrid

Rhythm analysis engine and rehearsal instrument.

Upload a track. Get back meter inference, subdivision graphs, groove profiling, drum hit classification, click tracks, and MIDI — with continuous confidence scoring across every dimension.

---

## Stack

```
┌──────────────┐     ┌──────────────┐     ┌────────────┐
│  Next.js 14  │────▶│   FastAPI     │────▶│ PostgreSQL │
│  port 3000   │     │   port 8000   │     │ port 5432  │
└──────────────┘     └──────┬───────┘     └────────────┘
                            │
                     ┌──────▼──────┐
                     │    Redis    │
                     │  port 6379  │
                     └──────┬──────┘
                            │
                  ┌─────────▼─────────┐
                  │   Celery Worker   │
                  │                   │
                  │   Engine v2       │
                  │   Pipeline        │
                  └─────────┬─────────┘
                            │
                  ┌─────────▼─────────┐
                  │   File Storage    │
                  │   local / S3      │
                  └───────────────────┘
```

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| API | FastAPI, SQLAlchemy (async), Pydantic |
| Task queue | Celery + Redis |
| Engine | Python, librosa, madmom, Demucs v4 |
| Database | PostgreSQL 16 |
| Audio extraction | FFmpeg |

---

## Engine v2 — Pipeline

Pure-function pipeline with zero database or Celery dependencies. The worker calls in and handles persistence.

```
Upload
  │
  ├─ 1. Separation ──── FFmpeg extract → Demucs v4 stem isolation
  │
  ├─ 2. Signal ──────── Onset detection → sample-level transient refinement
  │
  ├─ 3. Temporal ────── Beat tracking → downbeats → tempo octave correction → sections
  │
  ├─ 3b. Metrical ───── Multi-resolution periodicity → hypothesis generation →
  │      Inference       scoring → temporal tracking → modulation detection
  │
  ├─ 3c. Subdivision ── Persistent subdivision graph → multi-layer rhythm grid →
  │      Graph           phase relations between layers
  │
  ├─ 4. Groove ──────── Swing detection → microtiming → accent profiling
  │
  ├─ 5. Hits ────────── Multi-feature drum hit classification (k/s/h/t/c)
  │
  ├─ 6. Export ──────── MIDI (multi-track) → click track → waveform peaks
  │
  └─ Confidence ─────── Metric-vector scoring (6 dimensions + overall)
```

| Stage | Module | Description |
|-------|--------|-------------|
| 1 | `stages/separation.py` | FFmpeg audio extraction, Demucs v4 stem isolation, spectral SNR |
| 2 | `stages/signal.py` | Frame-level onset detection + sample-level transient refinement |
| 3 | `stages/temporal.py` | Beat tracking, downbeat detection, tempo octave correction, sections |
| 3b | `stages/metrical_inference.py` | Periodicity → hypothesis generation → scoring → tracking |
| 3c | `stages/subdivision_graph.py` | Persistent multi-layer subdivision graph with phase relations |
| 4 | `stages/groove.py` | Swing, microtiming, accent profiling, groove classification |
| 5 | `stages/hits.py` | Drum hit classification (kick/snare/hat/tom/cymbal) |
| 6 | `stages/export.py` | MIDI export, click track generation, waveform peaks |
| — | `confidence.py` | Continuous [0,1] metric-vector confidence scoring |
| — | `versioning.py` | Engine version tracking, artifact caching, stale-stage invalidation |

### Metrical Inference (Stage 3b)

~2400 lines. Handles complex rhythmic structures: math rock, polymeter, tempo changes, metric modulations.

```
Onset Impulse Train
       │
       ▼
Multi-Resolution Periodicity Analysis
  (autocorrelation + spectral, sliding windows, 4 resolutions)
       │
       ▼
Hypothesis Generator
  (period × beat_count × grouping → MeterHypothesis candidates)
       │
       ▼
Hypothesis Scorer
  (accent alignment, IOI consistency, prediction error,
   structural repetition, harmonic penalty, bar-level accent
   periodicity, downbeat-anchored meter scoring)
       │
       ▼
Hypothesis Tracker
  (EMA smoothing, hierarchical resolution, dominant tracking,
   modulation detection, ambiguity flagging, polyrhythm buffer)
       │
       ▼
InferenceResult
  ├── window_inferences[]
  ├── detected_modulations[]
  ├── persistent_polyrhythms[]
  └── global_dominant
```

### Subdivision Graph (Stage 3c)

`PersistentSubdivisionGraphBuilder` — windowed analysis of onset data against the beat grid. Detects simultaneous subdivision ratios (2, 3, 5, 7, etc.), tracks layer persistence across time, and computes pairwise phase relationships between layers.

Output: `RhythmGraph` with `SubdivisionLayer[]` + `PhaseRelation[]`.

### Confidence Model

Continuous [0,1] metric-vector. Geometric mean ensures a single weak dimension drags overall score.

| Dimension | Measures |
|-----------|----------|
| `tempo_stability_score` | Tempo coefficient of variation |
| `downbeat_alignment_score` | Downbeat proximity to beat grid |
| `meter_consistency_score` | Meter consistency across sections |
| `section_contrast_score` | Feature contrast at boundaries |
| `groove_consistency_score` | Groove pattern consistency |
| `hit_classification_score` | Hit classification confidence |
| `overall_confidence_score` | Weighted geometric mean |

---

## Frontend

Next.js 14 (App Router), TypeScript, Tailwind CSS. Three routes:

| Route | Component | Description |
|-------|-----------|-------------|
| `/` | `page.tsx` | Upload console with rhythm scope visualization |
| `/projects` | `projects/page.tsx` | Project list |
| `/projects/[id]` | `projects/[id]/page.tsx` | Analysis dashboard |

Key components:

| Component | Description |
|-----------|-------------|
| `AudioEngine.tsx` | Multi-stem Web Audio API mixer (mute/solo/volume per stem) |
| `WaveformDisplay.tsx` | Canvas waveform renderer |
| `ArrangementMap.tsx` | Section arrangement view |
| `TimelinePanel.tsx` | Timeline visualization |
| `RhythmPreviewHero.tsx` | Analytical subdivision scope (landing page) |
| `SubdivisionGraphPanel.tsx` | Subdivision graph debug panel |
| `RhythmDebugPanel.tsx` | Metrical inference debug view |
| `ProcessingView.tsx` | Processing status display |
| `ConfidenceBadge.tsx` | Confidence level indicator |

---

## Project Structure

```
SessionGrid/
├── apps/
│   ├── api/
│   │   ├── main.py                        # API routes
│   │   ├── config.py                      # Settings
│   │   ├── models.py                      # SQLAlchemy models
│   │   ├── schemas.py                     # Pydantic schemas
│   │   ├── database.py                    # DB sessions
│   │   ├── engine/
│   │   │   ├── __init__.py                # ENGINE_VERSION
│   │   │   ├── pipeline.py               # Pipeline orchestrator
│   │   │   ├── confidence.py             # Metric-vector scoring
│   │   │   ├── versioning.py             # Version tracking + caching
│   │   │   ├── stages/
│   │   │   │   ├── separation.py         # FFmpeg + Demucs
│   │   │   │   ├── signal.py             # Onset detection
│   │   │   │   ├── temporal.py           # Beats, downbeats, sections
│   │   │   │   ├── metrical_inference.py # Periodicity → hypotheses
│   │   │   │   ├── subdivision_graph.py  # Multi-layer rhythm graph
│   │   │   │   ├── groove.py             # Swing, microtiming
│   │   │   │   ├── hits.py               # Drum hit classification
│   │   │   │   └── export.py             # MIDI, click, waveforms
│   │   │   └── evaluation/
│   │   │       ├── ground_truth.py       # Ground-truth data model
│   │   │       ├── transcript_parser.py  # JSON loading + validation
│   │   │       ├── metrics.py            # Metric computation
│   │   │       └── evaluator.py          # Evaluation pipeline
│   │   ├── workers/
│   │   │   ├── celery_app.py              # Celery config
│   │   │   └── tasks.py                   # Pipeline task + persistence
│   │   ├── alembic/                       # Migrations
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── web/
│       ├── app/
│       │   ├── page.tsx                    # Upload console
│       │   ├── layout.tsx                  # Root layout
│       │   ├── globals.css                 # Styles
│       │   └── projects/
│       │       ├── page.tsx                # Project list
│       │       └── [id]/page.tsx           # Analysis dashboard
│       ├── components/
│       │   ├── analysis/
│       │   │   ├── ArrangementMap.tsx
│       │   │   ├── ExportPanel.tsx
│       │   │   ├── PracticeDeck.tsx
│       │   │   ├── ProcessingView.tsx
│       │   │   ├── ProjectSidebar.tsx
│       │   │   ├── RhythmDebugPanel.tsx
│       │   │   ├── RhythmPreviewHero.tsx
│       │   │   ├── SubdivisionGraphPanel.tsx
│       │   │   └── TimelinePanel.tsx
│       │   ├── player/
│       │   │   ├── AudioEngine.tsx
│       │   │   └── WaveformDisplay.tsx
│       │   └── ui/
│       │       └── ConfidenceBadge.tsx
│       ├── lib/
│       │   ├── api.ts                      # API client
│       │   └── types.ts                    # TypeScript models
│       ├── Dockerfile
│       └── package.json
│
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   └── VALIDATION.md
│
├── storage/
├── docker-compose.yml
└── .gitignore
```

---

## Quick Start

### Docker Compose

```bash
git clone https://github.com/acLebert/SessionGrid.git
cd SessionGrid
docker compose up --build
```

| Service | Port |
|---------|------|
| web | 3000 |
| api | 8000 |
| worker | — |
| postgres | 5432 |
| redis | 6379 |

Frontend: http://localhost:3000
API docs: http://localhost:8000/docs

### Local Development

**Backend:**
```bash
cd apps/api
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# separate terminal:
celery -A workers.celery_app worker --loglevel=info
```

**Frontend:**
```bash
cd apps/web
npm install
npm run dev
```

---

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/projects` | List projects |
| `POST` | `/api/projects` | Create + upload |
| `GET` | `/api/projects/:id` | Project details |
| `GET` | `/api/projects/:id/status` | Poll status |
| `POST` | `/api/projects/:id/analyze` | Trigger analysis |
| `GET` | `/api/projects/:id/audio` | Stream audio |
| `GET` | `/api/projects/:id/stems/:type` | Download stem |
| `GET` | `/api/projects/:id/click` | Download click |
| `GET` | `/api/projects/:id/waveform` | Waveform data |
| `GET` | `/api/projects/:id/midi` | Download MIDI |
| `POST` | `/api/projects/:id/midi/quantize` | Re-quantize MIDI |
| `GET` | `/api/projects/:id/drum-hits` | Drum hits |
| `GET` | `/api/projects/:id/groove` | Groove profile |
| `GET` | `/api/projects/:id/confidence` | Confidence vector |
| `GET` | `/api/projects/:id/rhythm-debug` | Metrical inference data |
| `GET` | `/api/projects/:id/subdivision-debug` | Subdivision graph data |
| `PATCH` | `/api/projects/:id/sections/:sid` | Edit section |
| `GET` | `/api/projects/:id/export/json` | Full analysis JSON |
| `DELETE` | `/api/projects/:id` | Delete project |

---

## Evaluation Framework

Synthetic test pipeline for metrical inference. No audio required.

| Module | Purpose |
|--------|---------|
| `ground_truth.py` | Immutable ground-truth dataclasses |
| `transcript_parser.py` | JSON loading + schema validation |
| `metrics.py` | Metric computation (meter accuracy, modulation P/R, polyrhythm recall) |
| `evaluator.py` | Pipeline + 5 synthetic test scenarios |

Metrics: meter accuracy, grouping accuracy, modulation precision/recall/timing, polyrhythm recall, ambiguity alignment, confidence calibration.

---

## Determinism

- Engine version semver tracked per run
- Stage-level sub-versioning — only stale stages re-run
- Intermediate artifacts cached as `.npz`
- Input hash + engine version + model weights + seeds → deterministic output

---

## Roadmap

- [x] Drums-focused analysis pipeline
- [x] Click track generation
- [x] Section detection with confidence
- [x] Engine v2 staged pipeline
- [x] Multi-resolution periodicity detection
- [x] Metrical inference (hypothesis generation, scoring, tracking)
- [x] Hierarchical meter resolution + modulation persistence
- [x] Bar-level accent periodicity scoring
- [x] Downbeat-anchored meter scoring
- [x] Persistent subdivision graph builder
- [x] Metric modulation and polyrhythm detection
- [x] Drum hit classification
- [x] Groove profiling (swing, microtiming, accents)
- [x] MIDI export with quantization control
- [x] Continuous confidence vector
- [x] Multi-stem Web Audio API mixer
- [x] Evaluation framework with synthetic tests
- [x] Engine versioning and artifact caching
- [x] Subdivision graph debug UI
- [x] Metrical inference debug panel
- [ ] Speed adjustment for practice
- [ ] Count-in before loop playback
- [ ] Bass/guitar stem analysis
- [ ] Multi-instrument arrangement maps
- [ ] Manual section boundary editing
- [ ] User accounts & project history

---

## License

Private — All rights reserved.
