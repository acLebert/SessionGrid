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
- **Score** confidence on every analysis dimension
- **Generate** a click track aligned to the real beat grid
- **Display** a waveform timeline with section markers and loopable playback
- **Export** click track WAV, JSON analysis, and more

## Architecture

```
Next.js (Frontend)  →  FastAPI (Backend)  →  PostgreSQL
                            ↓
                    Celery + Redis (Queue)
                            ↓
               FFmpeg → Demucs → librosa → madmom
                            ↓
                    File Storage (Local/S3)
```

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Backend API | FastAPI (Python) |
| Task Queue | Celery + Redis |
| Stem Separation | Demucs v4 (htdemucs) |
| Beat Analysis | librosa + madmom |
| Audio Extraction | FFmpeg |
| Database | PostgreSQL |
| Waveform UI | Custom Canvas renderer |

## Project Structure

```
SessionGrid/
├── apps/
│   ├── api/                      # FastAPI backend
│   │   ├── main.py               # API routes
│   │   ├── config.py             # Settings
│   │   ├── models.py             # SQLAlchemy models
│   │   ├── schemas.py            # Pydantic schemas
│   │   ├── database.py           # DB session management
│   │   ├── services/             # Analysis pipeline
│   │   │   ├── audio_extract.py  # FFmpeg audio extraction
│   │   │   ├── stem_separate.py  # Demucs stem separation
│   │   │   ├── beat_analysis.py  # librosa + madmom analysis
│   │   │   ├── section_detect.py # Structural segmentation
│   │   │   ├── click_generate.py # Click track generation
│   │   │   ├── confidence.py     # Confidence scoring
│   │   │   └── waveform.py       # Waveform peak generation
│   │   ├── workers/
│   │   │   ├── celery_app.py     # Celery configuration
│   │   │   └── tasks.py          # Full pipeline task
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── web/                      # Next.js frontend
│       ├── app/
│       │   ├── page.tsx           # Home / upload page
│       │   ├── layout.tsx         # Root layout
│       │   ├── globals.css        # Tailwind + custom styles
│       │   └── projects/
│       │       ├── page.tsx       # Projects list
│       │       └── [id]/page.tsx  # Analysis dashboard
│       ├── components/
│       │   ├── analysis/          # Dashboard components
│       │   ├── player/            # Waveform + playback
│       │   └── ui/                # Shared UI components
│       ├── lib/
│       │   ├── api.ts             # API client
│       │   └── types.ts           # TypeScript types
│       ├── Dockerfile
│       └── package.json
│
├── docs/
│   ├── PRD.md                    # Product Requirements Document
│   ├── ARCHITECTURE.md           # System architecture
│   └── VALIDATION.md             # Repeatability & validation strategy
│
├── storage/                      # Upload/output file storage
├── docker-compose.yml            # Full stack compose
├── .env.example                  # Environment template
└── .gitignore
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- (Or: Node.js 20+, Python 3.11+, PostgreSQL, Redis, FFmpeg)

### Run with Docker Compose

```bash
# Clone the repo
git clone <repo-url> SessionGrid
cd SessionGrid

# Copy environment config
cp .env.example .env

# Start all services
docker compose up --build
```

- **Frontend**: http://localhost:3000
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

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
| `PATCH` | `/api/projects/:id/sections/:sid` | Edit section |
| `GET` | `/api/projects/:id/export/json` | Export analysis JSON |
| `DELETE` | `/api/projects/:id` | Delete project |

## Analysis Pipeline

```
Upload → FFmpeg Extract → Demucs Separate → Beat Analysis → Section Detection
    → Confidence Scoring → Click Track Generation → Waveform Peaks → Done
```

Every job records input hash, pipeline version, model versions, random seeds, and output hash for full determinism and repeatability tracking.

## Confidence Model

| Dimension | What It Measures |
|-----------|-----------------|
| Stem Quality | Separation clarity (energy ratio) |
| Beat Grid | Beat regularity and tempo stability |
| Downbeat | Bar-start detection accuracy |
| Meter | Time signature confidence per section |
| Sections | Structural boundary reliability |

Each scored **High** / **Medium** / **Low** with corresponding UI treatment.

## Rights & Privacy

- Users must confirm rights before uploading
- No streaming-link ingestion
- Outputs are private by default
- No stem redistribution features

## Roadmap

- [x] MVP: Drums-focused analysis pipeline
- [x] Click track generation
- [x] Section detection with confidence
- [ ] Speed adjustment for practice
- [ ] PDF section guide export
- [ ] MIDI map export
- [ ] Manual section boundary editing
- [ ] Bass stem analysis
- [ ] Guitar stem analysis
- [ ] Multi-instrument arrangement maps
- [ ] User accounts & project history

## License

Private — All rights reserved.
