"use client";

import { useState } from "react";
import { getSubdivisionDebug } from "@/lib/api";

interface SubdivisionGraphPanelProps {
  projectId: string;
}

export default function SubdivisionGraphPanel({ projectId }: SubdivisionGraphPanelProps) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleToggle() {
    if (!open && !data) {
      try {
        setLoading(true);
        const res = await getSubdivisionDebug(projectId);
        setData(res);
      } catch (err) {
        setError("Failed to load subdivision graph");
      } finally {
        setLoading(false);
      }
    }
    setOpen(!open);
  }

  return (
    <div className="mt-4 border-t pt-4">
      <button
        onClick={handleToggle}
        className="text-sm font-semibold text-purple-400"
      >
        🔬 Subdivision Graph Debug
      </button>

      {open && (
        <div className="mt-3 text-xs bg-black p-3 rounded max-h-96 overflow-y-auto">
          {loading && <div>Loading...</div>}
          {error && <div className="text-red-400">{error}</div>}
          {data && (
            <pre className="whitespace-pre-wrap">
              {JSON.stringify(data, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
