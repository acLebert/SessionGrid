"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Headphones, Plus, Trash2, Clock, Music } from "lucide-react";
import { listProjects, deleteProject } from "@/lib/api";
import type { ProjectListItem, ProjectStatus } from "@/lib/types";
import { PROCESSING_STEPS } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  complete: "text-emerald-400",
  failed: "text-rose-400",
  uploading: "text-cyan-400",
  extracting: "text-cyan-400",
  separating: "text-cyan-400",
  analyzing: "text-cyan-400",
  generating_click: "text-cyan-400",
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProjects();
  }, []);

  async function loadProjects() {
    try {
      const data = await listProjects();
      setProjects(data);
    } catch (err) {
      console.error("Failed to load projects:", err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this project and all its files?")) return;
    try {
      await deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      console.error("Delete failed:", err);
    }
  }

  function formatDuration(seconds: number | null): string {
    if (!seconds) return "--:--";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      <header className="border-b border-white/5">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-400/15">
              <Headphones className="h-5 w-5 text-cyan-400" />
            </div>
            <span className="text-lg font-semibold tracking-tight">
              SessionGrid
            </span>
          </Link>
          <Link href="/" className="btn-primary flex items-center gap-2">
            <Plus className="h-4 w-4" /> New Project
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-10">
        <h1 className="text-2xl font-bold">My Projects</h1>

        {loading ? (
          <div className="mt-12 flex justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
          </div>
        ) : projects.length === 0 ? (
          <div className="mt-12 text-center">
            <Music className="mx-auto h-12 w-12 text-zinc-700" />
            <p className="mt-3 text-zinc-500">No projects yet</p>
            <Link href="/" className="btn-primary mt-4 inline-block">
              Upload your first track
            </Link>
          </div>
        ) : (
          <div className="mt-6 space-y-3">
            {projects.map((project) => (
              <Link
                key={project.id}
                href={`/projects/${project.id}`}
                className="group flex items-center justify-between rounded-2xl border border-white/5 bg-white/[0.02] p-4 transition-colors hover:border-white/10 hover:bg-white/[0.04]"
              >
                <div className="flex items-center gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-zinc-900">
                    <Music className="h-5 w-5 text-zinc-500" />
                  </div>
                  <div>
                    <p className="font-medium">{project.name}</p>
                    <p className="text-sm text-zinc-500">
                      {project.original_filename}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-6">
                  <div className="text-right text-sm">
                    <p className={STATUS_COLORS[project.status] || "text-zinc-400"}>
                      {PROCESSING_STEPS[project.status as ProjectStatus]?.label || project.status}
                    </p>
                    <p className="flex items-center gap-1 text-zinc-600">
                      <Clock className="h-3 w-3" />
                      {formatDuration(project.duration_seconds)}
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      handleDelete(project.id);
                    }}
                    className="rounded-lg p-2 text-zinc-600 opacity-0 transition-all hover:bg-zinc-800 hover:text-rose-400 group-hover:opacity-100"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
