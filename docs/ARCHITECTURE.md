# SessionGrid — System Architecture

## Overview

SessionGrid is a monorepo containing a **Next.js** frontend and a **FastAPI** backend with **Celery** workers for async audio processing. The system is designed for local development with Docker Compose and cloud deployment readiness.

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
                     │  ┌─────────────────┐   │
                     │  │ FFmpeg Extract   │   │
                     │  │ Demucs Separate  │   │
                     │  │ Beat Analysis    │   │
                     │  │ Section Detect   │   │
                     │  │ Click Generate   │   │
                     │  └─────────────────┘   │
                     └───────────┬───────────┘
                                 │
                     ┌───────────▼───────────┐
                     │    File Storage       │
                     │  (Local / S3-compat)  │
                     └───────────────────────┘
```

## Stack Choices

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind CSS | SSR, great DX, matches studio-grade UI needs |
| Backend API | FastAPI | Async-native Python, perfect for ML-adjacent pipelines |
| Task Queue | Celery + Redis | Battle-tested async job processing for long-running audio tasks |
| Database | PostgreSQL | Reliable, structured metadata storage |
| Stem Separation | Demucs v4 (htdemucs) | Best open-source drum separation quality |
| Beat Analysis | librosa + madmom | librosa for general MIR, madmom for superior downbeat detection |
| Audio Extraction | FFmpeg | Universal container/codec support |
| Waveform UI | WaveSurfer.js | Mature, performant, customizable waveform component |
| File Storage | Local filesystem (MVP) → S3 | Start simple, abstract behind storage interface |

## Data Model

```
Project
├── id (UUID)
├── name (string)
├── status (enum: uploading, processing, analyzing, complete, failed)
├── created_at (timestamp)
├── updated_at (timestamp)
├── original_filename (string)
├── original_file_path (string)
├── audio_file_path (string, after extraction)
├── duration_seconds (float)
├── file_hash_sha256 (string)
│
├── AnalysisResult (1:1)
│   ├── id (UUID)
│   ├── project_id (FK)
│   ├── pipeline_version (string)
│   ├── model_versions (JSON)
│   ├── random_seeds (JSON)
│   ├── config_snapshot (JSON)
│   ├── overall_bpm (float)
│   ├── bpm_stable (boolean)
│   ├── time_signature (string)
│   ├── confidence_stem (enum: high/medium/low)
│   ├── confidence_beat (enum: high/medium/low)
│   ├── confidence_downbeat (enum: high/medium/low)
│   ├── confidence_meter (enum: high/medium/low)
│   ├── confidence_sections (enum: high/medium/low)
│   ├── beats_json (JSON array of timestamps)
│   ├── downbeats_json (JSON array of timestamps)
│   ├── output_hash_sha256 (string)
│   └── analysis_duration_ms (integer)
│
├── StemFile (1:many)
│   ├── id (UUID)
│   ├── project_id (FK)
│   ├── stem_type (enum: drums, bass, vocals, other)
│   ├── file_path (string)
│   └── quality_score (float)
│
├── Section (1:many, ordered)
│   ├── id (UUID)
│   ├── project_id (FK)
│   ├── order_index (integer)
│   ├── name (string)
│   ├── start_time (float, seconds)
│   ├── end_time (float, seconds)
│   ├── bars (integer)
│   ├── bpm (float)
│   ├── meter (string)
│   ├── confidence (enum: high/medium/low)
│   └── notes (string, nullable)
│
└── ClickTrack (1:1)
    ├── id (UUID)
    ├── project_id (FK)
    ├── file_path (string)
    ├── mode (string)
    └── created_at (timestamp)
```

## Analysis Pipeline

The pipeline runs as a Celery task chain:

```
1. EXTRACT    → FFmpeg: video → WAV (44.1kHz, mono/stereo)
2. HASH       → SHA-256 of extracted audio
3. SEPARATE   → Demucs v4 (htdemucs): WAV → drums stem
4. ANALYZE    → librosa + madmom:
                 a. Onset detection
                 b. Beat tracking
                 c. Downbeat detection (madmom)
                 d. Tempo estimation
                 e. Section boundary detection
                 f. Meter estimation per section
5. CONFIDENCE → Score each dimension based on signal quality metrics
6. CLICK      → Generate aligned click track WAV from beat grid
7. PERSIST    → Save all results + output hash to database
```

## Determinism Strategy

- Demucs: Pin exact model weights + version, set `torch` random seeds
- librosa/madmom: Pin versions, use deterministic parameters
- FFmpeg: Lock to specific version, use consistent encoding params
- Every job records: input hash, pipeline version, all model versions, random seeds, config snapshot, output hash
- Validation: re-run golden dataset, compare output hashes

## API Routes

```
POST   /api/projects              → Create project + start upload
POST   /api/projects/:id/upload   → Upload file (multipart)
POST   /api/projects/:id/analyze  → Trigger analysis pipeline
GET    /api/projects/:id          → Get project with analysis results
GET    /api/projects/:id/status   → Poll job status
GET    /api/projects/:id/stems/:type  → Stream/download stem file
GET    /api/projects/:id/click    → Stream/download click track
GET    /api/projects/:id/waveform → Get waveform peaks data
GET    /api/projects              → List user's projects
DELETE /api/projects/:id          → Delete project and files
```

## Deployment Strategy

**MVP (Local / Single Server):**
- Docker Compose with all services
- Local filesystem for file storage
- SQLite option for zero-config dev, Postgres for staging/prod

**Production-Ready:**
- Containerized services on any cloud (Railway, Fly.io, AWS ECS)
- S3-compatible storage (AWS S3, Cloudflare R2, MinIO)
- Managed Postgres (Supabase, Neon, RDS)
- Redis (Upstash, ElastiCache)
- GPU worker for Demucs (optional — CPU works, just slower)
