"use client";

import React, { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Upload,
  Music,
  ChevronRight,
  Headphones,
  Layers,
  Activity,
  MousePointerClick,
  FolderOpen,
} from "lucide-react";
import { createProject, triggerAnalysis } from "@/lib/api";

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
    <div className="flex min-h-screen flex-col bg-[#111114]">
      {/* ─── Top Bar ────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#111114]/90 glass">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-3 tablet:px-8">
          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-muted">
              <Headphones className="h-5 w-5 text-accent" />
            </div>
            <span className="text-lg font-semibold tracking-tight">
              SessionGrid
            </span>
          </div>
          <a
            href="/projects"
            className="btn-ghost text-sm"
          >
            <FolderOpen className="h-4 w-4" />
            My Projects
            <ChevronRight className="h-3.5 w-3.5 text-text-muted" />
          </a>
        </div>
      </header>

      {/* ─── Hero ───────────────────────────────────────────────── */}
      <main className="flex flex-1 flex-col items-center px-5 pb-10 pt-10 tablet:px-8 tablet:pt-16">
        <div className="w-full max-w-2xl text-center">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-muted px-3 py-1 text-xs font-medium text-accent-hover">
            <Activity className="h-3 w-3" /> Rehearsal Translator
          </span>
          <h1 className="mt-4 text-3xl font-bold tracking-tight tablet:text-4xl">
            Turn demos into
            <br />
            <span className="text-gradient">arrangement maps</span>
          </h1>
          <p className="mx-auto mt-3 max-w-md text-base text-text-secondary tablet:text-lg">
            Upload a song, isolate the drums, analyze tempo and structure, and
            get a rehearsal-ready guide.
          </p>
        </div>

        {/* ─── Upload Card ──────────────────────────────────────── */}
        <div className="mt-10 w-full max-w-2xl animate-fade-up">
          <div className="card p-5 tablet:p-6">
            {/* Drop Zone */}
            <div
              className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 transition-all tablet:p-14 ${
                dragging
                  ? "border-accent bg-accent-muted"
                  : selectedFile
                  ? "border-emerald-500/30 bg-emerald-500/[0.06]"
                  : "border-white/10 bg-surface hover:border-white/20"
              }`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
            >
              {selectedFile ? (
                <>
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10">
                    <Music className="h-7 w-7 text-emerald-400" />
                  </div>
                  <p className="mt-3 font-medium">{selectedFile.name}</p>
                  <p className="mt-1 text-sm text-text-secondary">
                    {(selectedFile.size / 1024 / 1024).toFixed(1)} MB
                  </p>
                  <button
                    onClick={() => {
                      setSelectedFile(null);
                      setProjectName("");
                    }}
                    className="btn-ghost mt-3 text-sm text-text-muted"
                  >
                    Remove
                  </button>
                </>
              ) : (
                <>
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-raised">
                    <Upload className="h-7 w-7 text-text-muted" />
                  </div>
                  <p className="mt-3 font-medium text-text-primary">
                    Drop audio or video here
                  </p>
                  <p className="mt-1 text-sm text-text-muted">
                    MP3, WAV, FLAC, MP4, MOV — up to 200 MB
                  </p>
                  <label className="btn-secondary mt-5 cursor-pointer">
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

            {/* ── Project Name + Submit ───────────────────────── */}
            {selectedFile && (
              <div className="mt-5 animate-fade-up space-y-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
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

                {/* Rights Confirmation */}
                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/[0.06] bg-surface p-4 transition-colors active:bg-surface-raised">
                  <input
                    type="checkbox"
                    checked={rightsConfirmed}
                    onChange={(e) => setRightsConfirmed(e.target.checked)}
                    className="mt-0.5 h-5 w-5 rounded border-white/20 bg-surface-raised accent-accent"
                  />
                  <div className="text-sm">
                    <p className="font-medium text-text-primary">
                      I have rights to this audio
                    </p>
                    <p className="mt-0.5 text-text-muted">
                      This is my own music, a demo I&apos;ve been given
                      permission to use, or material I have license to analyze.
                    </p>
                  </div>
                </label>

                {/* Error */}
                {error && (
                  <div className="rounded-xl border border-rose-500/25 bg-rose-500/10 p-3 text-sm text-rose-300">
                    {error}
                  </div>
                )}

                {/* Submit */}
                <button
                  onClick={handleSubmit}
                  disabled={!rightsConfirmed || !projectName || uploading}
                  className="btn-primary w-full py-3.5 text-base"
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
          </div>
        </div>

        {/* ─── Features ─────────────────────────────────────────── */}
        <div className="mt-10 w-full max-w-2xl">
          <div className="grid gap-3 tablet:grid-cols-3">
            {[
              {
                icon: Layers,
                title: "Stem Isolation",
                desc: "AI-powered drum separation using Demucs v4",
              },
              {
                icon: Activity,
                title: "Beat Analysis",
                desc: "Tempo, meter, and section detection with confidence scoring",
              },
              {
                icon: Headphones,
                title: "Click Track",
                desc: "Auto-generated click aligned to the real beat grid",
              },
            ].map((feature) => (
              <div
                key={feature.title}
                className="card flex items-start gap-3 p-4"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-muted">
                  <feature.icon className="h-4 w-4 text-accent" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">{feature.title}</h3>
                  <p className="mt-0.5 text-sm text-text-muted">{feature.desc}</p>
                </div>
              </div>
            ))}
          </div>

          {/* ── How It Works ──────────────────────────────────── */}
          <div className="mt-6 card p-5 tablet:p-6">
            <h3 className="text-center text-xs font-semibold uppercase tracking-[0.2em] text-text-muted">
              How it works
            </h3>
            <div className="mt-5 grid grid-cols-2 gap-5 tablet:grid-cols-4">
              {[
                { step: "1", title: "Upload", desc: "Drop any audio or video file" },
                { step: "2", title: "Analyze", desc: "Stems separated, beats mapped" },
                { step: "3", title: "Explore", desc: "Browse sections, loop parts" },
                { step: "4", title: "Rehearse", desc: "Slow down, count in, nail it" },
              ].map((item) => (
                <div key={item.step} className="text-center">
                  <div className="mx-auto flex h-9 w-9 items-center justify-center rounded-full bg-accent-muted text-sm font-bold text-accent">
                    {item.step}
                  </div>
                  <p className="mt-2 text-sm font-medium">{item.title}</p>
                  <p className="mt-0.5 text-xs text-text-muted">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
