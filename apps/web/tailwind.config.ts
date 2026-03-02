import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#111114",
          raised: "#1a1a1f",
          overlay: "#222228",
          border: "rgba(255,255,255,0.06)",
        },
        accent: {
          DEFAULT: "#22d3ee",
          hover: "#67e8f9",
          muted: "rgba(34,211,238,0.15)",
          glow: "rgba(34,211,238,0.35)",
        },
        text: {
          primary: "#e5e5ea",
          secondary: "#8e8e93",
          muted: "#5c5c66",
        },
        track: {
          vocals: "#818cf8",
          drums: "#f59e0b",
          bass: "#22d3ee",
          other: "#a78bfa",
          mix: "#94a3b8",
          click: "#6b7280",
        },
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.25rem",
        "4xl": "1.5rem",
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }],
      },
      spacing: {
        "safe-b": "env(safe-area-inset-bottom, 0px)",
        "safe-t": "env(safe-area-inset-top, 0px)",
        18: "4.5rem",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.2s ease-out",
        "fade-up": "fadeUp 0.35s ease-out",
        "scale-in": "scaleIn 0.2s ease-out",
        "slide-up": "slideUp 0.3s ease-out",
        shimmer: "shimmer 2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        slideUp: {
          "0%": { transform: "translateY(100%)" },
          "100%": { transform: "translateY(0)" },
        },
        shimmer: {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
      },
      screens: {
        xs: "475px",
        tablet: "768px",
        "tablet-lg": "1024px",
      },
    },
  },
  plugins: [],
};

export default config;
