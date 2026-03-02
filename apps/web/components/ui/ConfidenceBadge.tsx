"use client";

import type { ConfidenceLevel } from "@/lib/types";

interface ConfidenceBadgeProps {
  level: ConfidenceLevel | string | null | undefined;
  inline?: boolean;
}

const BADGE_STYLES: Record<string, string> = {
  high: "confidence-high",
  medium: "confidence-medium",
  low: "confidence-low",
};

const INLINE_STYLES: Record<string, string> = {
  high: "font-medium text-emerald-400",
  medium: "font-medium text-amber-400",
  low: "font-medium text-rose-400",
};

const DOT_STYLES: Record<string, string> = {
  high: "bg-emerald-400",
  medium: "bg-amber-400",
  low: "bg-rose-400",
};

export function ConfidenceBadge({ level, inline }: ConfidenceBadgeProps) {
  const normalized = level?.toLowerCase() || "low";
  const label = normalized.charAt(0).toUpperCase() + normalized.slice(1);

  if (inline) {
    return (
      <span className={`flex items-center gap-1.5 text-sm ${INLINE_STYLES[normalized] || INLINE_STYLES.low}`}>
        <span className={`h-1.5 w-1.5 rounded-full ${DOT_STYLES[normalized] || DOT_STYLES.low}`} />
        {label}
      </span>
    );
  }

  return (
    <span className={BADGE_STYLES[normalized] || BADGE_STYLES.low}>
      {label}
    </span>
  );
}
