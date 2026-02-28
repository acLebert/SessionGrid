"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  RefreshCw,
} from "lucide-react";
import { getProject, getProjectStatus, triggerAnalysis } from "@/lib/api";
import type { Project, ProjectStatus, Section } from "@/lib/types";
import { PROCESSING_STEPS } from "@/lib/types";
import { AudioEngineProvider, useAudioEngine } from "@/components/player/AudioEngine";
import { ProjectSidebar } from "@/components/analysis/ProjectSidebar";
import { TimelinePanel } from "@/components/analysis/TimelinePanel";
import { PracticeDeck } from "@/components/analysis/PracticeDeck";
import { ArrangementMap } from "@/components/analysis/ArrangementMap";
import { ExportPanel } from "@/components/analysis/ExportPanel";
import { ProcessingView } from "@/components/analysis/ProcessingView";

/* ─── Renderless: syncs highlighted section with playback position ── */
function SectionSync({
  sections,
  activeSection,
  isLooping,
  onAutoSection,
}: {
  sections: Section[];
  activeSection: number;
  isLooping: boolean;
  onAutoSection: (idx: number) => void;
}) {
  const audio = useAudioEngine();
  const prevActiveRef = useRef(activeSection);

  // When a section is selected for looping, seek to its start
  useEffect(() => {
    if (
      isLooping &&
      activeSection >= 0 &&
      activeSection !== prevActiveRef.current
    ) {
      const section = sections[activeSection];
      if (section) audio.seek(section.start_time);
    }
    prevActiveRef.current = activeSection;
  }, [activeSection, isLooping, sections, audio]);

  // Auto-detect which section the playhead is in (free-play mode)
  const ct = audio.currentTime;
  useEffect(() => {
    if (isLooping) return;
    const idx = sections.findIndex(
      (s) => ct >= s.start_time && ct < s.end_time
    );
    if (idx >= 0 && idx !== activeSection) {
      onAutoSection(idx);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Math.floor(ct), isLooping]);

  return null;
}

export default function ProjectPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState<number>(-1);
  const [isLooping, setIsLooping] = useState(false);
  const [playbackMode, setPlaybackMode] = useState<string>("click_drums");

  const loadProject = useCallback(async () => {
    try {
      const data = await getProject(projectId);
      setProject(data);
      setLoading(false);
    } catch (err) {
      console.error("Failed to load project:", err);
      setLoading(false);
    }
  }, [projectId]);

  // Initial load
  useEffect(() => {
    loadProject();
  }, [loadProject]);

  // Poll for status while processing
  useEffect(() => {
    if (!project) return;
    const isProcessing = !["complete", "failed"].includes(project.status);
    if (!isProcessing) return;

    const interval = setInterval(async () => {
      try {
        const status = await getProjectStatus(projectId);
        if (status.status === "complete" || status.status === "failed") {
          await loadProject();
          clearInterval(interval);
        } else {
          setProject((prev) =>
            prev
              ? {
                  ...prev,
                  status: status.status as ProjectStatus,
                  status_message: status.status_message,
                }
              : prev
          );
        }
      } catch {
        clearInterval(interval);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [project?.status, projectId, loadProject]);

  /* Arrangement-map click: select & loop, or deselect */
  function handleArrangementSelect(idx: number) {
    if (idx < 0 || idx === activeSection) {
      setActiveSection(-1);
      setIsLooping(false);
    } else {
      setActiveSection(idx);
      setIsLooping(true);
    }
  }

  /* Waveform / auto-tracking: just highlight, don't loop */
  function handleWaveformSectionChange(idx: number) {
    if (idx >= 0) setActiveSection(idx);
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950">
        <p className="text-zinc-500">Project not found</p>
        <Link href="/" className="btn-primary mt-4">
          Go Home
        </Link>
      </div>
    );
  }

  const isProcessing = !["complete", "failed"].includes(project.status);
  const currentSection =
    activeSection >= 0 && activeSection < project.sections.length
      ? project.sections[activeSection]
      : null;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto max-w-7xl p-6 lg:p-8">
        {/* ─── Header ──────────────────────────────────────────────── */}
        <div className="mb-6 flex flex-col gap-4 rounded-3xl border border-white/10 bg-white/5 p-5 shadow-2xl backdrop-blur md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <Link
                href="/projects"
                className="rounded-lg p-1.5 text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-300"
              >
                <ArrowLeft className="h-4 w-4" />
              </Link>
              <p className="text-sm uppercase tracking-[0.25em] text-zinc-400">
                SessionGrid
              </p>
            </div>
            <h1 className="mt-1 text-3xl font-semibold">{project.name}</h1>
            <p className="mt-2 max-w-3xl text-sm text-zinc-400">
              {project.original_filename}
              {project.duration_seconds &&
                ` • ${Math.floor(project.duration_seconds / 60)}:${Math.floor(project.duration_seconds % 60).toString().padStart(2, "0")}`}
              {project.analysis &&
                ` • ${project.analysis.overall_bpm} BPM`}
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => router.push("/projects")}
              className="btn-secondary"
            >
              Open Project
            </button>
            <Link href="/" className="btn-primary">
              Upload Track
            </Link>
          </div>
        </div>

        {/* ─── Processing State ─────────────────────────────────────── */}
        {isProcessing && (
          <ProcessingView
            status={project.status}
            message={project.status_message}
          />
        )}

        {/* ─── Failed State ─────────────────────────────────────────── */}
        {project.status === "failed" && (
          <div className="mb-6 rounded-3xl border border-rose-500/20 bg-rose-500/5 p-6 text-center">
            <p className="text-lg font-semibold text-rose-300">
              Analysis Failed
            </p>
            <p className="mt-2 text-sm text-zinc-400">
              {project.status_message}
            </p>
            <button
              onClick={async () => {
                await triggerAnalysis(project.id);
                loadProject();
              }}
              className="btn-secondary mt-4"
            >
              <RefreshCw className="mr-2 inline h-4 w-4" /> Retry Analysis
            </button>
          </div>
        )}

        {/* ─── Main Dashboard (Complete) ───────────────────────────── */}
        {project.status === "complete" && project.analysis && (
          <AudioEngineProvider projectId={project.id}>
            <SectionSync
              sections={project.sections}
              activeSection={activeSection}
              isLooping={isLooping}
              onAutoSection={handleWaveformSectionChange}
            />
            {/* Quick-start tips */}
            <div className="mb-6 rounded-2xl border border-cyan-400/10 bg-cyan-400/5 px-5 py-4">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-zinc-300">
                <span className="font-medium text-cyan-300">Quick start:</span>
                <span>▶ Press <kbd className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-cyan-300">Play</kbd> or click the waveform to listen</span>
                <span>🎯 Pick a section in the <strong>Arrangement Map</strong> to loop it</span>
                <span>🔀 Switch between <strong>Mix</strong>, <strong>Drums</strong>, or <strong>Click</strong> modes above the waveform</span>
                <span>⚡ Use <strong>-10% / +10%</strong> to slow down or speed up</span>
              </div>
            </div>

            <div className="grid gap-6 xl:grid-cols-[300px_minmax(0,1fr)_340px]">
            {/* Left Sidebar */}
            <ProjectSidebar
              project={project}
              playbackMode={playbackMode}
              onPlaybackModeChange={setPlaybackMode}
            />

            {/* Main Content */}
            <main className="space-y-6">
              <TimelinePanel
                project={project}
                currentSection={currentSection}
                activeSection={activeSection}
                playbackMode={playbackMode}
                onPlaybackModeChange={setPlaybackMode}
                onSectionSelect={handleWaveformSectionChange}
              />

              <PracticeDeck
                project={project}
                currentSection={currentSection}
                activeSection={activeSection}
                isLooping={isLooping}
              />
            </main>

            {/* Right Sidebar */}
            <aside className="space-y-6">
              <ArrangementMap
                sections={project.sections}
                activeSection={activeSection}
                onSectionSelect={handleArrangementSelect}
              />
              <ExportPanel projectId={project.id} />
            </aside>
          </div>
          </AudioEngineProvider>
        )}
      </div>
    </div>
  );
}
