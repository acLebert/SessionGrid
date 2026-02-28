# SessionGrid — Product Requirements Document

## 1. Product Summary

SessionGrid turns any song or demo into a musician-ready arrangement map. It starts as a drummer-focused rehearsal translator and is architected to expand to bass, guitar, piano, and full arrangement analysis.

## 2. Problem Statement

A musician gets a demo and is told "play it exactly like this." That creates friction:

- The instrument stem is buried in the mix
- Tempo changes are hard to detect by ear
- Section boundaries may not be obvious
- Meter changes or odd bars can be missed
- Building a click manually takes hours
- Not everyone reads standard notation

SessionGrid reduces prep time by converting raw audio into a guided rehearsal system.

## 3. Target Users

| Persona | Need |
|---------|------|
| Session drummer | Fast, accurate prep from rough demos |
| Gigging musician | Learn unfamiliar songs quickly |
| Music director | Share structured rehearsal guides with the band |
| Home producer | Validate arrangement structure and tempo map |

## 4. MVP Scope (v0.1)

### Must Have
- [ ] Upload audio (WAV, MP3, FLAC, OGG) or video (MP4, MOV, WebM)
- [ ] Extract audio from video containers via FFmpeg
- [ ] Separate drums stem via Demucs v4
- [ ] Estimate beat grid, tempo, and tempo changes
- [ ] Detect downbeats and estimate bar positions
- [ ] Detect section boundaries (intro, verse, chorus, bridge, outro)
- [ ] Estimate likely meter per section
- [ ] Generate click track aligned to detected beat grid
- [ ] Confidence scoring on every analysis dimension
- [ ] Waveform timeline with section markers
- [ ] Section-aware playback (original mix, drum stem, click, click+drums)
- [ ] Loop any section
- [ ] Export click track as WAV
- [ ] Export analysis as JSON

### Should Have (v0.2)
- [ ] Speed adjustment for practice (50% – 120%)
- [ ] Count-in before loop playback
- [ ] PDF section guide export
- [ ] MIDI map export
- [ ] AI cues panel (likely fills, pickups, accents)
- [ ] Manual override for section boundaries and meter
- [ ] Bar counter display during playback

### Could Have (v0.3+)
- [ ] Bass stem analysis
- [ ] Guitar stem analysis
- [ ] Multi-instrument arrangement map
- [ ] Collaborative project sharing
- [ ] User accounts and project history

## 5. Confidence Model

Every analysis output includes a confidence dimension:

| Dimension | What it measures |
|-----------|-----------------|
| Stem Quality | How clean the separated stem is |
| Beat Grid | Reliability of detected beat positions |
| Downbeat | Accuracy of bar-start detection |
| Meter | Confidence in time signature per section |
| Section Detection | Reliability of structural boundary guesses |

Each is rated **High**, **Medium**, or **Low** and surfaced in the UI.

**UI behavior by confidence level:**
- **High**: Normal display, no warnings
- **Medium**: Amber indicator, suggest manual review
- **Low**: Red indicator, strongly encourage manual override

## 6. Non-Functional Requirements

- **Determinism**: Same input + same pipeline version = same output
- **Latency**: Analysis of a 4-minute song should complete in < 90 seconds on GPU, < 5 minutes on CPU
- **File size**: Accept files up to 200 MB
- **Repeatability**: All model versions, seeds, and config are locked per job and recorded
- **Privacy**: User uploads and outputs are private by default

## 7. Rights Guardrails

- Users must confirm they have rights or permission before upload
- No streaming-link ingestion (Spotify, YouTube, etc.)
- Outputs are private by default — no public sharing of stems
- DMCA takedown process documented and accessible
- No stem redistribution features in MVP

## 8. Success Metrics

| Metric | Target |
|--------|--------|
| Upload → analysis complete (p95) | < 3 minutes |
| Beat grid accuracy vs manual annotation | > 85% |
| Section detection accuracy | > 75% |
| Repeat-run output hash match rate | > 99% |
| User completes a practice session | > 50% of uploads |
