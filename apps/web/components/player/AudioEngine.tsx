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

export type StemId = "vocals" | "drums" | "bass" | "other" | "click";

interface StemState {
  muted: boolean;
  solo: boolean;
  volume: number; // 0–1
}

interface AudioEngineState {
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  stems: Record<StemId, StemState>;
  loopSection: Section | null;
  playbackRate: number;
  isReady: boolean;
  /* Legacy compat */
  playbackMode: string;
}

interface AudioEngineActions {
  play: () => void;
  pause: () => void;
  toggle: () => void;
  seek: (time: number) => void;
  seekFraction: (fraction: number) => void;
  toggleMute: (stemId: StemId) => void;
  toggleSolo: (stemId: StemId) => void;
  setStemVolume: (stemId: StemId, volume: number) => void;
  setLoopSection: (section: Section | null) => void;
  setPlaybackRate: (rate: number) => void;
  /* Legacy compat — maps to solo behaviour */
  setPlaybackMode: (mode: string) => void;
}

type AudioEngine = AudioEngineState & AudioEngineActions;

const AudioEngineContext = createContext<AudioEngine | null>(null);

export function useAudioEngine(): AudioEngine {
  const ctx = useContext(AudioEngineContext);
  if (!ctx) throw new Error("useAudioEngine must be inside AudioEngineProvider");
  return ctx;
}

/* ─── Constants ───────────────────────────────────────────────────────── */

const ALL_STEMS: StemId[] = ["vocals", "drums", "bass", "other", "click"];

const DEFAULT_STEM_STATE: StemState = {
  muted: false,
  solo: false,
  volume: 0.8,
};

function makeStemUrl(projectId: string, stemId: StemId): string {
  if (stemId === "click") return getClickUrl(projectId);
  return getStemUrl(projectId, stemId);
}

/* ─── Provider ────────────────────────────────────────────────────────── */

interface AudioEngineProviderProps {
  projectId: string;
  children: React.ReactNode;
}

/**
 * Multi-stem audio engine using Web Audio API.
 *
 * Architecture:
 *   For each stem we create:
 *     <audio> → MediaElementSourceNode → GainNode → ctx.destination
 *
 *   Mute/solo/volume all manipulate the per-stem GainNode.
 *   A "mix" <audio> loads the original audio as fallback when stems
 *   haven't loaded yet.
 *
 *   All <audio> elements share the same currentTime — we sync them
 *   on play, seek, and periodically via a drift-correction loop.
 */
export function AudioEngineProvider({
  projectId,
  children,
}: AudioEngineProviderProps) {
  /* ── Refs ────────────────────────────────────────────────────────── */
  const audioCtxRef = useRef<AudioContext | null>(null);
  const mixAudioRef = useRef<HTMLAudioElement | null>(null);
  const mixSourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  const mixGainRef = useRef<GainNode | null>(null);

  const stemAudioRefs = useRef<Partial<Record<StemId, HTMLAudioElement>>>({});
  const stemSourceRefs = useRef<Partial<Record<StemId, MediaElementAudioSourceNode>>>({});
  const stemGainRefs = useRef<Partial<Record<StemId, GainNode>>>({});
  const stemLoadedRef = useRef<Set<StemId>>(new Set());

  const rafRef = useRef<number>(0);
  const isSeekingRef = useRef(false);
  const isPlayingRef = useRef(false);

  /* ── State ───────────────────────────────────────────────────────── */
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isReady, setIsReady] = useState(false);
  const [loopSection, setLoopSection] = useState<Section | null>(null);
  const loopRef = useRef<Section | null>(null);
  const [playbackRate, setPlaybackRateState] = useState(1);
  const [stems, setStems] = useState<Record<StemId, StemState>>(() => {
    const init: Record<string, StemState> = {};
    for (const id of ALL_STEMS) {
      init[id] = { ...DEFAULT_STEM_STATE };
    }
    return init as Record<StemId, StemState>;
  });
  const stemsRef = useRef(stems);

  // Keep refs in sync
  useEffect(() => { stemsRef.current = stems; }, [stems]);
  useEffect(() => { loopRef.current = loopSection; }, [loopSection]);
  useEffect(() => { isPlayingRef.current = isPlaying; }, [isPlaying]);

  /* ── Helper: resolve effective gain for a stem ─────────────────── */
  const computeGain = useCallback(
    (stemId: StemId, snap: Record<StemId, StemState>): number => {
      const s = snap[stemId];
      if (s.muted) return 0;
      const anySolo = ALL_STEMS.some((id) => snap[id].solo);
      if (anySolo && !s.solo) return 0;
      return s.volume;
    },
    []
  );

  /* ── Apply gains to all stems + mix ────────────────────────────── */
  const applyGains = useCallback(
    (snap: Record<StemId, StemState>) => {
      const ctx = audioCtxRef.current;
      const now = ctx?.currentTime || 0;

      for (const id of ALL_STEMS) {
        const gain = stemGainRefs.current[id];
        if (gain) {
          gain.gain.setTargetAtTime(computeGain(id, snap), now, 0.015);
        }
      }

      // Mix node: mute when we have enough stems loaded, otherwise audible
      if (mixGainRef.current) {
        const stemsLoaded = stemLoadedRef.current.size >= 4;
        mixGainRef.current.gain.setTargetAtTime(
          stemsLoaded ? 0 : 0.8,
          now,
          0.015
        );
      }
    },
    [computeGain]
  );

  /* ── Internal helpers ─────────────────────────────────────────── */
  const seekAll = useCallback((time: number) => {
    isSeekingRef.current = true;
    const mix = mixAudioRef.current;
    if (mix) {
      mix.currentTime = time;
    }
    for (const id of ALL_STEMS) {
      const a = stemAudioRefs.current[id];
      if (a && stemLoadedRef.current.has(id)) {
        a.currentTime = time;
      }
    }
    setCurrentTime(time);
    // Small delay to let elements settle before enabling drift correction
    setTimeout(() => { isSeekingRef.current = false; }, 100);
  }, []);

  const playAll = useCallback(() => {
    const ctx = audioCtxRef.current;
    if (ctx && ctx.state === "suspended") {
      ctx.resume();
    }

    const mix = mixAudioRef.current;
    if (mix) {
      mix.play().catch((err) => {
        console.warn("[AudioEngine] Mix play failed:", err);
      });
    }

    for (const id of ALL_STEMS) {
      const a = stemAudioRefs.current[id];
      if (a && stemLoadedRef.current.has(id)) {
        if (mix) a.currentTime = mix.currentTime;
        a.play().catch(() => {});
      }
    }
  }, []);

  const pauseAll = useCallback(() => {
    mixAudioRef.current?.pause();
    for (const id of ALL_STEMS) {
      stemAudioRefs.current[id]?.pause();
    }
  }, []);

  /* ── Init AudioContext + load all sources ──────────────────────── */
  useEffect(() => {
    const ctx = new AudioContext();
    audioCtxRef.current = ctx;

    // ─ Mix (fallback) ─
    const mixAudio = new Audio();
    mixAudio.crossOrigin = "anonymous";
    mixAudio.preload = "auto";
    mixAudio.src = getAudioUrl(projectId);
    mixAudioRef.current = mixAudio;

    const mixSource = ctx.createMediaElementSource(mixAudio);
    const mixGain = ctx.createGain();
    mixGain.gain.value = 0.8;
    mixSource.connect(mixGain).connect(ctx.destination);
    mixSourceRef.current = mixSource;
    mixGainRef.current = mixGain;

    // Duration from mix
    const onMeta = () => {
      if (mixAudio.duration && isFinite(mixAudio.duration)) {
        setDuration(mixAudio.duration);
        setIsReady(true);
      }
    };
    mixAudio.addEventListener("loadedmetadata", onMeta);
    mixAudio.addEventListener("durationchange", onMeta);

    // Error recovery
    mixAudio.addEventListener("error", () => {
      console.warn("[AudioEngine] Mix audio error, reloading in 1s");
      setTimeout(() => { mixAudio.load(); }, 1000);
    });

    // Stall recovery — if the mix stalls while playing, reload and resume
    mixAudio.addEventListener("stalled", () => {
      if (!mixAudio.paused && mixAudio.readyState < 3) {
        console.warn("[AudioEngine] Mix stalled, recovering…");
        const t = mixAudio.currentTime;
        mixAudio.load();
        const onReady = () => {
          mixAudio.currentTime = t;
          if (isPlayingRef.current) mixAudio.play().catch(() => {});
          mixAudio.removeEventListener("canplay", onReady);
        };
        mixAudio.addEventListener("canplay", onReady);
      }
    });

    // Ended
    mixAudio.addEventListener("ended", () => {
      setIsPlaying(false);
      isPlayingRef.current = false;
      for (const id of ALL_STEMS) {
        stemAudioRefs.current[id]?.pause();
      }
    });

    // ─ Stems ─
    for (const stemId of ALL_STEMS) {
      const audio = new Audio();
      audio.crossOrigin = "anonymous";
      audio.preload = "auto";
      audio.src = makeStemUrl(projectId, stemId);
      stemAudioRefs.current[stemId] = audio;

      const source = ctx.createMediaElementSource(audio);
      const gain = ctx.createGain();
      gain.gain.value = 0; // Will be set by applyGains once loaded
      source.connect(gain).connect(ctx.destination);
      stemSourceRefs.current[stemId] = source;
      stemGainRefs.current[stemId] = gain;

      audio.addEventListener("canplaythrough", () => {
        stemLoadedRef.current.add(stemId);
        // Once we have the 4 music stems, switch from mix fallback to stems
        if (stemLoadedRef.current.size >= 4) {
          applyGains(stemsRef.current);
        }
      });

      // Stem errors are non-fatal — we still have the mix
      audio.addEventListener("error", () => {
        console.warn(`[AudioEngine] Stem "${stemId}" failed to load`);
      });

      // Stall recovery per stem
      audio.addEventListener("stalled", () => {
        if (!audio.paused && audio.readyState < 3) {
          const t = audio.currentTime;
          audio.load();
          const onReady = () => {
            audio.currentTime = t;
            if (isPlayingRef.current) audio.play().catch(() => {});
            audio.removeEventListener("canplay", onReady);
          };
          audio.addEventListener("canplay", onReady);
        }
      });

      audio.load();
    }

    return () => {
      cancelAnimationFrame(rafRef.current);
      mixAudio.pause();
      mixAudio.removeAttribute("src");
      mixAudio.load();
      for (const id of ALL_STEMS) {
        const a = stemAudioRefs.current[id];
        if (a) { a.pause(); a.removeAttribute("src"); a.load(); }
      }
      ctx.close().catch(() => {});
      audioCtxRef.current = null;
      stemAudioRefs.current = {};
      stemSourceRefs.current = {};
      stemGainRefs.current = {};
      stemLoadedRef.current.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  /* ── Apply gains whenever stem state changes ──────────────────── */
  useEffect(() => {
    applyGains(stems);
  }, [stems, applyGains]);

  /* ── Animation frame for currentTime + loop enforcement ────────── */
  useEffect(() => {
    const tick = () => {
      const mix = mixAudioRef.current;
      if (mix) {
        const t = mix.currentTime;
        setCurrentTime(t);

        // Loop enforcement at frame rate (much more precise than timeupdate)
        const loop = loopRef.current;
        if (loop && t >= loop.end_time) {
          seekAll(loop.start_time);
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [seekAll]);

  /* ── Drift correction — sync stems to mix every 500ms ──────────── */
  useEffect(() => {
    if (!isPlaying) return;

    const interval = setInterval(() => {
      const mix = mixAudioRef.current;
      if (!mix || isSeekingRef.current) return;

      const master = mix.currentTime;
      for (const id of ALL_STEMS) {
        const a = stemAudioRefs.current[id];
        if (a && stemLoadedRef.current.has(id)) {
          if (Math.abs(a.currentTime - master) > 0.05) {
            a.currentTime = master;
          }
          // If mix is playing but stem stopped, restart it
          if (!mix.paused && a.paused && isPlayingRef.current) {
            a.currentTime = master;
            a.play().catch(() => {});
          }
        }
      }
    }, 500);

    return () => clearInterval(interval);
  }, [isPlaying]);

  /* ── Playback rate sync ───────────────────────────────────────── */
  useEffect(() => {
    if (mixAudioRef.current) mixAudioRef.current.playbackRate = playbackRate;
    for (const id of ALL_STEMS) {
      const a = stemAudioRefs.current[id];
      if (a) a.playbackRate = playbackRate;
    }
  }, [playbackRate]);

  /* ── Actions ──────────────────────────────────────────────────── */
  const play = useCallback(() => {
    const mix = mixAudioRef.current;
    if (!mix) return;

    // If looping and out of range, jump to loop start
    const loop = loopRef.current;
    if (loop && (mix.currentTime < loop.start_time || mix.currentTime >= loop.end_time)) {
      seekAll(loop.start_time);
    }

    playAll();
    setIsPlaying(true);
  }, [seekAll, playAll]);

  const pause = useCallback(() => {
    pauseAll();
    setIsPlaying(false);
  }, [pauseAll]);

  const toggle = useCallback(() => {
    isPlayingRef.current ? pause() : play();
  }, [pause, play]);

  const seek = useCallback((time: number) => {
    seekAll(time);
  }, [seekAll]);

  const seekFraction = useCallback(
    (fraction: number) => {
      seekAll(fraction * duration);
    },
    [duration, seekAll]
  );

  const toggleMute = useCallback((stemId: StemId) => {
    setStems((prev) => ({
      ...prev,
      [stemId]: { ...prev[stemId], muted: !prev[stemId].muted },
    }));
  }, []);

  const toggleSolo = useCallback((stemId: StemId) => {
    setStems((prev) => ({
      ...prev,
      [stemId]: { ...prev[stemId], solo: !prev[stemId].solo },
    }));
  }, []);

  const setStemVolume = useCallback((stemId: StemId, volume: number) => {
    setStems((prev) => ({
      ...prev,
      [stemId]: { ...prev[stemId], volume: Math.max(0, Math.min(1, volume)) },
    }));
  }, []);

  const setPlaybackRate = useCallback(
    (rate: number) => setPlaybackRateState(rate),
    []
  );

  /* ── Legacy compat: setPlaybackMode maps to solo ──────────────── */
  const setPlaybackMode = useCallback((mode: string) => {
    if (mode === "mix") {
      setStems((prev) => {
        const next = { ...prev };
        for (const id of ALL_STEMS) {
          next[id] = { ...next[id], solo: false, muted: false };
        }
        return next;
      });
    } else if (ALL_STEMS.includes(mode as StemId)) {
      setStems((prev) => {
        const next = { ...prev };
        for (const id of ALL_STEMS) {
          next[id] = { ...next[id], solo: id === mode };
        }
        return next;
      });
    }
  }, []);

  const playbackMode = (() => {
    const soloStem = ALL_STEMS.find((id) => stems[id].solo);
    return soloStem || "mix";
  })();

  /* ── Context value ────────────────────────────────────────────── */
  const value: AudioEngine = {
    isPlaying,
    currentTime,
    duration,
    stems,
    loopSection,
    playbackRate,
    isReady,
    playbackMode,
    play,
    pause,
    toggle,
    seek,
    seekFraction,
    toggleMute,
    toggleSolo,
    setStemVolume,
    setLoopSection,
    setPlaybackRate,
    setPlaybackMode,
  };

  return (
    <AudioEngineContext.Provider value={value}>
      {children}
    </AudioEngineContext.Provider>
  );
}
