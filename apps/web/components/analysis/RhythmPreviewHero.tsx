"use client";

/**
 * RhythmPreviewHero — Animated concentric subdivision rings.
 *
 * Pure CSS + React state animation. No external dependencies.
 * Rings represent subdivision ratios 2, 3, 5, 7 with rotating phase lines
 * and subtle pulsing. Parallax shift on mouse move (max 8px).
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
    setOffset({ x: dx * 8, y: dy * 8 });
  }, []);

  const handleMouseLeave = useCallback(() => {
    setOffset({ x: 0, y: 0 });
  }, []);

  const rings = [
    { ratio: 2, radius: 52, dots: 2, speed: 24, opacity: 0.7 },
    { ratio: 3, radius: 80, dots: 3, speed: 36, opacity: 0.55 },
    { ratio: 5, radius: 112, dots: 5, speed: 55, opacity: 0.4 },
    { ratio: 7, radius: 146, dots: 7, speed: 80, opacity: 0.28 },
  ];

  return (
    <div
      ref={containerRef}
      className="relative flex items-center justify-center"
      aria-hidden="true"
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      {/* Outer radial glow */}
      <div
        className="pointer-events-none absolute h-[420px] w-[420px] rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(34,211,238,0.06) 0%, rgba(34,211,238,0.02) 40%, transparent 70%)",
        }}
      />

      {/* Centre bloom */}
      <div
        className="pointer-events-none absolute h-32 w-32 rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(34,211,238,0.12) 0%, rgba(34,211,238,0.04) 50%, transparent 80%)",
          animation: "bloomPulse 4s ease-in-out infinite",
        }}
      />

      <svg
        viewBox="-180 -180 360 360"
        className="h-[320px] w-[320px] tablet:h-[400px] tablet:w-[400px]"
        style={{
          transform: `translate(${offset.x}px, ${offset.y}px)`,
          transition: "transform 0.3s ease-out",
        }}
      >
        <defs>
          <radialGradient id="centerGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Soft centre glow disc */}
        <circle cx="0" cy="0" r="24" fill="url(#centerGlow)">
          <animate
            attributeName="r"
            values="20;28;20"
            dur="4s"
            repeatCount="indefinite"
          />
        </circle>

        {/* Centre pulse node */}
        <circle cx="0" cy="0" r="5" fill="#22d3ee" opacity="0.9">
          <animate
            attributeName="r"
            values="4;6.5;4"
            dur="3s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0.9;0.45;0.9"
            dur="3s"
            repeatCount="indefinite"
          />
        </circle>

        {rings.map((ring) => (
          <g key={ring.ratio}>
            {/* Ring circle */}
            <circle
              cx="0"
              cy="0"
              r={ring.radius}
              fill="none"
              stroke="#22d3ee"
              strokeWidth="0.5"
              opacity={ring.opacity * 0.4}
            >
              <animate
                attributeName="opacity"
                values={`${ring.opacity * 0.2};${ring.opacity * 0.5};${ring.opacity * 0.2}`}
                dur={`${ring.speed / 4}s`}
                repeatCount="indefinite"
              />
            </circle>

            {/* Rotating group with subdivision dots + phase line */}
            <g>
              <animateTransform
                attributeName="transform"
                type="rotate"
                from="0 0 0"
                to="360 0 0"
                dur={`${ring.speed}s`}
                repeatCount="indefinite"
              />

              {/* Phase line from centre to ring */}
              <line
                x1="0"
                y1="0"
                x2={ring.radius}
                y2="0"
                stroke="#22d3ee"
                strokeWidth="0.4"
                opacity={ring.opacity * 0.3}
              />

              {/* Subdivision dots equally spaced around the ring */}
              {Array.from({ length: ring.dots }).map((_, i) => {
                const angle = (2 * Math.PI * i) / ring.dots;
                const cx = ring.radius * Math.cos(angle);
                const cy = ring.radius * Math.sin(angle);
                return (
                  <circle
                    key={i}
                    cx={cx}
                    cy={cy}
                    r={ring.ratio <= 3 ? 2.5 : 1.8}
                    fill="#22d3ee"
                    opacity={ring.opacity}
                  >
                    <animate
                      attributeName="opacity"
                      values={`${ring.opacity};${ring.opacity * 0.25};${ring.opacity}`}
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

      {/* Inline keyframes for bloom pulse */}
      <style jsx>{`
        @keyframes bloomPulse {
          0%, 100% { opacity: 0.5; transform: scale(1); }
          50% { opacity: 1; transform: scale(1.15); }
        }
      `}</style>
    </div>
  );
}
