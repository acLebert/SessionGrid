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

/* Accent colors in RGBA for canvas */
const ACCENT = { r: 139, g: 92, b: 246 }; // #8b5cf6

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

    ctx.clearRect(0, 0, width, height);

    // Draw thin center line
    ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
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
        ctx.fillStyle = `rgba(${ACCENT.r}, ${ACCENT.g}, ${ACCENT.b}, 0.08)`;
        ctx.fillRect(sx, 0, ex - sx, height);
      }

      // Section boundary line
      if (idx > 0) {
        ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(sx, 0);
        ctx.lineTo(sx, height);
        ctx.stroke();
      }
    });

    // Draw waveform bars
    const barWidth = Math.max(1.5, width / peaks.length - 1);
    const gap = Math.max(0.5, (width - barWidth * peaks.length) / peaks.length);
    peaks.forEach((peak, i) => {
      const x = i * (barWidth + gap);
      const time = (i / peaks.length) * duration;

      const inActive = sections[activeSection] &&
        time >= sections[activeSection].start_time &&
        time <= sections[activeSection].end_time;

      // Played portion is brighter
      const played = (i / peaks.length) <= playheadPosition;

      const maxH = Math.abs(peak.max) * centerY * 0.85;
      const minH = Math.abs(peak.min) * centerY * 0.85;

      if (inActive) {
        ctx.fillStyle = played
          ? `rgba(${ACCENT.r}, ${ACCENT.g}, ${ACCENT.b}, 0.75)`
          : `rgba(${ACCENT.r}, ${ACCENT.g}, ${ACCENT.b}, 0.4)`;
      } else {
        ctx.fillStyle = played
          ? "rgba(255, 255, 255, 0.35)"
          : "rgba(255, 255, 255, 0.12)";
      }

      // Draw rounded bars
      const radius = barWidth / 2;
      // Top bar
      ctx.beginPath();
      ctx.roundRect(x, centerY - maxH, barWidth, maxH, [radius, radius, 0, 0]);
      ctx.fill();
      // Bottom bar
      ctx.beginPath();
      ctx.roundRect(x, centerY, barWidth, minH, [0, 0, radius, radius]);
      ctx.fill();
    });

    // Draw playhead
    const playheadX = playheadPosition * width;
    ctx.strokeStyle = `rgba(${ACCENT.r}, ${ACCENT.g}, ${ACCENT.b}, 1)`;
    ctx.lineWidth = 2;
    ctx.shadowColor = `rgba(${ACCENT.r}, ${ACCENT.g}, ${ACCENT.b}, 0.6)`;
    ctx.shadowBlur = 16;
    ctx.beginPath();
    ctx.moveTo(playheadX, 0);
    ctx.lineTo(playheadX, height);
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Playhead dot
    ctx.fillStyle = `rgba(${ACCENT.r}, ${ACCENT.g}, ${ACCENT.b}, 1)`;
    ctx.beginPath();
    ctx.arc(playheadX, 4, 4, 0, Math.PI * 2);
    ctx.fill();
  }, [waveformData, sections, activeSection, playheadPosition]);

  // Handle click on waveform to seek audio and select section
  const handleClick = (e: React.MouseEvent | React.TouchEvent) => {
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const clientX = "touches" in e ? e.changedTouches[0].clientX : e.clientX;
    const fraction = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    audio.seekFraction(fraction);

    if (onSectionSelect && audio.duration > 0) {
      const clickedTime = fraction * audio.duration;
      const idx = sections.findIndex(
        (s) => clickedTime >= s.start_time && clickedTime < s.end_time
      );
      if (idx >= 0) onSectionSelect(idx);
    }
  };

  return (
    <div className="relative touch-pan-y">
      {/* Section labels — horizontally scrollable on tablet */}
      <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1 scrollbar-none snap-x-mandatory">
        {sections.map((section, idx) => (
          <span
            key={section.id}
            className={`snap-start ${
              idx === activeSection
                ? "section-pill-active"
                : "section-pill-inactive"
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
        className="relative h-32 cursor-crosshair overflow-hidden rounded-xl bg-gradient-to-b from-surface-raised to-surface tablet:h-40"
        onClick={handleClick}
        onTouchEnd={handleClick}
      >
        <canvas ref={canvasRef} className="absolute inset-0" />
      </div>
    </div>
  );
}
