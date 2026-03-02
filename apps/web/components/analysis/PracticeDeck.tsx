"use client";

import { useEffect } from "react";
import { Play, Pause, Minus, Plus } from "lucide-react";
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

  useEffect(() => {
    audio.setLoopSection(isLooping ? currentSection : null);
  }, [currentSection, isLooping]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="card p-4 tablet:p-5">
      <div className="flex flex-col gap-3 tablet:flex-row tablet:items-center tablet:justify-between">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
            Practice Deck
          </h2>
          <p className="mt-0.5 text-xs text-text-muted">
            Built for session prep
          </p>
        </div>

        {/* Speed Controls — pill shaped */}
        <div className="flex items-center gap-1 rounded-xl bg-surface p-1">
          <button
            onClick={() => audio.setPlaybackRate(Math.max(0.5, audio.playbackRate - 0.1))}
            className="btn-icon h-9 w-9 rounded-lg"
            aria-label="Decrease speed"
          >
            <Minus className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => audio.setPlaybackRate(1)}
            className={`rounded-lg px-4 py-2 text-sm font-semibold tabular-nums transition-colors ${
              audio.playbackRate === 1
                ? "text-accent"
                : "text-text-primary"
            }`}
          >
            {Math.round(audio.playbackRate * 100)}%
          </button>
          <button
            onClick={() => audio.setPlaybackRate(Math.min(1.5, audio.playbackRate + 0.1))}
            className="btn-icon h-9 w-9 rounded-lg"
            aria-label="Increase speed"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 tablet:grid-cols-[1.1fr_0.9fr]">
        {/* Bar Counter & Transport */}
        <div className="rounded-xl bg-surface p-4 tablet:p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-text-muted">Bar</p>
              <p className="mt-1 text-4xl font-bold tabular-nums tablet:text-5xl">
                {currentBar}
                <span className="text-lg font-normal text-text-muted">
                  {" "}/ {currentSection?.bars || "--"}
                </span>
              </p>
            </div>
            {currentSection && isLooping && (
              <div className="badge border-accent/30 bg-accent-muted text-accent-hover">
                Looping {currentSection.name}
              </div>
            )}
          </div>

          {/* Transport controls */}
          <div className="mt-5 flex items-center gap-2">
            <button
              onClick={audio.toggle}
              className="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent text-white shadow-lg transition-all hover:bg-accent-hover active:scale-95"
              style={{ boxShadow: "0 4px 20px rgba(139, 92, 246, 0.3)" }}
              aria-label={audio.isPlaying ? "Pause" : "Play"}
            >
              {audio.isPlaying ? (
                <Pause className="h-6 w-6" />
              ) : (
                <Play className="ml-0.5 h-6 w-6" />
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
        <div className="rounded-xl bg-surface p-4 tablet:p-5">
          <p className="text-xs font-medium uppercase tracking-wider text-text-muted">
            AI cues
          </p>
          <ul className="mt-3 space-y-2 text-sm text-text-primary">
            {currentSection && currentSection.confidence === "medium" ? (
              <>
                <li className="rounded-xl border border-white/[0.06] bg-surface-raised p-3">
                  Likely pickup into the next section on bar{" "}
                  {currentSection.bars || "?"}.
                </li>
                <li className="rounded-xl border border-white/[0.06] bg-surface-raised p-3">
                  Snare accent suggests a stronger backbeat click may help.
                </li>
                <li className="rounded-xl border border-amber-500/20 bg-amber-500/[0.06] p-3 text-amber-200">
                  Meter confidence is medium — manual override if this
                  section feels like a tag.
                </li>
              </>
            ) : currentSection?.confidence === "low" ? (
              <>
                <li className="rounded-xl border border-rose-500/20 bg-rose-500/[0.06] p-3 text-rose-200">
                  Low confidence. The beat grid may not be accurate — manual
                  review recommended.
                </li>
                <li className="rounded-xl border border-white/[0.06] bg-surface-raised p-3">
                  Consider adjusting section boundaries manually.
                </li>
              </>
            ) : (
              <>
                <li className="rounded-xl border border-white/[0.06] bg-surface-raised p-3">
                  Beat grid looks solid. Click track should align well.
                </li>
                <li className="rounded-xl border border-white/[0.06] bg-surface-raised p-3">
                  {project.analysis?.bpm_stable
                    ? "Tempo is stable throughout this section."
                    : "Tempo may drift slightly — the click follows the detected grid."}
                </li>
                <li className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.06] p-3 text-emerald-200">
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
