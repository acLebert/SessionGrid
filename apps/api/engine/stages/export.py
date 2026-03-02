"""
Export Stage — MIDI export, click track generation, waveform peaks.

MIDI Export Architecture (Elite Version):
  - Preserves raw timing by default (quantization_strength=0 → raw onset times).
  - Quantization strength parameter (0–100%): lerp between raw and grid times.
  - Preserves detected swing ratio in quantized output.
  - Multi-track MIDI (kick/snare/hats/toms on separate tracks).
  - Tempo map via MIDI Set Tempo events at each tempo curve point.
  - Time signature events from section meter analysis.
  - Tick conversion: seconds → MIDI ticks via cumulative tempo integration
    to avoid rounding drift.

Click track generation carries over from v1 with the addition of swing-aware
subdivision placement.
"""

import logging
import json
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# MIDI Export
# ---------------------------------------------------------------------------

# MIDI ticks per quarter note — standard resolution
TICKS_PER_QUARTER = 480


def export_midi(
    hits: list[dict],
    tempo_curve: list[dict],
    time_signature: str,
    sections: list[dict],
    output_path: str,
    quantization_strength: float = 0.0,
    swing_ratio: float = 0.5,
    beat_times: Optional[list[float]] = None,
) -> dict:
    """
    Export classified drum hits to a multi-track MIDI file.

    Parameters
    ----------
    hits : list[dict]
        Each: {time, hit_type, velocity, midi_note}
    tempo_curve : list[dict]
        [{time, bpm}, ...]
    time_signature : str
        e.g. "4/4", "3/4"
    sections : list[dict]
        For section marker text events.
    output_path : str
        Where to write the .mid file.
    quantization_strength : float
        0.0 = raw timing, 1.0 = fully quantized to grid.
    swing_ratio : float
        0.5 = straight, 0.667 = triplet swing. Applied during quantization.
    beat_times : list[float], optional
        Beat grid for quantization. Required if quantization_strength > 0.

    Returns
    -------
    dict with file_path, num_tracks, num_events, tick_resolution
    """
    try:
        import mido
    except ImportError:
        raise ImportError("mido package required for MIDI export. pip install mido")

    # Parse time signature
    ts_num, ts_den = _parse_time_signature(time_signature)

    # Build tempo map: list of (time_seconds, tempo_microseconds_per_beat)
    tempo_map = _build_tempo_map(tempo_curve)

    # Create MIDI file (Type 1 = multi-track)
    mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_QUARTER)

    # --- Track 0: Tempo + Time Signature + Section Markers ---
    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)

    # Time signature event at tick 0
    tempo_track.append(mido.MetaMessage(
        "time_signature",
        numerator=ts_num,
        denominator=ts_den,
        clocks_per_click=24,
        notated_32nd_notes_per_beat=8,
        time=0,
    ))

    # Tempo events
    last_tick = 0
    for tm in tempo_map:
        tick = _seconds_to_ticks(tm["time"], tempo_map, TICKS_PER_QUARTER)
        delta = max(0, tick - last_tick)
        tempo_track.append(mido.MetaMessage(
            "set_tempo",
            tempo=tm["tempo_us"],
            time=delta,
        ))
        last_tick = tick

    # Section markers as text events
    for sec in sections:
        tick = _seconds_to_ticks(sec.get("start_time", 0), tempo_map, TICKS_PER_QUARTER)
        delta = max(0, tick - last_tick)
        tempo_track.append(mido.MetaMessage(
            "text",
            text=sec.get("name", "Section"),
            time=delta,
        ))
        last_tick = tick

    tempo_track.append(mido.MetaMessage("end_of_track", time=0))

    # --- Group hits by type into separate tracks ---
    track_groups = {
        "Kick": ["kick"],
        "Snare": ["snare"],
        "Hi-Hat": ["hihat_closed", "hihat_open"],
        "Toms & Cymbals": ["tom", "cymbal", "unknown"],
    }

    total_events = 0

    for track_name, hit_types in track_groups.items():
        track_hits = [h for h in hits if h.get("hit_type") in hit_types]
        if not track_hits:
            continue

        track = mido.MidiTrack()
        mid.tracks.append(track)

        # Track name
        track.append(mido.MetaMessage("track_name", name=track_name, time=0))

        # Sort by time
        track_hits.sort(key=lambda h: h["time"])

        # Apply quantization if requested
        if quantization_strength > 0 and beat_times:
            track_hits = _quantize_hits(
                track_hits, beat_times, quantization_strength, swing_ratio
            )

        # Convert to MIDI events
        last_tick = 0
        for hit in track_hits:
            tick = _seconds_to_ticks(hit["time"], tempo_map, TICKS_PER_QUARTER)
            delta = max(0, tick - last_tick)

            note = hit.get("midi_note", 38)
            vel = max(1, min(127, hit.get("velocity", 80)))

            # Note on
            track.append(mido.Message(
                "note_on",
                channel=9,  # GM drums channel
                note=note,
                velocity=vel,
                time=delta,
            ))

            # Note off (short duration for percussion)
            note_off_ticks = max(1, TICKS_PER_QUARTER // 8)  # 1/32 note
            track.append(mido.Message(
                "note_off",
                channel=9,
                note=note,
                velocity=0,
                time=note_off_ticks,
            ))

            last_tick = tick + note_off_ticks
            total_events += 2

        track.append(mido.MetaMessage("end_of_track", time=0))

    # Write file
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(output_path))

    logger.info(
        f"MIDI exported: {output_path.name}, {len(mid.tracks)} tracks, "
        f"{total_events} events, quant={quantization_strength*100:.0f}%"
    )

    return {
        "file_path": str(output_path),
        "num_tracks": len(mid.tracks),
        "num_events": total_events,
        "tick_resolution": TICKS_PER_QUARTER,
        "quantization_strength": quantization_strength,
    }


# ---------------------------------------------------------------------------
# Click Track Generation (v2)
# ---------------------------------------------------------------------------


def generate_click_track(
    beat_times: list[float],
    downbeat_times: list[float],
    duration_seconds: float,
    output_path: str,
    mode: str = "quarter",
    swing_ratio: float = 0.5,
) -> dict:
    """
    Generate click WAV aligned to beat grid, with optional swing.

    Modes: "quarter", "eighth", "downbeat"
    """
    sr = settings.sample_rate
    total_samples = int(duration_seconds * sr) + sr
    click_audio = np.zeros(total_samples, dtype=np.float32)

    downbeat_click = _make_click(sr, freq=1500, dur_ms=15, amp=0.9)
    beat_click = _make_click(sr, freq=1000, dur_ms=10, amp=0.6)
    sub_click = _make_click(sr, freq=800, dur_ms=8, amp=0.35)

    downbeat_set = set(round(t, 3) for t in downbeat_times)

    if mode == "downbeat":
        for t in downbeat_times:
            _place_click(click_audio, downbeat_click, t, sr)
    elif mode == "eighth":
        for i, t in enumerate(beat_times):
            is_db = any(abs(t - dt) < 0.05 for dt in downbeat_set)
            _place_click(click_audio, downbeat_click if is_db else beat_click, t, sr)

            if i + 1 < len(beat_times):
                # Apply swing to subdivision
                period = beat_times[i + 1] - t
                sub_time = t + period * swing_ratio
                _place_click(click_audio, sub_click, sub_time, sr)
    else:  # quarter
        for t in beat_times:
            is_db = any(abs(t - dt) < 0.05 for dt in downbeat_set)
            _place_click(click_audio, downbeat_click if is_db else beat_click, t, sr)

    # Trim + normalize
    actual = min(len(click_audio), int(duration_seconds * sr))
    click_audio = click_audio[:actual]
    peak = np.max(np.abs(click_audio))
    if peak > 0:
        click_audio = click_audio / peak * 0.85

    sf.write(output_path, click_audio, sr, subtype="PCM_16")
    logger.info(f"Click track: {output_path} ({mode}, swing={swing_ratio:.2f})")

    return {
        "file_path": output_path,
        "mode": mode,
        "swing_ratio": swing_ratio,
        "sample_rate": sr,
        "duration_seconds": duration_seconds,
        "num_clicks": len(beat_times),
    }


# ---------------------------------------------------------------------------
# Waveform Peaks
# ---------------------------------------------------------------------------


def generate_waveform_peaks(
    audio_path: str,
    output_path: Optional[str] = None,
    points_per_second: int = 50,
) -> dict:
    """Generate downsampled waveform peak data."""
    import librosa as _lr

    y, sr = _lr.load(audio_path, sr=settings.sample_rate, mono=True)
    duration = _lr.get_duration(y=y, sr=sr)
    total_points = int(duration * points_per_second)
    spp = max(1, len(y) // total_points)

    peaks = []
    for i in range(0, len(y), spp):
        chunk = y[i:i + spp]
        if len(chunk) > 0:
            peaks.append({
                "min": round(float(np.min(chunk)), 4),
                "max": round(float(np.max(chunk)), 4),
                "rms": round(float(np.sqrt(np.mean(chunk ** 2))), 4),
            })

    result = {
        "peaks": peaks,
        "duration": round(duration, 3),
        "sample_rate": sr,
        "points_per_second": points_per_second,
        "total_points": len(peaks),
    }

    if output_path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(result, f)

    return result


# ---------------------------------------------------------------------------
# Internal: MIDI helpers
# ---------------------------------------------------------------------------


def _parse_time_signature(ts: str) -> tuple[int, int]:
    try:
        parts = ts.split("/")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 4, 4


def _build_tempo_map(tempo_curve: list[dict]) -> list[dict]:
    """
    Convert tempo curve [{time, bpm}] to [{time, tempo_us}].
    tempo_us = microseconds per quarter note.
    """
    if not tempo_curve:
        return [{"time": 0.0, "tempo_us": 500000, "bpm": 120.0}]

    tempo_map = []
    for point in tempo_curve:
        bpm = point.get("bpm", 120.0)
        if bpm <= 0:
            bpm = 120.0
        tempo_us = int(round(60_000_000 / bpm))
        tempo_map.append({
            "time": point["time"],
            "tempo_us": tempo_us,
            "bpm": bpm,
        })

    # Ensure there's a tempo at t=0
    if tempo_map[0]["time"] > 0:
        tempo_map.insert(0, {
            "time": 0.0,
            "tempo_us": tempo_map[0]["tempo_us"],
            "bpm": tempo_map[0]["bpm"],
        })

    return tempo_map


def _seconds_to_ticks(
    time_seconds: float,
    tempo_map: list[dict],
    ticks_per_quarter: int,
) -> int:
    """
    Convert absolute time in seconds to MIDI ticks using cumulative
    tempo integration.

    This avoids rounding drift by integrating across tempo changes:
      For each tempo segment, ticks += (segment_duration / tempo_seconds_per_beat) * tpq

    where tempo_seconds_per_beat = tempo_us / 1_000_000.
    """
    if not tempo_map:
        # Default 120 BPM
        beats = time_seconds * 2.0  # 120 BPM = 2 beats/sec
        return int(round(beats * ticks_per_quarter))

    total_ticks = 0.0
    remaining = time_seconds

    for i, tm in enumerate(tempo_map):
        # Duration of this tempo segment
        if i + 1 < len(tempo_map):
            segment_end = tempo_map[i + 1]["time"]
        else:
            segment_end = float("inf")

        segment_start = tm["time"]
        segment_duration = segment_end - segment_start

        # How much of `remaining` falls in this segment?
        time_in_segment = min(remaining, max(0.0, segment_duration))

        if time_in_segment <= 0:
            if remaining <= 0:
                break
            continue

        # Convert time → ticks at this tempo
        seconds_per_beat = tm["tempo_us"] / 1_000_000.0
        beats_in_segment = time_in_segment / seconds_per_beat
        total_ticks += beats_in_segment * ticks_per_quarter

        remaining -= time_in_segment
        if remaining <= 1e-9:
            break

    return int(round(total_ticks))


def _quantize_hits(
    hits: list[dict],
    beat_times: list[float],
    strength: float,
    swing_ratio: float = 0.5,
    subdivisions: int = 4,
) -> list[dict]:
    """
    Quantize hit times using percentage-based interpolation.

    quantized_time = raw_time + strength * (grid_time - raw_time)

    When swing_ratio != 0.5, the grid itself is swung:
      Off-beat grid positions are shifted by the swing ratio.
    """
    # Build subdivision grid (with swing)
    grid = []
    for i in range(len(beat_times) - 1):
        t0 = beat_times[i]
        t1 = beat_times[i + 1]
        period = t1 - t0
        for s in range(subdivisions):
            if s == 0:
                grid.append(t0)
            elif subdivisions == 2 and s == 1:
                # Apply swing to the off-beat
                grid.append(t0 + period * swing_ratio)
            elif subdivisions == 4:
                if s == 1:
                    grid.append(t0 + period * swing_ratio * 0.5)
                elif s == 2:
                    grid.append(t0 + period * swing_ratio)
                elif s == 3:
                    grid.append(t0 + period * (swing_ratio + (1 - swing_ratio) * 0.5))
            else:
                frac = s / subdivisions
                grid.append(t0 + period * frac)
    if beat_times:
        grid.append(beat_times[-1])

    grid_arr = np.array(grid)

    quantized = []
    for hit in hits:
        raw_time = hit["time"]
        # Find nearest grid point
        dists = np.abs(grid_arr - raw_time)
        nearest_idx = int(np.argmin(dists))
        grid_time = grid_arr[nearest_idx]

        # Interpolate
        q_time = raw_time + strength * (grid_time - raw_time)

        hit_copy = dict(hit)
        hit_copy["time"] = q_time
        hit_copy["raw_time"] = raw_time
        quantized.append(hit_copy)

    return quantized


# ---------------------------------------------------------------------------
# Internal: Click helpers
# ---------------------------------------------------------------------------


def _make_click(sr: int, freq: float = 1000, dur_ms: float = 10, amp: float = 0.8) -> np.ndarray:
    n = int(sr * dur_ms / 1000)
    t = np.linspace(0, dur_ms / 1000, n, endpoint=False)
    click = amp * np.sin(2 * np.pi * freq * t)
    envelope = np.exp(-t * 1000 / (dur_ms * 0.3))
    return (click * envelope).astype(np.float32)


def _place_click(audio: np.ndarray, click: np.ndarray, time: float, sr: int):
    start = int(time * sr)
    end = start + len(click)
    if start < 0 or start >= len(audio):
        return
    end = min(end, len(audio))
    audio[start:end] += click[:end - start]
