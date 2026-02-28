"use client";

import { useEffect } from "react";
import { Play, Pause } from "lucide-react";
import type { Project, Section } from "@/lib/types";
import { getClickUrl } from "@/lib/api";
import { useAudioEngine } from "@/components/player/AudioEngine";

interface PracticeDeckProps {
  project: Project;
  currentSection: Section | null;
  activeSection: number;
  isLooping: boolean;
}

function computeCurrentBar(
  currentTime: number,
  section: Section | null
): number {
  if (!section || !section.bars || section.bars <= 0) return 1;
  const elapsed = currentTime - section.start_time;
  const sectionDuration = section.end_time - section.start_time;
  if (sectionDuration <= 0 || elapsed <= 0) return 1;
  const fraction = Math.min(elapsed / sectionDuration, 1);
  return Math.min(Math.floor(fraction * section.bars) + 1, section.bars);
}

export function PracticeDeck({
  project,
  currentSection,
  activeSection,
  isLooping,
}: PracticeDeckProps) {
  const audio = useAudioEngine();
  const currentBar = computeCurrentBar(audio.currentTime, currentSection);

  // Only constrain playback when user explicitly selected a section to loop
  useEffect(() => {
    audio.setLoopSection(isLooping ? currentSection : null);
  }, [currentSection, isLooping]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="glass-panel p-5">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Practice Deck</h2>
          <p className="mt-1 text-sm text-zinc-400">
            Built for session prep, not notation-first analysis.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => audio.setPlaybackRate(Math.max(0.5, audio.playbackRate - 0.1))}
            className="btn-ghost"
          >
            -10%
          </button>
          <button
            onClick={() => audio.setPlaybackRate(1)}
            className={`btn-ghost ${
              audio.playbackRate === 1 ? "border-cyan-400/30 text-cyan-300" : ""
            }`}
          >
            {Math.round(audio.playbackRate * 100)}%
          </button>
          <button
            onClick={() => audio.setPlaybackRate(Math.min(1.5, audio.playbackRate + 0.1))}
            className="btn-ghost"
          >
            +10%
          </button>
        </div>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-[1.1fr_0.9fr]">
        {/* Bar Counter & Controls */}
        <div className="rounded-2xl bg-zinc-900/70 p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-zinc-400">Bar counter</p>
              <p className="mt-1 text-5xl font-semibold tabular-nums">
                {currentBar} / {currentSection?.bars || "--"}
              </p>
            </div>
            {currentSection && isLooping && (
              <div className="rounded-full border border-cyan-400/40 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-200">
                Looping {currentSection.name}
              </div>
            )}
          </div>
          <div className="mt-6 flex items-center gap-3">
            <button
              onClick={audio.toggle}
              className="flex h-14 w-14 items-center justify-center rounded-full bg-cyan-400 text-xl font-bold text-zinc-950 transition-colors hover:bg-cyan-300"
            >
              {audio.isPlaying ? (
                <Pause className="h-6 w-6" />
              ) : (
                <Play className="ml-1 h-6 w-6" />
              )}
            </button>
            <button className="btn-ghost">Count In</button>
            <button className="btn-ghost">Rehearse Fill</button>
            <a
              href={getClickUrl(project.id)}
              download="click.wav"
              className="btn-ghost"
            >
              Export Click
            </a>
          </div>
        </div>

        {/* AI Cues */}
        <div className="rounded-2xl bg-zinc-900/70 p-5">
          <p className="text-sm text-zinc-400">AI cues</p>
          <ul className="mt-3 space-y-3 text-sm text-zinc-200">
            {currentSection && currentSection.confidence === "medium" ? (
              <>
                <li className="rounded-2xl border border-white/10 bg-zinc-950/80 p-3">
                  Likely pickup into the next section on bar{" "}
                  {currentSection.bars || "?"}.
                </li>
                <li className="rounded-2xl border border-white/10 bg-zinc-950/80 p-3">
                  Snare accent suggests a stronger backbeat click may help here.
                </li>
                <li className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-3 text-amber-100">
                  Meter confidence is medium. Allow manual override if this
                  section feels like a tag.
                </li>
              </>
            ) : currentSection?.confidence === "low" ? (
              <>
                <li className="rounded-2xl border border-rose-500/20 bg-rose-500/10 p-3 text-rose-100">
                  Low confidence on this section. The beat grid may not be
                  accurate — manual review recommended.
                </li>
                <li className="rounded-2xl border border-white/10 bg-zinc-950/80 p-3">
                  Consider adjusting section boundaries manually.
                </li>
              </>
            ) : (
              <>
                <li className="rounded-2xl border border-white/10 bg-zinc-950/80 p-3">
                  Beat grid looks solid. Click track should align well.
                </li>
                <li className="rounded-2xl border border-white/10 bg-zinc-950/80 p-3">
                  {project.analysis?.bpm_stable
                    ? "Tempo is stable throughout this section."
                    : "Tempo may drift slightly — the click follows the detected grid."}
                </li>
                <li className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-emerald-100">
                  High confidence. This section is rehearsal-ready.
                </li>
              </>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
