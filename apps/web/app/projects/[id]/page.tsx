"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Music2,
  Layers,
  Download,
  SkipBack,
  SkipForward,
  Play,
  Pause,
  Repeat,
  Volume2,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import {
  getProject,
  getProjectStatus,
  triggerAnalysis,
  getWaveformData,
} from "@/lib/api";
import type { Project, ProjectStatus, Section, WaveformData } from "@/lib/types";
import { AudioEngineProvider, useAudioEngine } from "@/components/player/AudioEngine";
import { ArrangementMap } from "@/components/analysis/ArrangementMap";
import { ExportPanel } from "@/components/analysis/ExportPanel";
import { ProcessingView } from "@/components/analysis/ProcessingView";
import { RhythmDebugPanel } from "@/components/analysis/RhythmDebugPanel"; // DEBUG ONLY

/* ─── Constants ───────────────────────────────────────────────────── */

const TRACK_COLORS: Record<string, string> = {
  vocals: "#818cf8",
  drums: "#f59e0b",
  bass: "#22d3ee",
  other: "#a78bfa",
  click: "#6b7280",
};

const STEM_ORDER = ["vocals", "drums", "bass", "other"];
const TRACK_HEIGHT = 80;

interface TrackDef {
  id: string;
  name: string;
  color: string;
  stemType: string;
}

/* ─── Helpers ─────────────────────────────────────────────────────── */

function getTracksForProject(project: Project): TrackDef[] {
  const stemTypes = new Set(project.stems.map((s) => s.stem_type));
  const tracks: TrackDef[] = [];

  for (const type of STEM_ORDER) {
    if (stemTypes.has(type)) {
      tracks.push({
        id: type,
        name: type.charAt(0).toUpperCase() + type.slice(1),
        color: TRACK_COLORS[type] || "#94a3b8",
        stemType: type,
      });
    }
  }
  if (project.click_track) {
    tracks.push({
      id: "click",
      name: "Smart Metronome",
      color: TRACK_COLORS.click,
      stemType: "click",
    });
  }
  return tracks;
}

function getSectionColor(name: string): string {
  const lower = name.toLowerCase();
  if (lower.includes("intro")) return "#3b82f6";
  if (lower.includes("verse")) return "#22c55e";
  if (lower.includes("pre")) return "#eab308";
  if (lower.includes("chorus")) return "#ef4444";
  if (lower.includes("bridge")) return "#a855f7";
  if (lower.includes("outro")) return "#6b7280";
  if (lower.includes("solo")) return "#f97316";
  const hash = name.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  const palette = ["#64748b", "#78716c", "#71717a", "#737373"];
  return palette[hash % palette.length];
}

function generateFakePeaks(
  stemType: string,
  numPoints: number,
  duration: number
): WaveformData {
  const seed = stemType.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  let rng = seed;
  const next = () => {
    rng = (rng * 16807) % 2147483647;
    return rng / 2147483647;
  };
  const amp: Record<string, number> = {
    vocals: 0.65,
    drums: 0.8,
    bass: 0.6,
    other: 0.5,
    click: 0.25,
  };
  const a = amp[stemType] || 0.6;
  const peaks = Array.from({ length: numPoints }, (_, i) => {
    const t = i / numPoints;
    const env = Math.sin(t * Math.PI) * 0.5 + 0.5;
    const n = next();
    const v = env * a * (0.3 + n * 0.7);
    return { min: -v, max: v, rms: v * 0.7 };
  });
  return {
    peaks,
    duration,
    sample_rate: 44100,
    points_per_second: numPoints / duration,
    total_points: numPoints,
  };
}

function formatTime(s: number): string {
  if (!s || !isFinite(s)) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

/* ─── Track Waveform Canvas ───────────────────────────────────────── */

function TrackWaveformCanvas({
  waveformData,
  color,
  playheadFraction,
  sections,
  activeSection,
  duration,
  isSolo,
  isMuted,
  onSeek,
}: {
  waveformData: WaveformData | null;
  color: string;
  playheadFraction: number;
  sections: Section[];
  activeSection: number;
  duration: number;
  isSolo: boolean;
  isMuted: boolean;
  onSeek: (fraction: number) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || !waveformData) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = container.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    const cy = h / 2;
    const { peaks } = waveformData;

    ctx.clearRect(0, 0, w, h);

    // Parse hex color
    const r = parseInt(color.slice(1, 3), 16);
    const g = parseInt(color.slice(3, 5), 16);
    const b = parseInt(color.slice(5, 7), 16);

    const alphaBase = isMuted ? 0.06 : isSolo ? 0.6 : 0.25;
    const alphaPlayed = isMuted ? 0.1 : isSolo ? 1 : 0.45;

    // Section boundaries
    sections.forEach((section, idx) => {
      if (idx === 0) return;
      const sx = (section.start_time / duration) * w;
      ctx.strokeStyle = "rgba(255,255,255,0.03)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(sx, 0);
      ctx.lineTo(sx, h);
      ctx.stroke();
    });

    // Active section highlight
    if (activeSection >= 0 && sections[activeSection]) {
      const sec = sections[activeSection];
      const sx = (sec.start_time / duration) * w;
      const ex = (sec.end_time / duration) * w;
      ctx.fillStyle = `rgba(${r},${g},${b},0.04)`;
      ctx.fillRect(sx, 0, ex - sx, h);
    }

    // Waveform bars
    const gap = w / peaks.length;
    const barW = Math.max(1, gap * 0.65);

    for (let i = 0; i < peaks.length; i++) {
      const peak = peaks[i];
      const x = i * gap;
      const played = i / peaks.length <= playheadFraction;
      const alpha = played ? alphaPlayed : alphaBase;
      const maxH = Math.abs(peak.max) * cy * 0.92;
      const minH = Math.abs(peak.min) * cy * 0.92;

      ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
      ctx.fillRect(x, cy - maxH, barW, maxH);
      ctx.fillRect(x, cy, barW, minH);
    }
  }, [waveformData, color, playheadFraction, sections, activeSection, duration, isSolo, isMuted]);

  const handleClick = (e: React.MouseEvent | React.TouchEvent) => {
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const clientX = "touches" in e ? e.changedTouches[0].clientX : e.clientX;
    const fraction = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    onSeek(fraction);
  };

  return (
    <div
      ref={containerRef}
      className="relative h-full cursor-crosshair"
      onClick={handleClick}
      onTouchEnd={handleClick}
    >
      <canvas ref={canvasRef} className="absolute inset-0" />
    </div>
  );
}

/* ─── Beat Ruler Canvas ───────────────────────────────────────────── */

function BeatRulerCanvas({
  duration,
  beats,
  downbeats,
}: {
  duration: number;
  beats: number[] | null;
  downbeats: number[] | null;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = container.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    ctx.clearRect(0, 0, w, h);

    if (downbeats) {
      let measure = 1;
      const downbeatSet = new Set(downbeats.map((d) => d.toFixed(2)));
      downbeats.forEach((t) => {
        const x = (t / duration) * w;
        ctx.strokeStyle = "rgba(255,255,255,0.18)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, h * 0.3);
        ctx.lineTo(x, h);
        ctx.stroke();

        ctx.fillStyle = "rgba(255,255,255,0.35)";
        ctx.font = "9px Inter, system-ui, sans-serif";
        ctx.fillText(String(measure), x + 3, h * 0.42);
        measure++;
      });

      if (beats) {
        beats.forEach((t) => {
          if (downbeatSet.has(t.toFixed(2))) return;
          const x = (t / duration) * w;
          ctx.strokeStyle = "rgba(255,255,255,0.06)";
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(x, h * 0.6);
          ctx.lineTo(x, h);
          ctx.stroke();
        });
      }
    }
  }, [duration, beats, downbeats]);

  return (
    <div ref={containerRef} className="h-full w-full">
      <canvas ref={canvasRef} className="h-full w-full" />
    </div>
  );
}

/* ─── Section Sync (renderless) ───────────────────────────────────── */

function SectionSync({
  sections,
  activeSection,
  isLooping,
  onAutoSection,
}: {
  sections: Section[];
  activeSection: number;
  isLooping: boolean;
  onAutoSection: (idx: number) => void;
}) {
  const audio = useAudioEngine();
  const prevActiveRef = useRef(activeSection);

  useEffect(() => {
    if (
      isLooping &&
      activeSection >= 0 &&
      activeSection !== prevActiveRef.current
    ) {
      const section = sections[activeSection];
      if (section) audio.seek(section.start_time);
    }
    prevActiveRef.current = activeSection;
  }, [activeSection, isLooping, sections, audio]);

  const ct = audio.currentTime;
  useEffect(() => {
    if (isLooping) return;
    const idx = sections.findIndex(
      (s) => ct >= s.start_time && ct < s.end_time
    );
    if (idx >= 0 && idx !== activeSection) onAutoSection(idx);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Math.floor(ct), isLooping]);

  return null;
}

/* ═══════════════════════════════════════════════════════════════════
   DAW Content — The multi-track studio interface
   ═══════════════════════════════════════════════════════════════════ */

function DAWContent({
  project,
  activeSection,
  setActiveSection,
  isLooping,
  setIsLooping,
}: {
  project: Project;
  activeSection: number;
  setActiveSection: (idx: number) => void;
  isLooping: boolean;
  setIsLooping: (v: boolean) => void;
}) {
  const audio = useAudioEngine();
  const analysis = project.analysis!;
  const tracks = useMemo(() => getTracksForProject(project), [project]);
  const duration = project.duration_seconds || 240;

  const [rightPanel, setRightPanel] = useState<"sections" | "export" | null>(
    "sections"
  );
  const [soloTrack, setSoloTrack] = useState<string | null>(null);
  const [mutedTracks, setMutedTracks] = useState<Set<string>>(new Set());
  const [trackWaveforms, setTrackWaveforms] = useState<
    Record<string, WaveformData>
  >({});

  const playheadFraction =
    audio.duration > 0 ? audio.currentTime / audio.duration : 0;

  // Fetch waveform data for all tracks
  useEffect(() => {
    tracks.forEach(async (track) => {
      try {
        const data = await getWaveformData(project.id, track.stemType);
        setTrackWaveforms((prev) => ({ ...prev, [track.id]: data }));
      } catch {
        const fake = generateFakePeaks(track.stemType, 500, duration);
        setTrackWaveforms((prev) => ({ ...prev, [track.id]: fake }));
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  // Map solo track → playback mode
  useEffect(() => {
    if (!soloTrack) {
      audio.setPlaybackMode("mix");
    } else if (
      soloTrack === "drums" ||
      soloTrack === "vocals" ||
      soloTrack === "bass" ||
      soloTrack === "other"
    ) {
      audio.setPlaybackMode(soloTrack as "drums" | "vocals" | "bass" | "other");
    } else if (soloTrack === "click") {
      audio.setPlaybackMode("click");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [soloTrack]);

  function handleSolo(trackId: string) {
    setSoloTrack((prev) => (prev === trackId ? null : trackId));
  }

  function handleMute(trackId: string) {
    setMutedTracks((prev) => {
      const next = new Set(prev);
      if (next.has(trackId)) next.delete(trackId);
      else next.add(trackId);
      return next;
    });
  }

  function handleSeek(fraction: number) {
    audio.seekFraction(fraction);
    const time = fraction * (audio.duration || duration);
    const idx = project.sections.findIndex(
      (s) => time >= s.start_time && time < s.end_time
    );
    if (idx >= 0) setActiveSection(idx);
  }

  function handleArrangementSelect(idx: number) {
    if (idx < 0 || idx === activeSection) {
      setActiveSection(-1);
      setIsLooping(false);
    } else {
      setActiveSection(idx);
      setIsLooping(true);
    }
  }

  return (
    <>
      <SectionSync
        sections={project.sections}
        activeSection={activeSection}
        isLooping={isLooping}
        onAutoSection={(idx) => setActiveSection(idx)}
      />

      {/* ─── Header ──────────────────────────────────────────── */}
      <header className="daw-header">
        <div className="flex items-center gap-3 min-w-0">
          <Link href="/projects" className="daw-header-btn">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <Music2 className="h-4 w-4 shrink-0 text-[#22d3ee]" />
          <h1 className="truncate text-sm font-semibold text-white">
            {project.name}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <span className="daw-pill hidden tablet:inline-flex">
            <span className="text-[#22d3ee]">♩</span>{" "}
            {analysis.overall_bpm || "--"}
          </span>
          <span className="daw-pill hidden tablet:inline-flex">
            {analysis.time_signature || "4/4"}
          </span>
          <span className="daw-pill hidden tablet:inline-flex">
            {project.sections.length} sections
          </span>
          <button
            onClick={() =>
              setRightPanel((prev) => (prev ? null : "sections"))
            }
            className="daw-header-btn"
            title="Toggle sections panel"
          >
            <Layers className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* ─── Main Content ────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Icon Rail */}
        <nav className="daw-icon-rail hidden tablet:flex">
          {(
            [
              { id: "sections", icon: Layers, label: "Sections" },
              { id: "export", icon: Download, label: "Export" },
            ] as const
          ).map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() =>
                setRightPanel((prev) =>
                  prev === id ? null : (id as "sections" | "export")
                )
              }
              className={`daw-rail-btn ${rightPanel === id ? "active" : ""}`}
              title={label}
            >
              <Icon className="h-5 w-5" />
            </button>
          ))}
        </nav>

        {/* Tracks Area */}
        <div className="flex flex-1 overflow-hidden">
          {/* Track Headers Column */}
          <div className="daw-headers-col">
            {/* Spacer for section markers + ruler */}
            <div className="h-[52px] border-b border-white/[0.04]" />

            {tracks.map((track) => (
              <div
                key={track.id}
                className="daw-track-header"
                style={{ height: `${TRACK_HEIGHT}px` }}
              >
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => handleMute(track.id)}
                    className={`daw-mute-btn ${mutedTracks.has(track.id) ? "active" : ""}`}
                    title={
                      mutedTracks.has(track.id)
                        ? `Unmute ${track.name}`
                        : `Mute ${track.name}`
                    }
                  >
                    M
                  </button>
                  <button
                    onClick={() => handleSolo(track.id)}
                    className={`daw-solo-btn ${soloTrack === track.id ? "active" : ""}`}
                    title={
                      soloTrack === track.id
                        ? `Unsolo ${track.name}`
                        : `Solo ${track.name}`
                    }
                  >
                    S
                  </button>
                  <span
                    className="ml-1 truncate text-xs font-medium"
                    style={{
                      color:
                        soloTrack === track.id ? track.color : undefined,
                    }}
                  >
                    {track.name}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center gap-2">
                  <input
                    type="range"
                    min={0}
                    max={100}
                    defaultValue={80}
                    className="daw-volume-slider"
                  />
                  <div
                    className="daw-pan-knob"
                    style={{ borderColor: `${track.color}40` }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Timeline Column */}
          <div className="relative flex-1 overflow-hidden bg-[#0a0a0c]">
            {/* Section markers */}
            <div className="daw-section-markers">
              {project.sections.map((section, idx) => {
                const widthPct =
                  ((section.end_time - section.start_time) / duration) * 100;
                const color = getSectionColor(section.name);
                return (
                  <button
                    key={section.id}
                    onClick={() => handleArrangementSelect(idx)}
                    className={`daw-section-block ${idx === activeSection ? "active" : ""}`}
                    style={{
                      width: `${widthPct}%`,
                      backgroundColor:
                        idx === activeSection
                          ? `${color}30`
                          : `${color}15`,
                      borderColor: `${color}60`,
                    }}
                    title={`${section.name} (${formatTime(section.start_time)})`}
                  >
                    <span className="truncate" style={{ color }}>
                      {section.name}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Beat Ruler */}
            <div className="h-[24px] border-b border-white/[0.04] bg-[#0c0c0f]">
              <BeatRulerCanvas
                duration={duration}
                beats={analysis.beats_json}
                downbeats={analysis.downbeats_json}
              />
            </div>

            {/* Track Waveforms */}
            {tracks.map((track) => (
              <div
                key={track.id}
                className="border-b border-white/[0.03]"
                style={{ height: `${TRACK_HEIGHT}px` }}
              >
                <TrackWaveformCanvas
                  waveformData={trackWaveforms[track.id] || null}
                  color={track.color}
                  playheadFraction={playheadFraction}
                  sections={project.sections}
                  activeSection={activeSection}
                  duration={duration}
                  isSolo={soloTrack === track.id}
                  isMuted={mutedTracks.has(track.id)}
                  onSeek={handleSeek}
                />
              </div>
            ))}

            {/* Playhead overlay */}
            <div
              className="daw-playhead"
              style={{ left: `${playheadFraction * 100}%` }}
            >
              <div className="daw-playhead-line" />
              <div className="daw-playhead-head" />
            </div>
          </div>
        </div>

        {/* Right Panel */}
        {rightPanel && (
          <aside className="daw-right-panel animate-fade-in">
            <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2.5">
              <div className="flex gap-1">
                <button
                  onClick={() => setRightPanel("sections")}
                  className={`daw-panel-tab ${rightPanel === "sections" ? "active" : ""}`}
                >
                  Sections
                </button>
                <button
                  onClick={() => setRightPanel("export")}
                  className={`daw-panel-tab ${rightPanel === "export" ? "active" : ""}`}
                >
                  Export
                </button>
              </div>
              <button
                onClick={() => setRightPanel(null)}
                className="daw-header-btn"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3 scrollbar-none">
              {rightPanel === "sections" && (
                <ArrangementMap
                  sections={project.sections}
                  activeSection={activeSection}
                  onSectionSelect={handleArrangementSelect}
                />
              )}
              {rightPanel === "export" && (
                <ExportPanel projectId={project.id} />
              )}
              {/* DEBUG ONLY — Rhythm Engine Debug Panel */}
              <RhythmDebugPanel projectId={project.id} />
            </div>
          </aside>
        )}
      </div>

      {/* ─── Transport Bar ───────────────────────────────────── */}
      <div className="daw-transport">
        {/* Transport Controls */}
        <div className="flex items-center gap-0.5">
          <button className="daw-transport-btn" title="Volume">
            <Volume2 className="h-4 w-4" />
          </button>
          <button
            className="daw-transport-btn"
            onClick={() => audio.seek(Math.max(0, audio.currentTime - 5))}
            title="Rewind 5s"
          >
            <SkipBack className="h-4 w-4" />
          </button>
          <button
            className="daw-transport-btn-primary"
            onClick={audio.toggle}
            title={audio.isPlaying ? "Pause" : "Play"}
          >
            {audio.isPlaying ? (
              <Pause className="h-5 w-5" />
            ) : (
              <Play className="ml-0.5 h-5 w-5" />
            )}
          </button>
          <button
            className="daw-transport-btn"
            onClick={() =>
              audio.seek(Math.min(audio.duration, audio.currentTime + 5))
            }
            title="Forward 5s"
          >
            <SkipForward className="h-4 w-4" />
          </button>
          <button
            className={`daw-transport-btn ${isLooping ? "text-[#22d3ee]" : ""}`}
            onClick={() => setIsLooping(!isLooping)}
            title="Loop"
          >
            <Repeat className="h-4 w-4" />
          </button>
        </div>

        {/* Scrubber */}
        <div className="mx-4 flex flex-1 items-center gap-3">
          <span className="daw-time">{formatTime(audio.currentTime)}</span>
          <input
            type="range"
            min={0}
            max={audio.duration || 1}
            step={0.01}
            value={audio.currentTime}
            onChange={(e) => audio.seek(Number(e.target.value))}
            className="daw-scrubber flex-1"
          />
          <span className="daw-time">{formatTime(audio.duration)}</span>
        </div>

        {/* Speed Controls */}
        <div className="hidden items-center gap-0.5 tablet:flex">
          {[0.5, 1, 2].map((rate) => (
            <button
              key={rate}
              onClick={() => audio.setPlaybackRate(rate)}
              className={`daw-speed-btn ${audio.playbackRate === rate ? "active" : ""}`}
            >
              {rate}x
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   Page Component
   ═══════════════════════════════════════════════════════════════════ */

export default function ProjectPage() {
  const params = useParams();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState<number>(-1);
  const [isLooping, setIsLooping] = useState(false);

  const loadProject = useCallback(async () => {
    try {
      const data = await getProject(projectId);
      setProject(data);
      setLoading(false);
    } catch (err) {
      console.error("Failed to load project:", err);
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadProject();
  }, [loadProject]);

  // Poll while processing
  useEffect(() => {
    if (!project) return;
    const isProcessing = !["complete", "failed"].includes(project.status);
    if (!isProcessing) return;

    const interval = setInterval(async () => {
      try {
        const status = await getProjectStatus(projectId);
        if (status.status === "complete" || status.status === "failed") {
          await loadProject();
          clearInterval(interval);
        } else {
          setProject((prev) =>
            prev
              ? {
                  ...prev,
                  status: status.status as ProjectStatus,
                  status_message: status.status_message,
                }
              : prev
          );
        }
      } catch {
        clearInterval(interval);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [project?.status, projectId, loadProject]);

  /* ── Loading ─────────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0a0a0c]">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-[#22d3ee] border-t-transparent" />
      </div>
    );
  }

  /* ── Not Found ───────────────────────────────────────────── */
  if (!project) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-[#0a0a0c]">
        <p className="text-[#8e8e93]">Project not found</p>
        <Link
          href="/"
          className="rounded-lg bg-[#22d3ee] px-4 py-2 text-sm font-semibold text-black"
        >
          Go Home
        </Link>
      </div>
    );
  }

  const isProcessing = !["complete", "failed"].includes(project.status);

  /* ── Processing ──────────────────────────────────────────── */
  if (isProcessing) {
    return (
      <div className="flex h-screen flex-col bg-[#0a0a0c]">
        <header className="daw-header">
          <div className="flex items-center gap-3">
            <Link href="/projects" className="daw-header-btn">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <h1 className="text-sm font-semibold text-white">
              {project.name}
            </h1>
          </div>
        </header>
        <div className="flex flex-1 items-center justify-center px-4">
          <ProcessingView
            status={project.status}
            message={project.status_message}
          />
        </div>
      </div>
    );
  }

  /* ── Failed ──────────────────────────────────────────────── */
  if (project.status === "failed") {
    return (
      <div className="flex h-screen flex-col bg-[#0a0a0c]">
        <header className="daw-header">
          <div className="flex items-center gap-3">
            <Link href="/projects" className="daw-header-btn">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <h1 className="text-sm font-semibold text-white">
              {project.name}
            </h1>
          </div>
        </header>
        <div className="flex flex-1 flex-col items-center justify-center px-4 text-center">
          <p className="text-lg font-semibold text-rose-300">
            Analysis Failed
          </p>
          <p className="mt-2 text-sm text-[#8e8e93]">
            {project.status_message}
          </p>
          <button
            onClick={async () => {
              await triggerAnalysis(project.id);
              loadProject();
            }}
            className="mt-4 flex items-center gap-2 rounded-lg bg-[#1c1c20] px-4 py-2 text-sm text-white hover:bg-[#222228]"
          >
            <RefreshCw className="h-4 w-4" /> Retry
          </button>
        </div>
      </div>
    );
  }

  /* ── Complete → DAW View ─────────────────────────────────── */
  if (project.status === "complete" && project.analysis) {
    return (
      <div className="flex h-screen flex-col bg-[#0a0a0c] text-[#e5e5ea]">
        <AudioEngineProvider projectId={project.id}>
          <DAWContent
            project={project}
            activeSection={activeSection}
            setActiveSection={setActiveSection}
            isLooping={isLooping}
            setIsLooping={setIsLooping}
          />
        </AudioEngineProvider>
      </div>
    );
  }

  return null;
}
