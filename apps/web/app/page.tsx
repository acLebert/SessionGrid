"use client";

import React, { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Upload,
  Music,
  ChevronRight,
  Headphones,
  MousePointerClick,
  FolderOpen,
} from "lucide-react";
import { createProject, triggerAnalysis } from "@/lib/api";
import RhythmPreviewHero from "@/components/analysis/RhythmPreviewHero";

const ALLOWED = new Set([
  ".mp3", ".wav", ".flac", ".ogg", ".mp4", ".mov", ".webm", ".m4a", ".aac",
]);

export default function HomePage() {
  const router = useRouter();
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [projectName, setProjectName] = useState("");
  const [rightsConfirmed, setRightsConfirmed] = useState(false);

  const handleFile = useCallback((file: File) => {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ALLOWED.has(ext)) {
      setError(`Unsupported file type: ${ext}`);
      return;
    }
    setSelectedFile(file);
    setProjectName(file.name.replace(/\.[^.]+$/, ""));
    setError(null);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleSubmit = async () => {
    if (!selectedFile || !projectName || !rightsConfirmed) return;

    setUploading(true);
    setError(null);

    try {
      const project = await createProject(projectName, selectedFile, rightsConfirmed);
      await triggerAnalysis(project.id);
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setUploading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-[#0a0a0c]">
      {/* ─── Top Bar ────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#0a0a0c]/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3 tablet:px-8">
          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-muted">
              <Headphones className="h-5 w-5 text-accent" />
            </div>
            <span className="text-lg font-semibold tracking-tight">
              SessionGrid
            </span>
          </div>
          <a href="/projects" className="btn-ghost text-sm">
            <FolderOpen className="h-4 w-4" />
            My Projects
            <ChevronRight className="h-3.5 w-3.5 text-text-muted" />
          </a>
        </div>
      </header>

      <main className="flex flex-1 flex-col">
        {/* ─── Hero ─────────────────────────────────────────────── */}
        <section className="relative overflow-hidden">
          {/* Animated grid background with opacity pulse */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              backgroundImage:
                "linear-gradient(rgba(34,211,238,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.025) 1px, transparent 1px)",
              backgroundSize: "60px 60px",
              animation: "gridPulse 8s ease-in-out infinite",
            }}
          />
          {/* Subtle horizontal scanline */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              backgroundImage:
                "repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(34,211,238,0.008) 3px, rgba(34,211,238,0.008) 4px)",
              animation: "scanDrift 12s linear infinite",
            }}
          />
          {/* Bottom fade */}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[#0a0a0c]" />
          {/* Radial vignette */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(ellipse 70% 60% at 50% 40%, transparent 40%, #0a0a0c 100%)",
            }}
          />

          <div className="relative mx-auto flex max-w-6xl flex-col items-center gap-10 px-5 pb-20 pt-16 tablet:flex-row tablet:gap-16 tablet:px-8 tablet:pt-24 tablet:pb-28">
            {/* Left — Copy */}
            <div className="flex-1 text-center tablet:text-left">
              <h1 className="text-[2rem] font-bold leading-[1.1] tracking-[-0.02em] tablet:text-[2.75rem]">
                <span className="text-[#c8c8cc]">See the structure</span>
                <br />
                <span className="bg-gradient-to-r from-cyan-400 to-teal-300 bg-clip-text text-transparent">
                  inside rhythm.
                </span>
              </h1>
              <p className="mt-5 max-w-md text-base leading-[1.7] tracking-wide text-[#7a7a82] tablet:text-lg">
                Upload a track. Watch meter, subdivisions, and phase layers unfold.
              </p>
              <div className="mt-8 flex flex-col gap-3 tablet:flex-row">
                <a href="#analyze" className="btn-primary px-6 py-3 text-base">
                  Analyze a Track
                  <ChevronRight className="h-4 w-4" />
                </a>
                <a href="/projects" className="btn-secondary px-6 py-3 text-base">
                  Explore Demo
                </a>
              </div>
            </div>

            {/* Right — Rhythm visualization */}
            <div className="flex flex-1 items-center justify-center">
              <RhythmPreviewHero />
            </div>
          </div>

          {/* Inline keyframes */}
          <style jsx>{`
            @keyframes gridPulse {
              0%, 100% { opacity: 1; }
              50% { opacity: 0.4; }
            }
            @keyframes scanDrift {
              0% { background-position: 0 0; }
              100% { background-position: 0 200px; }
            }
          `}</style>
        </section>

        {/* ─── Feature Cards ────────────────────────────────────── */}
        <section className="mx-auto w-full max-w-6xl px-5 tablet:px-8">
          <div className="grid gap-4 tablet:grid-cols-3">
            {[
              {
                title: "Meter Intelligence",
                desc: "Persistent detection of time signatures and structural meter shifts.",
                border: "from-cyan-500/25 via-cyan-500/8 to-transparent",
              },
              {
                title: "Subdivision Graph",
                desc: "Detect simultaneous rhythmic grids and nested patterns.",
                border: "from-teal-500/25 via-teal-500/8 to-transparent",
              },
              {
                title: "Phase & Polymeter",
                desc: "Track layer relationships and phase offsets across time.",
                border: "from-sky-500/25 via-sky-500/8 to-transparent",
              },
            ].map((card) => (
              <div
                key={card.title}
                className="group relative rounded-2xl p-px transition-all duration-300 hover:-translate-y-[3px]"
              >
                {/* Gradient border shell */}
                <div
                  className={`pointer-events-none absolute inset-0 rounded-2xl bg-gradient-to-b ${card.border} opacity-60 transition-opacity duration-300 group-hover:opacity-100`}
                />
                {/* Inner panel */}
                <div
                  className="relative rounded-2xl bg-[#0d0d10] p-6 transition-colors duration-300 group-hover:bg-[#0f0f13]"
                  style={{
                    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03), inset 0 -1px 0 rgba(0,0,0,0.4)",
                  }}
                >
                  <h3 className="text-[13px] font-semibold tracking-wide text-text-primary">
                    {card.title}
                  </h3>
                  <p className="mt-2 text-[13px] leading-relaxed text-[#55555e]">
                    {card.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ─── Statement ────────────────────────────────────────── */}
        <section className="mx-auto max-w-2xl px-5 py-20 text-center tablet:px-8 tablet:py-28">
          <h2 className="text-xl font-semibold tracking-[-0.01em] text-[#d0d0d4] tablet:text-2xl">
            Built for musicians who think in structure.
          </h2>
          <p className="mt-4 text-base leading-[1.7] tracking-wide text-[#62626a]">
            SessionGrid maps the invisible architecture of rhythm — so you can
            rehearse, compose, and explore with clarity.
          </p>
        </section>

        {/* ─── Upload CTA ───────────────────────────────────────── */}
        <section
          id="analyze"
          className="mx-auto w-full max-w-xl px-5 pb-24 tablet:px-8"
        >
          <h3 className="mb-6 text-center text-lg font-semibold tracking-tight">
            Ready to analyze a track?
          </h3>

          {/* Drop zone */}
          <div
            className={`relative flex flex-col items-center justify-center rounded-2xl border transition-all duration-300 ${
              dragging
                ? "border-accent bg-accent-muted"
                : selectedFile
                ? "border-emerald-500/30 bg-emerald-500/[0.04]"
                : "border-white/[0.06] bg-[#0d0d10] hover:border-white/[0.12] hover:shadow-[0_0_24px_-6px_rgba(34,211,238,0.06)]"
            } px-6 py-10`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
          >
            {selectedFile ? (
              <>
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/10">
                  <Music className="h-6 w-6 text-emerald-400" />
                </div>
                <p className="mt-3 text-sm font-medium">{selectedFile.name}</p>
                <p className="mt-1 text-xs text-text-muted">
                  {(selectedFile.size / 1024 / 1024).toFixed(1)} MB
                </p>
                <button
                  onClick={() => {
                    setSelectedFile(null);
                    setProjectName("");
                  }}
                  className="mt-2 text-xs text-text-muted underline underline-offset-2 hover:text-text-secondary"
                >
                  Remove
                </button>
              </>
            ) : (
              <>
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-surface-raised">
                  <Upload className="h-6 w-6 text-text-muted" />
                </div>
                <p className="mt-3 text-sm font-medium text-text-primary">
                  Drop audio or video here
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  MP3, WAV, FLAC, MP4, MOV — up to 200 MB
                </p>
                <label className="btn-secondary mt-4 cursor-pointer text-sm">
                  <MousePointerClick className="h-4 w-4" />
                  Browse Files
                  <input
                    type="file"
                    className="hidden"
                    accept=".mp3,.wav,.flac,.ogg,.mp4,.mov,.webm,.m4a,.aac"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleFile(file);
                    }}
                  />
                </label>
              </>
            )}
          </div>

          {/* Project name + submit */}
          {selectedFile && (
            <div className="mt-4 animate-fade-up space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-text-secondary">
                  Project name
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  className="input"
                  placeholder="My Demo"
                />
              </div>

              <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/[0.05] bg-[#0d0d10] p-3.5 transition-colors active:bg-surface-raised">
                <input
                  type="checkbox"
                  checked={rightsConfirmed}
                  onChange={(e) => setRightsConfirmed(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-white/20 bg-surface-raised accent-accent"
                />
                <div className="text-xs">
                  <p className="font-medium text-text-primary">
                    I have rights to this audio
                  </p>
                  <p className="mt-0.5 text-text-muted">
                    This is my own music, a demo I&apos;ve been given permission
                    to use, or material I have license to analyze.
                  </p>
                </div>
              </label>

              {error && (
                <div className="rounded-xl border border-rose-500/25 bg-rose-500/10 p-3 text-sm text-rose-300">
                  {error}
                </div>
              )}

              <button
                onClick={handleSubmit}
                disabled={!rightsConfirmed || !projectName || uploading}
                className="btn-primary w-full py-3 text-sm"
              >
                {uploading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Uploading & analyzing...
                  </span>
                ) : (
                  "Upload & Analyze"
                )}
              </button>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
