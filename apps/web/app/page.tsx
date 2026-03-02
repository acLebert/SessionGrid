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
      <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#0a0a0c]/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-2.5 tablet:px-8">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-muted">
              <Headphones className="h-4 w-4 text-accent" />
            </div>
            <span className="text-[13px] font-semibold tracking-tight text-text-secondary">
              SessionGrid
            </span>
          </div>
          <a href="/projects" className="btn-ghost text-xs">
            <FolderOpen className="h-3.5 w-3.5" />
            Projects
            <ChevronRight className="h-3 w-3 text-text-muted" />
          </a>
        </div>
      </header>

      <main className="flex flex-1 flex-col">
        {/* ─── Hero ─────────────────────────────────────────────── */}
        <section className="relative overflow-hidden">
          {/* Measurement surface — vertical emphasis, faint axis grid */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              backgroundImage: [
                "linear-gradient(90deg, rgba(34,211,238,0.03) 1px, transparent 1px)",
                "linear-gradient(rgba(34,211,238,0.015) 1px, transparent 1px)",
              ].join(", "),
              backgroundSize: "60px 60px",
            }}
          />
          {/* Subtle tick marks at 12px sub-grid (very faint) */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              backgroundImage:
                "linear-gradient(90deg, rgba(34,211,238,0.012) 1px, transparent 1px)",
              backgroundSize: "12px 12px",
            }}
          />
          {/* Deep vignette */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(ellipse 65% 55% at 50% 45%, transparent 30%, #0a0a0c 100%)",
            }}
          />
          {/* Bottom fade */}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[#0a0a0c]" />

          <div className="relative mx-auto flex max-w-6xl flex-col items-center gap-6 px-5 pb-12 pt-10 tablet:flex-row tablet:gap-12 tablet:px-8 tablet:pt-16 tablet:pb-16">
            {/* Left — Copy */}
            <div className="flex-1 text-center tablet:text-left">
              <h1 className="text-[1.6rem] font-semibold leading-[1.05] tracking-[-0.03em] tablet:text-[2.2rem]">
                <span className="text-[#b0b0b4]">See the structure</span>
                <br />
                <span className="text-cyan-500/90">inside rhythm.</span>
              </h1>
              <p className="mt-3 max-w-sm text-[13px] font-light leading-[1.6] tracking-wide text-[#606068] tablet:text-sm">
                Upload a track. Watch meter, subdivisions, and phase layers unfold.
              </p>
              <div className="mt-5 flex flex-col gap-2.5 tablet:flex-row">
                <a href="#analyze" className="btn-primary px-5 py-2.5 text-[13px]">
                  Analyze a Track
                  <ChevronRight className="h-3.5 w-3.5" />
                </a>
                <a href="/projects" className="btn-secondary px-5 py-2.5 text-[13px]">
                  Explore Demo
                </a>
              </div>
            </div>

            {/* Right — Scope visualization */}
            <div className="flex flex-1 items-center justify-center">
              <RhythmPreviewHero />
            </div>
          </div>
        </section>

        {/* ─── Analysis Module Panels ───────────────────────────── */}
        <section className="mx-auto w-full max-w-5xl px-5 tablet:px-8">
          <div className="grid gap-px tablet:grid-cols-3">
            {[
              {
                title: "Meter Intelligence",
                desc: "Persistent detection of time signatures and structural meter shifts across sections.",
              },
              {
                title: "Subdivision Graph",
                desc: "Simultaneous rhythmic grids, nested patterns, and layer persistence scoring.",
              },
              {
                title: "Phase & Polymeter",
                desc: "Layer relationships, phase offsets, and stability tracking across time.",
              },
            ].map((mod) => (
              <div
                key={mod.title}
                className="group relative border border-white/[0.04] bg-[#08080a] transition-colors duration-300 hover:border-white/[0.09]"
              >
                {/* Top accent line */}
                <div className="absolute inset-x-0 top-0 h-px bg-cyan-500/20" />
                <div className="px-5 py-4">
                  <h3 className="text-[12px] font-semibold tracking-wide text-[#a0a0a6]">
                    {mod.title}
                  </h3>
                  <p className="mt-1.5 text-[11px] leading-[1.55] text-[#48484f]">
                    {mod.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ─── Statement (minimal) ──────────────────────────────── */}
        <div className="mx-auto max-w-xl px-5 py-10 text-center tablet:px-8 tablet:py-14">
          <p className="text-[11px] tracking-[0.08em] text-[#3e3e44]">
            Built for musicians who think in structure.
          </p>
        </div>

        {/* ─── Upload Console ───────────────────────────────────── */}
        <section
          id="analyze"
          className="mx-auto w-full max-w-lg px-5 pb-16 tablet:px-8"
        >
          {/* Drop zone — inset panel */}
          <div
            className={`relative flex flex-col items-center justify-center border transition-colors duration-200 ${
              dragging
                ? "border-cyan-500/30 bg-cyan-500/[0.03]"
                : selectedFile
                ? "border-emerald-500/20 bg-emerald-500/[0.02]"
                : "border-white/[0.05] bg-[#08080a] hover:border-white/[0.09]"
            } px-5 py-8`}
            style={{
              backgroundImage: dragging || selectedFile
                ? "none"
                : "linear-gradient(90deg, rgba(34,211,238,0.008) 1px, transparent 1px), linear-gradient(rgba(34,211,238,0.008) 1px, transparent 1px)",
              backgroundSize: "20px 20px",
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
          >
            {selectedFile ? (
              <>
                <div className="flex h-10 w-10 items-center justify-center bg-emerald-500/10">
                  <Music className="h-5 w-5 text-emerald-400/80" />
                </div>
                <p className="mt-2.5 text-[13px] font-medium text-text-primary">{selectedFile.name}</p>
                <p className="mt-0.5 text-[11px] text-text-muted">
                  {(selectedFile.size / 1024 / 1024).toFixed(1)} MB
                </p>
                <button
                  onClick={() => {
                    setSelectedFile(null);
                    setProjectName("");
                  }}
                  className="mt-1.5 text-[11px] text-text-muted underline underline-offset-2 hover:text-text-secondary"
                >
                  Remove
                </button>
              </>
            ) : (
              <>
                <div className="flex h-10 w-10 items-center justify-center bg-[#0e0e12]">
                  <Upload className="h-5 w-5 text-[#3e3e44]" />
                </div>
                <p className="mt-2.5 text-[13px] font-medium text-[#808088]">
                  Drop audio or video here
                </p>
                <p className="mt-0.5 text-[11px] text-[#3e3e44]">
                  MP3, WAV, FLAC, MP4, MOV — up to 200 MB
                </p>
                <label className="btn-secondary mt-3 cursor-pointer text-[12px]">
                  <MousePointerClick className="h-3.5 w-3.5" />
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
            <div className="mt-3 animate-fade-up space-y-2.5">
              <div>
                <label className="mb-0.5 block text-[11px] font-medium text-[#606068]">
                  Project name
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  className="input text-[13px]"
                  placeholder="My Demo"
                />
              </div>

              <label className="flex cursor-pointer items-start gap-2.5 border border-white/[0.04] bg-[#08080a] p-3 transition-colors active:bg-surface-raised">
                <input
                  type="checkbox"
                  checked={rightsConfirmed}
                  onChange={(e) => setRightsConfirmed(e.target.checked)}
                  className="mt-0.5 h-3.5 w-3.5 rounded border-white/20 bg-surface-raised accent-accent"
                />
                <div className="text-[11px]">
                  <p className="font-medium text-[#808088]">
                    I have rights to this audio
                  </p>
                  <p className="mt-0.5 text-[#3e3e44]">
                    Own music, permitted demo, or licensed material.
                  </p>
                </div>
              </label>

              {error && (
                <div className="border border-rose-500/20 bg-rose-500/[0.05] p-2.5 text-[12px] text-rose-300/80">
                  {error}
                </div>
              )}

              <button
                onClick={handleSubmit}
                disabled={!rightsConfirmed || !projectName || uploading}
                className="btn-primary w-full py-2.5 text-[13px]"
              >
                {uploading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Analyzing…
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
