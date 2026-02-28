"use client";

import type { ConfidenceLevel } from "@/lib/types";

interface ConfidenceBadgeProps {
  level: ConfidenceLevel | string | null | undefined;
  inline?: boolean;
}

const STYLES: Record<string, string> = {
  high: "confidence-high",
  medium: "confidence-medium",
  low: "confidence-low",
};

const INLINE_STYLES: Record<string, string> = {
  high: "font-medium text-emerald-300",
  medium: "font-medium text-amber-300",
  low: "font-medium text-rose-300",
};

export function ConfidenceBadge({ level, inline }: ConfidenceBadgeProps) {
  const normalized = level?.toLowerCase() || "low";
  const label = normalized.charAt(0).toUpperCase() + normalized.slice(1);

  if (inline) {
    return (
      <span className={INLINE_STYLES[normalized] || INLINE_STYLES.low}>
        {label}
      </span>
    );
  }

  return (
    <span className={STYLES[normalized] || STYLES.low}>
      {label}
    </span>
  );
}
