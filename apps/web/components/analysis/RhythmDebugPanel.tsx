// DEBUG ONLY — Rhythm Engine Debug Panel
// This component is strictly for engine verification.
// Remove when no longer needed.

"use client";

import { useEffect, useState } from "react";
import { getRhythmDebug, type RhythmDebugData } from "@/lib/api";

// DEBUG ONLY
interface RhythmDebugPanelProps {
  projectId: string;
}

// DEBUG ONLY
export function RhythmDebugPanel({ projectId }: RhythmDebugPanelProps) {
  const [data, setData] = useState<RhythmDebugData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(true);
  const [loading, setLoading] = useState(false);

  // DEBUG ONLY — fetch rhythm debug data on expand
  useEffect(() => {
    if (collapsed) return;
    if (data) return; // already loaded

    setLoading(true);
    getRhythmDebug(projectId)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => {
        setError(e.message || "Failed to load rhythm debug data");
      })
      .finally(() => setLoading(false));
  }, [collapsed, projectId, data]);

  // DEBUG ONLY
  return (
    <div
      style={{
        margin: "8px",
        border: "1px solid rgba(255,255,255,0.1)",
        borderRadius: "8px",
        background: "rgba(255,255,255,0.03)",
        fontSize: "12px",
      }}
    >
      {/* Header / Toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        style={{
          width: "100%",
          padding: "10px 12px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "none",
          border: "none",
          color: "#e5e5ea",
          cursor: "pointer",
          fontFamily: "inherit",
          fontSize: "13px",
          fontWeight: 600,
        }}
      >
        <span>🧠 Rhythm Engine Debug</span>
        <span style={{ opacity: 0.5 }}>{collapsed ? "▶" : "▼"}</span>
      </button>

      {/* DEBUG ONLY — Collapsible content */}
      {!collapsed && (
        <div style={{ padding: "0 12px 12px" }}>
          {loading && (
            <p style={{ color: "#8e8e93" }}>Loading…</p>
          )}

          {error && (
            <p style={{ color: "#f87171" }}>{error}</p>
          )}

          {data && (
            <>
              {/* Summary stats */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "6px 16px",
                  marginBottom: "10px",
                }}
              >
                <div>
                  <span style={{ color: "#8e8e93" }}>Dominant Meters: </span>
                  <span style={{ color: "#22d3ee" }}>
                    {data.unique_meters.length > 0
                      ? data.unique_meters.join(", ")
                      : "—"}
                  </span>
                </div>
                <div>
                  <span style={{ color: "#8e8e93" }}>Confidence Range: </span>
                  <span style={{ color: "#a78bfa" }}>
                    {data.confidence_min != null && data.confidence_max != null
                      ? `${data.confidence_min.toFixed(2)} – ${data.confidence_max.toFixed(2)}`
                      : "—"}
                  </span>
                </div>
                <div>
                  <span style={{ color: "#8e8e93" }}>Modulations Detected: </span>
                  <span style={{ color: "#fbbf24" }}>{data.modulation_count}</span>
                </div>
                <div>
                  <span style={{ color: "#8e8e93" }}>Polyrhythm Layers: </span>
                  <span style={{ color: "#fbbf24" }}>{data.polyrhythm_count}</span>
                </div>
                <div>
                  <span style={{ color: "#8e8e93" }}>Ambiguous Windows: </span>
                  <span style={{ color: "#fb923c" }}>{data.ambiguous_window_count}</span>
                </div>
                <div>
                  <span style={{ color: "#8e8e93" }}>Total Windows: </span>
                  <span>{data.total_windows}</span>
                </div>
              </div>

              {/* Sample windows (first 10) */}
              {data.sample_windows.length > 0 && (
                <>
                  <p
                    style={{
                      color: "#8e8e93",
                      marginBottom: "4px",
                      fontWeight: 600,
                    }}
                  >
                    First {data.sample_windows.length} Window Hypotheses:
                  </p>
                  <div
                    style={{
                      maxHeight: "180px",
                      overflow: "auto",
                      background: "rgba(0,0,0,0.3)",
                      borderRadius: "6px",
                      padding: "8px",
                      fontFamily: "monospace",
                      fontSize: "11px",
                      lineHeight: "1.5",
                      color: "#d4d4d8",
                    }}
                  >
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                      {JSON.stringify(data.sample_windows, null, 2)}
                    </pre>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
