"use client";

import type { Project } from "@/lib/types";
import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";

interface ProjectSidebarProps {
  project: Project;
  playbackMode: string;
  onPlaybackModeChange: (mode: string) => void;
}

export function ProjectSidebar({
  project,
  playbackMode,
  onPlaybackModeChange,
}: ProjectSidebarProps) {
  const analysis = project.analysis!;

  return (
    <aside className="space-y-6">
      {/* Project Info */}
      <div className="glass-panel p-5">
        <h2 className="text-lg font-semibold">Project</h2>
        <div className="mt-4 rounded-2xl border border-dashed border-white/15 bg-zinc-900/70 p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm text-zinc-400">Uploaded file</span>
            <span className="rounded-full bg-cyan-400/15 px-2 py-1 text-xs font-medium text-cyan-300">
              Ready
            </span>
          </div>
          <p className="font-medium">{project.original_filename}</p>
          <p className="mt-1 text-sm text-zinc-400">
            {project.duration_seconds
              ? `${Math.floor(project.duration_seconds / 60)}:${Math.floor(project.duration_seconds % 60).toString().padStart(2, "0")}`
              : "--:--"}{" "}
            • Audio extracted • Drum stem generated
          </p>
        </div>

        {/* Confidence Indicators */}
        <div className="mt-5 space-y-3 text-sm">
          {[
            { label: "Stem quality", value: analysis.confidence_stem },
            { label: "Beat grid", value: analysis.confidence_beat },
            { label: "Meter map", value: analysis.confidence_meter },
            { label: "Section detection", value: analysis.confidence_sections },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="flex items-center justify-between rounded-2xl bg-zinc-900/70 px-3 py-3"
            >
              <span className="text-zinc-400">{label}</span>
              <ConfidenceBadge level={value} inline />
            </div>
          ))}
        </div>
      </div>

      {/* Analysis Summary */}
      <div className="glass-panel p-5">
        <h2 className="text-lg font-semibold">Analysis</h2>
        <div className="mt-4 space-y-3 text-sm">
          <div className="flex items-center justify-between rounded-2xl bg-zinc-900/70 px-3 py-3">
            <span className="text-zinc-400">Overall BPM</span>
            <span className="font-medium">{analysis.overall_bpm ?? "--"}</span>
          </div>
          <div className="flex items-center justify-between rounded-2xl bg-zinc-900/70 px-3 py-3">
            <span className="text-zinc-400">Time signature</span>
            <span className="font-medium">{analysis.time_signature ?? "--"}</span>
          </div>
          <div className="flex items-center justify-between rounded-2xl bg-zinc-900/70 px-3 py-3">
            <span className="text-zinc-400">Tempo stable</span>
            <span className="font-medium">{analysis.bpm_stable ? "Yes" : "No"}</span>
          </div>
          <div className="flex items-center justify-between rounded-2xl bg-zinc-900/70 px-3 py-3">
            <span className="text-zinc-400">Sections</span>
            <span className="font-medium">{project.sections.length}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
