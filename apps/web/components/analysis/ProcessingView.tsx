"use client";

import type { ProjectStatus } from "@/lib/types";
import { PROCESSING_STEPS } from "@/lib/types";

interface ProcessingViewProps {
  status: ProjectStatus;
  message: string | null;
}

export function ProcessingView({ status, message }: ProcessingViewProps) {
  const step = PROCESSING_STEPS[status] || {
    label: "Processing...",
    progress: 50,
  };

  return (
    <div className="glass-panel mb-6 p-8 text-center">
      <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-[3px] border-cyan-400/20 border-t-cyan-400" />
      </div>

      <h2 className="text-xl font-semibold">{step.label}</h2>
      {message && (
        <p className="mt-2 text-sm text-zinc-400">{message}</p>
      )}

      {/* Progress bar */}
      <div className="mx-auto mt-6 max-w-md">
        <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-teal-400 transition-all duration-1000"
            style={{ width: `${step.progress}%` }}
          />
        </div>
        <div className="mt-2 flex justify-between text-xs text-zinc-600">
          <span>Extract</span>
          <span>Separate</span>
          <span>Analyze</span>
          <span>Click</span>
          <span>Done</span>
        </div>
      </div>

      <p className="mt-6 text-sm text-zinc-600">
        This typically takes 1–3 minutes depending on song length.
      </p>
    </div>
  );
}
