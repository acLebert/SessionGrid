"use client";

import type { Project, Section } from "@/lib/types";
import { PLAYBACK_MODES } from "@/lib/types";
import { WaveformDisplay } from "@/components/player/WaveformDisplay";
import { useAudioEngine } from "@/components/player/AudioEngine";

interface TimelinePanelProps {
  project: Project;
  currentSection: Section | null;
  activeSection: number;
  playbackMode: string;
  onPlaybackModeChange: (mode: string) => void;
  onSectionSelect?: (index: number) => void;
}

export function TimelinePanel({
  project,
  currentSection,
  activeSection,
  playbackMode,
  onPlaybackModeChange,
  onSectionSelect,
}: TimelinePanelProps) {
  const analysis = project.analysis!;
  const audio = useAudioEngine();

  const handleModeChange = (mode: string) => {
    onPlaybackModeChange(mode);
    audio.setPlaybackMode(mode as "mix" | "drums" | "click" | "click_drums");
  };

  return (
    <div className="card p-4 tablet:p-5">
      {/* Header row */}
      <div className="flex flex-col gap-3 tablet:flex-row tablet:items-center tablet:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-text-muted">
            Now playing
          </p>
          <h2 className="mt-0.5 text-xl font-semibold tablet:text-2xl">
            {currentSection?.name || "Full Track"}
          </h2>
        </div>

        {/* Segmented Control for playback mode */}
        <div className="segmented-control overflow-x-auto scrollbar-none">
          {PLAYBACK_MODES.map(({ key, label }) => (
            <button
              key={key}
              data-active={playbackMode === key}
              onClick={() => handleModeChange(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Waveform / Timeline */}
      <div className="mt-5 rounded-xl border border-white/[0.06] bg-surface p-4">
        <div className="mb-3 flex items-center justify-between text-xs text-text-muted">
          <span>Song timeline</span>
          {currentSection && (
            <span>
              Loop: {formatTime(currentSection.start_time)} → {formatTime(currentSection.end_time)}
            </span>
          )}
        </div>

        {/* Waveform Visualization */}
        <WaveformDisplay
          projectId={project.id}
          sections={project.sections}
          activeSection={activeSection}
          playbackMode={playbackMode}
          onSectionSelect={onSectionSelect}
        />

        {/* Stats Row */}
        <div className="mt-4 grid grid-cols-2 gap-2 tablet:grid-cols-4">
          <div className="stat-card">
            <p className="text-xs text-text-muted">Tempo</p>
            <p className="mt-1 text-lg font-semibold tablet:text-xl">
              {currentSection?.bpm || analysis.overall_bpm || "--"}
              <span className="ml-0.5 text-xs font-normal text-text-muted">BPM</span>
            </p>
          </div>
          <div className="stat-card">
            <p className="text-xs text-text-muted">Meter</p>
            <p className="mt-1 text-lg font-semibold tablet:text-xl">
              {currentSection?.meter || analysis.time_signature || "--"}
            </p>
          </div>
          <div className="stat-card">
            <p className="text-xs text-text-muted">Bars</p>
            <p className="mt-1 text-lg font-semibold tablet:text-xl">
              {currentSection?.bars || "--"}
            </p>
          </div>
          <div className="stat-card">
            <p className="text-xs text-text-muted">Confidence</p>
            <p
              className={`mt-1 text-lg font-semibold tablet:text-xl ${
                currentSection?.confidence === "high"
                  ? "text-emerald-400"
                  : currentSection?.confidence === "medium"
                  ? "text-amber-400"
                  : currentSection?.confidence === "low"
                  ? "text-rose-400"
                  : "text-text-muted"
              }`}
            >
              {currentSection?.confidence
                ? currentSection.confidence.charAt(0).toUpperCase() +
                  currentSection.confidence.slice(1)
                : "--"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
