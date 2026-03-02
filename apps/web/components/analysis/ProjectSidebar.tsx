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
}: ProjectSidebarProps) {
  const analysis = project.analysis!;

  return (
    <aside className="space-y-4">
      {/* Project Info */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
          Project
        </h2>
        <div className="mt-3 rounded-xl border border-dashed border-white/[0.08] bg-surface p-3.5">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs text-text-muted">Uploaded file</span>
            <span className="badge border-emerald-500/25 bg-emerald-500/10 text-emerald-400">
              Ready
            </span>
          </div>
          <p className="text-sm font-medium">{project.original_filename}</p>
          <p className="mt-1 text-xs text-text-muted">
            {project.duration_seconds
              ? `${Math.floor(project.duration_seconds / 60)}:${Math.floor(project.duration_seconds % 60).toString().padStart(2, "0")}`
              : "--:--"}{" "}
            · Audio extracted · Drum stem generated
          </p>
        </div>

        {/* Confidence Indicators */}
        <div className="mt-4 space-y-1.5">
          {[
            { label: "Stem quality", value: analysis.confidence_stem },
            { label: "Beat grid", value: analysis.confidence_beat },
            { label: "Meter map", value: analysis.confidence_meter },
            { label: "Section detection", value: analysis.confidence_sections },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="flex items-center justify-between rounded-lg bg-surface px-3 py-2.5"
            >
              <span className="text-sm text-text-secondary">{label}</span>
              <ConfidenceBadge level={value} inline />
            </div>
          ))}
        </div>
      </div>

      {/* Analysis Summary */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
          Analysis
        </h2>
        <div className="mt-3 space-y-1.5">
          {[
            { label: "Overall BPM", value: analysis.overall_bpm ?? "--" },
            { label: "Time signature", value: analysis.time_signature ?? "--" },
            { label: "Tempo stable", value: analysis.bpm_stable ? "Yes" : "No" },
            { label: "Sections", value: project.sections.length },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="flex items-center justify-between rounded-lg bg-surface px-3 py-2.5"
            >
              <span className="text-sm text-text-secondary">{label}</span>
              <span className="text-sm font-medium">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
