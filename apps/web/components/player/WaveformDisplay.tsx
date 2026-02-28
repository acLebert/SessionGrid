"use client";

import { useEffect, useRef, useState } from "react";
import type { Section, WaveformData } from "@/lib/types";
import { getWaveformData } from "@/lib/api";
import { useAudioEngine } from "@/components/player/AudioEngine";

interface WaveformDisplayProps {
  projectId: string;
  sections: Section[];
  activeSection: number;
  playbackMode: string;
  onSectionSelect?: (index: number) => void;
}

interface PeakData {
  min: number;
  max: number;
  rms: number;
}

export function WaveformDisplay({
  projectId,
  sections,
  activeSection,
  playbackMode,
  onSectionSelect,
}: WaveformDisplayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [waveformData, setWaveformData] = useState<WaveformData | null>(null);
  const audio = useAudioEngine();
  const playheadPosition = audio.duration > 0 ? audio.currentTime / audio.duration : 0;

  // Load waveform data
  useEffect(() => {
    const stem = playbackMode === "drums" || playbackMode === "click_drums" ? "drums" : "mix";
    
    getWaveformData(projectId, stem)
      .then(setWaveformData)
      .catch(() => {
        // Generate placeholder waveform data for initial state
        const fakePeaks: PeakData[] = Array.from({ length: 200 }, () => ({
          min: -(0.1 + Math.random() * 0.6),
          max: 0.1 + Math.random() * 0.6,
          rms: 0.1 + Math.random() * 0.4,
        }));
        setWaveformData({
          peaks: fakePeaks,
          duration: 240,
          sample_rate: 44100,
          points_per_second: 10,
          total_points: 200,
        });
      });
  }, [projectId, playbackMode]);

  // Render waveform
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || !waveformData) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = container.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = rect.height;
    const centerY = height / 2;
    const { peaks, duration } = waveformData;

    // Clear
    ctx.clearRect(0, 0, width, height);

    // Draw center line
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, centerY);
    ctx.lineTo(width, centerY);
    ctx.stroke();

    // Draw section backgrounds
    sections.forEach((section, idx) => {
      const sx = (section.start_time / duration) * width;
      const ex = (section.end_time / duration) * width;

      if (idx === activeSection) {
        ctx.fillStyle = "rgba(34, 211, 238, 0.06)";
        ctx.fillRect(sx, 0, ex - sx, height);
      }

      // Section boundary line
      if (idx > 0) {
        ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(sx, 0);
        ctx.lineTo(sx, height);
        ctx.stroke();
      }
    });

    // Draw waveform bars
    const barWidth = Math.max(1, width / peaks.length - 0.5);
    peaks.forEach((peak, i) => {
      const x = (i / peaks.length) * width;
      const time = (i / peaks.length) * duration;

      // Determine if this peak is in the active section
      const inActive = sections[activeSection] &&
        time >= sections[activeSection].start_time &&
        time <= sections[activeSection].end_time;

      const maxH = Math.abs(peak.max) * centerY * 0.85;
      const minH = Math.abs(peak.min) * centerY * 0.85;

      ctx.fillStyle = inActive
        ? "rgba(34, 211, 238, 0.5)"
        : "rgba(34, 211, 238, 0.2)";

      // Draw symmetric bar
      ctx.fillRect(x, centerY - maxH, barWidth, maxH);
      ctx.fillRect(x, centerY, barWidth, minH);
    });

    // Draw playhead
    const playheadX = playheadPosition * width;
    ctx.strokeStyle = "rgba(34, 211, 238, 1)";
    ctx.lineWidth = 2;
    ctx.shadowColor = "rgba(34, 211, 238, 0.65)";
    ctx.shadowBlur = 24;
    ctx.beginPath();
    ctx.moveTo(playheadX, 0);
    ctx.lineTo(playheadX, height);
    ctx.stroke();
    ctx.shadowBlur = 0;
  }, [waveformData, sections, activeSection, playheadPosition]);

  // Handle click on waveform to seek audio and select section
  const handleClick = (e: React.MouseEvent) => {
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const fraction = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    audio.seekFraction(fraction);

    // Auto-detect which section was clicked
    if (onSectionSelect && audio.duration > 0) {
      const clickedTime = fraction * audio.duration;
      const idx = sections.findIndex(
        (s) => clickedTime >= s.start_time && clickedTime < s.end_time
      );
      if (idx >= 0) onSectionSelect(idx);
    }
  };

  return (
    <div className="relative">
      {/* Section labels */}
      <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1 text-xs font-medium scrollbar-none">
        {sections.map((section, idx) => (
          <span
            key={section.id}
            className={`flex-shrink-0 rounded-full px-2.5 py-1 ${
              idx === activeSection
                ? "bg-cyan-400/20 text-cyan-200"
                : "bg-zinc-800/90 text-zinc-400"
            }`}
          >
            {section.name.length > 12
              ? section.name.slice(0, 11) + "…"
              : section.name}
          </span>
        ))}
      </div>

      {/* Waveform canvas */}
      <div
        ref={containerRef}
        className="relative h-40 cursor-crosshair overflow-hidden rounded-2xl bg-gradient-to-b from-zinc-800 to-zinc-950"
        onClick={handleClick}
      >
        <canvas ref={canvasRef} className="absolute inset-0" />
      </div>
    </div>
  );
}
