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
    <div className="space-y-1">
      {/* Full Track (no loop) */}
      <button
        onClick={() => onSectionSelect(-1)}
        className={`daw-section-item ${activeSection < 0 ? "active" : ""}`}
      >
        <span className="daw-section-num">▶</span>
        <div>
          <p className="text-sm font-medium">Full Track</p>
          <p className="text-[11px] text-[#5c5c66]">Free playback</p>
        </div>
      </button>

      {sections.map((section, idx) => (
        <button
          key={section.id}
          onClick={() => onSectionSelect(idx)}
          className={`daw-section-item ${idx === activeSection ? "active" : ""}`}
        >
          <span className="daw-section-num">{idx + 1}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{section.name}</p>
            <p className="truncate text-[11px] text-[#5c5c66]">
              {formatTime(section.start_time)} · {section.bars ?? "?"} bars
              {section.bpm ? ` · ${section.bpm}` : ""}
            </p>
          </div>
          <ConfidenceBadge level={section.confidence} />
        </button>
      ))}
    </div>
  );
}
