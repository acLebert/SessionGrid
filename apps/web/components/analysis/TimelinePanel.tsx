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
    <div className="glass-panel p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm text-zinc-400">Current section</p>
          <h2 className="text-2xl font-semibold">
            {currentSection?.name || "Full Track"}
          </h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {PLAYBACK_MODES.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => handleModeChange(key)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                playbackMode === key
                  ? "bg-cyan-400 text-zinc-950"
                  : "bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Waveform / Timeline */}
      <div className="mt-6 rounded-[28px] border border-white/10 bg-zinc-900/80 p-5">
        <div className="mb-4 flex items-center justify-between text-sm text-zinc-400">
          <span>Song timeline</span>
          {currentSection && (
            <span>
              Loop In{" "}
              {formatTime(currentSection.start_time)} • Loop Out{" "}
              {formatTime(currentSection.end_time)}
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
        <div className="mt-5 grid gap-3 md:grid-cols-4">
          <div className="stat-card">
            <p className="text-sm text-zinc-400">Tempo</p>
            <p className="mt-1 text-2xl font-semibold">
              {currentSection?.bpm || analysis.overall_bpm || "--"} BPM
            </p>
          </div>
          <div className="stat-card">
            <p className="text-sm text-zinc-400">Meter</p>
            <p className="mt-1 text-2xl font-semibold">
              {currentSection?.meter || analysis.time_signature || "--"}
            </p>
          </div>
          <div className="stat-card">
            <p className="text-sm text-zinc-400">Bars</p>
            <p className="mt-1 text-2xl font-semibold">
              {currentSection?.bars || "--"}
            </p>
          </div>
          <div className="stat-card">
            <p className="text-sm text-zinc-400">Confidence</p>
            <p
              className={`mt-1 text-2xl font-semibold ${
                currentSection?.confidence === "high"
                  ? "text-emerald-300"
                  : currentSection?.confidence === "medium"
                  ? "text-amber-300"
                  : "text-rose-300"
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
