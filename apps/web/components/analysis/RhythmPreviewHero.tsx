"use client";

/**
 * RhythmPreviewHero — Analytical subdivision scope.
 *
 * Concentric rings (ratios 2, 3, 5, 7) with crosshair axis lines.
 * Minimal glow. Measured rotation. Instrument-panel aesthetic.
 * Parallax shift on mouse move (max 5px).
 */

import { useCallback, useRef, useState } from "react";

export default function RhythmPreviewHero() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = (e.clientX - cx) / (rect.width / 2);
    const dy = (e.clientY - cy) / (rect.height / 2);
    setOffset({ x: dx * 5, y: dy * 5 });
  }, []);

  const handleMouseLeave = useCallback(() => {
    setOffset({ x: 0, y: 0 });
  }, []);

  const rings = [
    { ratio: 2, radius: 48, dots: 2, speed: 30, opacity: 0.6 },
    { ratio: 3, radius: 76, dots: 3, speed: 45, opacity: 0.45 },
    { ratio: 5, radius: 108, dots: 5, speed: 66, opacity: 0.32 },
    { ratio: 7, radius: 140, dots: 7, speed: 96, opacity: 0.2 },
  ];

  const outerR = 155;

  return (
    <div
      ref={containerRef}
      className="relative flex items-center justify-center"
      aria-hidden="true"
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      <svg
        viewBox="-180 -180 360 360"
        className="h-[280px] w-[280px] tablet:h-[340px] tablet:w-[340px]"
        style={{
          transform: `translate(${offset.x}px, ${offset.y}px)`,
          transition: "transform 0.4s ease-out",
        }}
      >
        {/* ── Crosshair axis lines ── */}
        <line x1={-outerR} y1="0" x2={outerR} y2="0" stroke="#22d3ee" strokeWidth="0.3" opacity="0.12" />
        <line x1="0" y1={-outerR} x2="0" y2={outerR} stroke="#22d3ee" strokeWidth="0.3" opacity="0.12" />

        {/* ── Tick marks on axes ── */}
        {rings.map((ring) => (
          <g key={`tick-${ring.ratio}`}>
            <line x1={ring.radius - 3} y1="0" x2={ring.radius + 3} y2="0" stroke="#22d3ee" strokeWidth="0.4" opacity="0.18" />
            <line x1={-ring.radius - 3} y1="0" x2={-ring.radius + 3} y2="0" stroke="#22d3ee" strokeWidth="0.4" opacity="0.18" />
            <line x1="0" y1={ring.radius - 3} x2="0" y2={ring.radius + 3} stroke="#22d3ee" strokeWidth="0.4" opacity="0.18" />
            <line x1="0" y1={-ring.radius - 3} x2="0" y2={-ring.radius + 3} stroke="#22d3ee" strokeWidth="0.4" opacity="0.18" />
          </g>
        ))}

        {/* ── Centre node ── */}
        <circle cx="0" cy="0" r="3" fill="#22d3ee" opacity="0.6">
          <animate
            attributeName="opacity"
            values="0.6;0.3;0.6"
            dur="4s"
            repeatCount="indefinite"
          />
        </circle>

        {/* ── Rings ── */}
        {rings.map((ring) => (
          <g key={ring.ratio}>
            {/* Static ring */}
            <circle
              cx="0"
              cy="0"
              r={ring.radius}
              fill="none"
              stroke="#22d3ee"
              strokeWidth="0.4"
              opacity={ring.opacity * 0.35}
            />

            {/* Rotating group */}
            <g>
              <animateTransform
                attributeName="transform"
                type="rotate"
                from="0 0 0"
                to="360 0 0"
                dur={`${ring.speed}s`}
                repeatCount="indefinite"
              />

              {/* Phase line */}
              <line
                x1="0"
                y1="0"
                x2={ring.radius}
                y2="0"
                stroke="#22d3ee"
                strokeWidth="0.3"
                opacity={ring.opacity * 0.2}
              />

              {/* Subdivision dots */}
              {Array.from({ length: ring.dots }).map((_, i) => {
                const angle = (2 * Math.PI * i) / ring.dots;
                const cx = ring.radius * Math.cos(angle);
                const cy = ring.radius * Math.sin(angle);
                return (
                  <circle
                    key={i}
                    cx={cx}
                    cy={cy}
                    r={ring.ratio <= 3 ? 2 : 1.4}
                    fill="#22d3ee"
                    opacity={ring.opacity}
                  >
                    <animate
                      attributeName="opacity"
                      values={`${ring.opacity};${ring.opacity * 0.2};${ring.opacity}`}
                      dur={`${ring.speed / ring.dots}s`}
                      begin={`${(i * ring.speed) / ring.dots / ring.dots}s`}
                      repeatCount="indefinite"
                    />
                  </circle>
                );
              })}
            </g>
          </g>
        ))}
      </svg>
    </div>
  );
}
