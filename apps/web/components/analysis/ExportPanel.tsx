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
        return null; // PDF and MIDI coming in v0.2
    }
  }

  return (
    <div className="glass-panel p-5">
      <h2 className="text-lg font-semibold">Exports</h2>
      <div className="mt-4 grid gap-3 text-sm">
        {EXPORTS.map(({ label, type }) => {
          const url = getUrl(type);
          const isAvailable = !!url;

          return isAvailable ? (
            <a
              key={type}
              href={url}
              download
              className="flex items-center justify-between rounded-2xl border border-white/10 bg-zinc-900/70 px-4 py-3 text-zinc-200 transition-colors hover:bg-zinc-900"
            >
              {label}
              <Download className="h-4 w-4 text-zinc-500" />
            </a>
          ) : (
            <div
              key={type}
              className="flex items-center justify-between rounded-2xl border border-white/5 bg-zinc-900/40 px-4 py-3 text-zinc-500"
            >
              {label}
              <span className="text-xs">Coming soon</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
