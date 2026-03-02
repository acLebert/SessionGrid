"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Headphones,
  Plus,
  Trash2,
  Clock,
  Music,
  ChevronRight,
} from "lucide-react";
import { listProjects, deleteProject } from "@/lib/api";
import type { ProjectListItem, ProjectStatus } from "@/lib/types";
import { PROCESSING_STEPS } from "@/lib/types";

const STATUS_DOT: Record<string, string> = {
  complete: "bg-emerald-400",
  failed: "bg-rose-400",
  uploading: "bg-accent animate-pulse",
  extracting: "bg-accent animate-pulse",
  separating: "bg-accent animate-pulse",
  analyzing: "bg-accent animate-pulse",
  generating_click: "bg-accent animate-pulse",
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
    <div className="flex min-h-screen flex-col bg-[#111114]">
      {/* ─── Top Bar ────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#111114]/90 glass">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-3 tablet:px-8">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-muted">
              <Headphones className="h-5 w-5 text-accent" />
            </div>
            <span className="text-lg font-semibold tracking-tight">
              SessionGrid
            </span>
          </Link>
          <Link href="/" className="btn-primary">
            <Plus className="h-4 w-4" /> New Project
          </Link>
        </div>
      </header>

      {/* ─── Content ────────────────────────────────────────────── */}
      <main className="flex-1 px-5 pb-10 pt-6 tablet:px-8">
        <div className="mx-auto max-w-5xl">
          <h1 className="text-2xl font-bold">My Projects</h1>
          <p className="mt-1 text-sm text-text-secondary">
            All your uploaded songs and analysis results.
          </p>

          {loading ? (
            <div className="mt-16 flex justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
          ) : projects.length === 0 ? (
            <div className="mt-16 flex flex-col items-center text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-surface-raised">
                <Music className="h-8 w-8 text-text-muted" />
              </div>
              <p className="mt-4 font-medium text-text-secondary">
                No projects yet
              </p>
              <p className="mt-1 text-sm text-text-muted">
                Upload your first track to get started
              </p>
              <Link href="/" className="btn-primary mt-5">
                <Plus className="h-4 w-4" /> Upload Track
              </Link>
            </div>
          ) : (
            <div className="mt-5 grid gap-3 tablet:grid-cols-2">
              {projects.map((project) => (
                <Link
                  key={project.id}
                  href={`/projects/${project.id}`}
                  className="card-interactive group flex items-center gap-4 p-4"
                >
                  {/* Icon */}
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-surface">
                    <Music className="h-5 w-5 text-text-muted" />
                  </div>

                  {/* Info */}
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{project.name}</p>
                    <div className="mt-1 flex items-center gap-3 text-sm text-text-muted">
                      <span className="flex items-center gap-1.5">
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
                            STATUS_DOT[project.status] || "bg-text-muted"
                          }`}
                        />
                        {PROCESSING_STEPS[project.status as ProjectStatus]?.label ||
                          project.status}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatDuration(project.duration_seconds)}
                      </span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        handleDelete(project.id);
                      }}
                      className="btn-icon opacity-0 transition-opacity group-hover:opacity-100 tablet:opacity-100"
                      aria-label="Delete project"
                    >
                      <Trash2 className="h-4 w-4 text-text-muted" />
                    </button>
                    <ChevronRight className="h-4 w-4 text-text-muted" />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
