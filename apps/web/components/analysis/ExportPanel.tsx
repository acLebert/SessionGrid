"use client";

import { Download } from "lucide-react";
import { getClickUrl, getExportJsonUrl } from "@/lib/api";

interface ExportPanelProps {
  projectId: string;
}

const EXPORTS = [
  { label: "Click track WAV", type: "click" },
  { label: "Section guide PDF", type: "pdf" },
  { label: "JSON analysis", type: "json" },
  { label: "MIDI map", type: "midi" },
];

export function ExportPanel({ projectId }: ExportPanelProps) {
  function getUrl(type: string): string | null {
    switch (type) {
      case "click":
        return getClickUrl(projectId);
      case "json":
        return getExportJsonUrl(projectId);
      default:
        return null;
    }
  }

  return (
    <div className="space-y-1.5">
      {EXPORTS.map(({ label, type }) => {
        const url = getUrl(type);
        const isAvailable = !!url;

        return isAvailable ? (
          <a key={type} href={url} download className="daw-export-item">
            {label}
            <Download className="h-3.5 w-3.5 text-[#5c5c66]" />
          </a>
        ) : (
          <div key={type} className="daw-export-item opacity-40">
            {label}
            <span className="text-[10px] uppercase tracking-wider text-[#5c5c66]">
              Soon
            </span>
          </div>
        );
      })}
    </div>
  );
}
