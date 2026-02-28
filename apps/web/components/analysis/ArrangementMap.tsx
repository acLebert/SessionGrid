"use client";

import type { Section } from "@/lib/types";
import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";

interface ArrangementMapProps {
  sections: Section[];
  activeSection: number;
  onSectionSelect: (index: number) => void;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function ArrangementMap({
  sections,
  activeSection,
  onSectionSelect,
}: ArrangementMapProps) {
  return (
    <div className="glass-panel flex max-h-[calc(100vh-12rem)] flex-col p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Arrangement Map</h2>
        <span className="rounded-full bg-zinc-800 px-2.5 py-0.5 text-xs text-zinc-400">
          {sections.length} sections
        </span>
      </div>
      <div className="mt-4 -mr-2 flex-1 space-y-2 overflow-y-auto pr-2">
        {/* Full Track (no loop) */}
        <button
          onClick={() => onSectionSelect(-1)}
          className={`w-full rounded-2xl border p-3 text-left transition-all ${
            activeSection < 0
              ? "border-cyan-400/30 bg-cyan-400/10 shadow-lg shadow-cyan-400/5"
              : "border-white/10 bg-zinc-900/70 hover:bg-zinc-900"
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-md bg-zinc-800 text-[10px] font-medium text-zinc-400">
              ▶
            </span>
            <p className="text-sm font-medium">Full Track</p>
          </div>
          <p className="mt-1 pl-7 text-xs text-zinc-500">
            No loop — play the whole song freely
          </p>
        </button>

        {sections.map((section, idx) => (
          <button
            key={section.id}
            onClick={() => onSectionSelect(idx)}
            className={`w-full rounded-2xl border p-3 text-left transition-all ${
              idx === activeSection
                ? "border-cyan-400/30 bg-cyan-400/10 shadow-lg shadow-cyan-400/5"
                : "border-white/10 bg-zinc-900/70 hover:bg-zinc-900"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-md bg-zinc-800 text-[10px] font-medium text-zinc-400">
                    {idx + 1}
                  </span>
                  <p className="truncate text-sm font-medium">{section.name}</p>
                </div>
                <p className="mt-1 truncate pl-7 text-xs text-zinc-500">
                  {formatTime(section.start_time)} •{" "}
                  {section.bars ?? "?"} bars •{" "}
                  {section.bpm ?? "--"} BPM •{" "}
                  {section.meter || "--"}
                </p>
              </div>
              <ConfidenceBadge level={section.confidence} />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
