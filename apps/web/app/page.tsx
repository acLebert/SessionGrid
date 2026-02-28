"use client";

import React, { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Upload, Music, ChevronRight, Headphones } from "lucide-react";
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
    <div className="min-h-screen bg-zinc-950">
      {/* Header */}
      <header className="border-b border-white/5">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-400/15">
              <Headphones className="h-5 w-5 text-cyan-400" />
            </div>
            <span className="text-lg font-semibold tracking-tight">SessionGrid</span>
          </div>
          <a
            href="/projects"
            className="text-sm text-zinc-400 transition-colors hover:text-zinc-200"
          >
            My Projects <ChevronRight className="ml-1 inline h-3 w-3" />
          </a>
        </div>
      </header>

      {/* Hero */}
      <main className="mx-auto max-w-5xl px-6 py-16">
        <div className="text-center">
          <p className="text-sm uppercase tracking-[0.3em] text-cyan-400">
            Rehearsal Translator
          </p>
          <h1 className="mt-3 text-4xl font-bold tracking-tight md:text-5xl">
            Turn demos into
            <br />
            <span className="bg-gradient-to-r from-cyan-400 to-teal-400 bg-clip-text text-transparent">
              arrangement maps
            </span>
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-zinc-400">
            Upload a song, isolate the drums, analyze tempo and structure, and
            get a rehearsal-ready guide with click track support.
          </p>
        </div>

        {/* Upload Card */}
        <div className="mx-auto mt-12 max-w-2xl">
          <div className="glass-panel p-6">
            {/* Drop Zone */}
            <div
              className={`relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-12 transition-colors ${
                dragging
                  ? "border-cyan-400 bg-cyan-400/5"
                  : selectedFile
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : "border-white/15 bg-zinc-900/50 hover:border-white/25"
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
                  <Music className="h-10 w-10 text-emerald-400" />
                  <p className="mt-3 font-medium">{selectedFile.name}</p>
                  <p className="mt-1 text-sm text-zinc-400">
                    {(selectedFile.size / 1024 / 1024).toFixed(1)} MB
                  </p>
                  <button
                    onClick={() => {
                      setSelectedFile(null);
                      setProjectName("");
                    }}
                    className="mt-3 text-sm text-zinc-500 hover:text-zinc-300"
                  >
                    Remove
                  </button>
                </>
              ) : (
                <>
                  <Upload className="h-10 w-10 text-zinc-500" />
                  <p className="mt-3 text-zinc-300">
                    Drop your audio or video file here
                  </p>
                  <p className="mt-1 text-sm text-zinc-500">
                    MP3, WAV, FLAC, MP4, MOV — up to 200 MB
                  </p>
                  <label className="btn-secondary mt-4 cursor-pointer">
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

            {/* Project Name */}
            {selectedFile && (
              <div className="mt-5 animate-fade-in space-y-4">
                <div>
                  <label className="mb-1.5 block text-sm text-zinc-400">
                    Project name
                  </label>
                  <input
                    type="text"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-zinc-900 px-4 py-2.5 text-sm text-zinc-100 outline-none transition-colors focus:border-cyan-400/50"
                    placeholder="My Demo"
                  />
                </div>

                {/* Rights Confirmation */}
                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 bg-zinc-900/70 p-4">
                  <input
                    type="checkbox"
                    checked={rightsConfirmed}
                    onChange={(e) => setRightsConfirmed(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-white/20 bg-zinc-800 accent-cyan-400"
                  />
                  <div className="text-sm">
                    <p className="font-medium text-zinc-200">
                      I have rights to this audio
                    </p>
                    <p className="mt-0.5 text-zinc-500">
                      This is my own music, a demo I&apos;ve been given
                      permission to use, or material I have license to analyze.
                    </p>
                  </div>
                </label>

                {/* Error */}
                {error && (
                  <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">
                    {error}
                  </div>
                )}

                {/* Submit */}
                <button
                  onClick={handleSubmit}
                  disabled={!rightsConfirmed || !projectName || uploading}
                  className="btn-primary w-full py-3 text-base disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {uploading ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-950 border-t-transparent" />
                      Uploading & starting analysis...
                    </span>
                  ) : (
                    "Upload & Analyze"
                  )}
                </button>
              </div>
            )}
          </div>

          {/* Features */}
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {[
              {
                title: "Stem Isolation",
                desc: "AI-powered drum separation using Demucs v4",
              },
              {
                title: "Beat Analysis",
                desc: "Tempo, meter, and section detection with confidence scoring",
              },
              {
                title: "Click Track",
                desc: "Auto-generated click aligned to the real beat grid",
              },
            ].map((feature) => (
              <div
                key={feature.title}
                className="rounded-2xl border border-white/5 bg-white/[0.02] p-5"
              >
                <h3 className="text-sm font-semibold">{feature.title}</h3>
                <p className="mt-1 text-sm text-zinc-500">{feature.desc}</p>
              </div>
            ))}
          </div>

          {/* How It Works */}
          <div className="mt-10 rounded-2xl border border-white/5 bg-white/[0.02] p-6">
            <h3 className="text-center text-sm font-semibold uppercase tracking-widest text-zinc-400">
              How it works
            </h3>
            <div className="mt-5 grid gap-6 md:grid-cols-4">
              {[
                { step: "1", title: "Upload", desc: "Drop any audio or video file — MP3, WAV, FLAC, MP4, etc." },
                { step: "2", title: "Analyze", desc: "SessionGrid extracts audio, separates stems, and maps the arrangement." },
                { step: "3", title: "Explore", desc: "Browse sections, loop parts, switch between mix/drums/click." },
                { step: "4", title: "Rehearse", desc: "Use the Practice Deck to slow down, count in, and nail the part." },
              ].map((item) => (
                <div key={item.step} className="text-center">
                  <div className="mx-auto flex h-8 w-8 items-center justify-center rounded-full bg-cyan-400/15 text-sm font-bold text-cyan-400">
                    {item.step}
                  </div>
                  <p className="mt-2 text-sm font-medium">{item.title}</p>
                  <p className="mt-1 text-xs text-zinc-500">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
