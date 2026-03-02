"use client";

/**
 * RhythmPreviewHero — Animated concentric subdivision rings.
 *
 * Pure CSS animation. No external dependencies.
 * Rings represent subdivision ratios 2, 3, 5, 7 with rotating phase lines
 * and subtle pulsing. Suggests layered rhythmic structure at a glance.
 */

export default function RhythmPreviewHero() {
  const rings = [
    { ratio: 2, radius: 52, dots: 2, speed: 12, opacity: 0.7 },
    { ratio: 3, radius: 80, dots: 3, speed: 18, opacity: 0.55 },
    { ratio: 5, radius: 112, dots: 5, speed: 30, opacity: 0.4 },
    { ratio: 7, radius: 146, dots: 7, speed: 45, opacity: 0.28 },
  ];

  return (
    <div className="relative flex items-center justify-center" aria-hidden="true">
      {/* Glow backdrop */}
      <div
        className="absolute h-72 w-72 rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(34,211,238,0.08) 0%, transparent 70%)",
        }}
      />

      <svg
        viewBox="-180 -180 360 360"
        className="h-[320px] w-[320px] tablet:h-[380px] tablet:w-[380px]"
      >
        {/* Centre pulse */}
        <circle cx="0" cy="0" r="6" fill="#22d3ee" opacity="0.8">
          <animate
            attributeName="r"
            values="5;8;5"
            dur="2s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0.8;0.4;0.8"
            dur="2s"
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
              opacity={ring.opacity * 0.5}
            >
              <animate
                attributeName="opacity"
                values={`${ring.opacity * 0.3};${ring.opacity * 0.6};${ring.opacity * 0.3}`}
                dur={`${ring.speed / 3}s`}
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
                strokeWidth="0.5"
                opacity={ring.opacity * 0.4}
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
                    r={ring.ratio <= 3 ? 3 : 2}
                    fill="#22d3ee"
                    opacity={ring.opacity}
                  >
                    <animate
                      attributeName="opacity"
                      values={`${ring.opacity};${ring.opacity * 0.3};${ring.opacity}`}
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
