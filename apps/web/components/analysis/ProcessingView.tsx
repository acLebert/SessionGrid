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

  const stages = [
    { label: "Extract", threshold: 15 },
    { label: "Separate", threshold: 40 },
    { label: "Analyze", threshold: 65 },
    { label: "Click", threshold: 85 },
    { label: "Done", threshold: 100 },
  ];

  return (
    <div className="card mx-auto max-w-lg p-8 text-center">
      <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-muted">
        <div className="h-8 w-8 animate-spin rounded-full border-[3px] border-accent/20 border-t-accent" />
      </div>

      <h2 className="text-xl font-semibold">{step.label}</h2>
      {message && (
        <p className="mt-2 text-sm text-text-secondary">{message}</p>
      )}

      {/* Progress bar */}
      <div className="mx-auto mt-6 max-w-sm">
        <div className="h-1.5 overflow-hidden rounded-full bg-surface">
          <div
            className="h-full rounded-full bg-gradient-to-r from-[#22d3ee] to-[#0891b2] transition-all duration-1000"
            style={{ width: `${step.progress}%` }}
          />
        </div>
        <div className="mt-3 flex justify-between text-2xs text-text-muted">
          {stages.map((s) => (
            <span
              key={s.label}
              className={step.progress >= s.threshold ? "text-accent" : ""}
            >
              {s.label}
            </span>
          ))}
        </div>
      </div>

      <p className="mt-6 text-sm text-text-muted">
        This typically takes 1–3 minutes depending on song length.
      </p>
    </div>
  );
}
