"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { Section } from "@/lib/types";
import { getAudioUrl, getStemUrl, getClickUrl } from "@/lib/api";

/* ─── Types ───────────────────────────────────────────────────────────── */

export type PlaybackMode = "mix" | "drums" | "click" | "click_drums" | "vocals" | "bass" | "other";

interface AudioEngineState {
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  playbackMode: PlaybackMode;
  loopSection: Section | null;
  playbackRate: number;
}

interface AudioEngineActions {
  play: () => void;
  pause: () => void;
  toggle: () => void;
  seek: (time: number) => void;
  seekFraction: (fraction: number) => void;
  setPlaybackMode: (mode: PlaybackMode) => void;
  setLoopSection: (section: Section | null) => void;
  setPlaybackRate: (rate: number) => void;
}

type AudioEngine = AudioEngineState & AudioEngineActions;

const AudioEngineContext = createContext<AudioEngine | null>(null);

export function useAudioEngine(): AudioEngine {
  const ctx = useContext(AudioEngineContext);
  if (!ctx) throw new Error("useAudioEngine must be inside AudioEngineProvider");
  return ctx;
}

/* ─── Provider ────────────────────────────────────────────────────────── */

interface AudioEngineProviderProps {
  projectId: string;
  children: React.ReactNode;
}

export function AudioEngineProvider({
  projectId,
  children,
}: AudioEngineProviderProps) {
  /* Refs for the two audio layers we blend */
  const primaryRef = useRef<HTMLAudioElement | null>(null);
  const clickRef = useRef<HTMLAudioElement | null>(null);

  /* State */
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackMode, setPlaybackModeState] = useState<PlaybackMode>("mix");
  const [loopSection, setLoopSection] = useState<Section | null>(null);
  const [playbackRate, setPlaybackRateState] = useState(1);

  /* ── Build audio URLs ─────────────────────────────────────────────── */
  const urlFor = useCallback(
    (mode: PlaybackMode) => {
      switch (mode) {
        case "mix":
          return getAudioUrl(projectId);
        case "drums":
        case "click_drums":
          return getStemUrl(projectId, "drums");
        case "click":
          return getClickUrl(projectId);
        case "vocals":
          return getStemUrl(projectId, "vocals");
        case "bass":
          return getStemUrl(projectId, "bass");
        case "other":
          return getStemUrl(projectId, "other");
        default:
          return getAudioUrl(projectId);
      }
    },
    [projectId]
  );

  /* ── Create / swap <audio> elements when mode changes ─────────────── */
  useEffect(() => {
    // Primary audio source
    if (!primaryRef.current) {
      primaryRef.current = new Audio();
      primaryRef.current.preload = "auto";
    }
    const primary = primaryRef.current;
    const src = urlFor(playbackMode);

    // Compare only the pathname portion — primary.src is always absolute
    const currentPath = (() => {
      try { return new URL(primary.src).pathname; } catch { return ""; }
    })();
    const targetPath = (() => {
      try { return new URL(src, window.location.origin).pathname; } catch { return src; }
    })();

    if (currentPath !== targetPath) {
      const wasPlaying = !primary.paused;
      const prevTime = primary.currentTime;
      primary.src = src;
      // Wait for the new source to be ready before seeking
      const onCanPlay = () => {
        primary.currentTime = prevTime || 0;
        if (wasPlaying) primary.play().catch(() => {});
        primary.removeEventListener("canplay", onCanPlay);
      };
      primary.addEventListener("canplay", onCanPlay);
      primary.load();
    }

    // Click layer (only needed for click_drums mode)
    if (playbackMode === "click_drums") {
      if (!clickRef.current) {
        clickRef.current = new Audio();
        clickRef.current.preload = "auto";
      }
      const clickSrc = getClickUrl(projectId);
      const clickPath = (() => {
        try { return new URL(clickRef.current!.src).pathname; } catch { return ""; }
      })();
      const clickTarget = (() => {
        try { return new URL(clickSrc, window.location.origin).pathname; } catch { return clickSrc; }
      })();
      if (clickPath !== clickTarget) {
        clickRef.current.src = clickSrc;
        clickRef.current.load();
      }
      clickRef.current.currentTime = primary.currentTime;
      clickRef.current.playbackRate = primary.playbackRate;
      if (!primary.paused) clickRef.current.play().catch(() => {});
    } else if (clickRef.current) {
      clickRef.current.pause();
    }
  }, [playbackMode, projectId, urlFor]);

  /* ── timeupdate / metadata listeners ──────────────────────────────── */
  useEffect(() => {
    const primary = primaryRef.current;
    if (!primary) return;

    const onTime = () => setCurrentTime(primary.currentTime);
    const onMeta = () => setDuration(primary.duration || 0);
    const onEnded = () => {
      setIsPlaying(false);
      clickRef.current?.pause();
    };

    primary.addEventListener("timeupdate", onTime);
    primary.addEventListener("loadedmetadata", onMeta);
    primary.addEventListener("durationchange", onMeta);
    primary.addEventListener("ended", onEnded);

    return () => {
      primary.removeEventListener("timeupdate", onTime);
      primary.removeEventListener("loadedmetadata", onMeta);
      primary.removeEventListener("durationchange", onMeta);
      primary.removeEventListener("ended", onEnded);
    };
  }, []);

  /* ── Section looping ──────────────────────────────────────────────── */
  useEffect(() => {
    if (!loopSection) return;
    const primary = primaryRef.current;
    if (!primary) return;

    const check = () => {
      if (primary.currentTime >= loopSection.end_time) {
        primary.currentTime = loopSection.start_time;
        if (clickRef.current) clickRef.current.currentTime = loopSection.start_time;
      }
    };

    primary.addEventListener("timeupdate", check);
    return () => primary.removeEventListener("timeupdate", check);
  }, [loopSection]);

  /* ── Playback rate sync ───────────────────────────────────────────── */
  useEffect(() => {
    if (primaryRef.current) primaryRef.current.playbackRate = playbackRate;
    if (clickRef.current) clickRef.current.playbackRate = playbackRate;
  }, [playbackRate]);

  /* ── Actions ──────────────────────────────────────────────────────── */
  const play = useCallback(() => {
    const primary = primaryRef.current;
    if (!primary) return;

    // If we have a loop section and we're outside it, jump to loop start
    if (loopSection && (primary.currentTime < loopSection.start_time || primary.currentTime >= loopSection.end_time)) {
      primary.currentTime = loopSection.start_time;
      if (clickRef.current) clickRef.current.currentTime = loopSection.start_time;
    }

    primary.play().catch(() => {});
    if (playbackMode === "click_drums" && clickRef.current) {
      clickRef.current.currentTime = primary.currentTime;
      clickRef.current.play().catch(() => {});
    }
    setIsPlaying(true);
  }, [loopSection, playbackMode]);

  const pause = useCallback(() => {
    primaryRef.current?.pause();
    clickRef.current?.pause();
    setIsPlaying(false);
  }, []);

  const toggle = useCallback(() => {
    isPlaying ? pause() : play();
  }, [isPlaying, pause, play]);

  const seek = useCallback((time: number) => {
    const primary = primaryRef.current;
    if (!primary) return;
    primary.currentTime = time;
    if (clickRef.current) clickRef.current.currentTime = time;
    setCurrentTime(time);
  }, []);

  const seekFraction = useCallback(
    (fraction: number) => {
      seek(fraction * duration);
    },
    [duration, seek]
  );

  const setPlaybackMode = useCallback(
    (mode: PlaybackMode) => setPlaybackModeState(mode),
    []
  );

  const setPlaybackRate = useCallback(
    (rate: number) => setPlaybackRateState(rate),
    []
  );

  /* ── Context value ────────────────────────────────────────────────── */
  const value: AudioEngine = {
    isPlaying,
    currentTime,
    duration,
    playbackMode,
    loopSection,
    playbackRate,
    play,
    pause,
    toggle,
    seek,
    seekFraction,
    setPlaybackMode,
    setLoopSection,
    setPlaybackRate,
  };

  return (
    <AudioEngineContext.Provider value={value}>
      {children}
    </AudioEngineContext.Provider>
  );
}
