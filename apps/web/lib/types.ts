/* ─── SessionGrid API Types ────────────────────────────────────────────── */

export type ConfidenceLevel = "high" | "medium" | "low";

export type ProjectStatus =
  | "uploading"
  | "extracting"
  | "separating"
  | "analyzing"
  | "generating_click"
  | "complete"
  | "failed";

export interface Section {
  id: string;
  order_index: number;
  name: string;
  start_time: number;
  end_time: number;
  bars: number | null;
  bpm: number | null;
  meter: string | null;
  confidence: ConfidenceLevel | null;
  notes: string | null;
}

export interface Stem {
  id: string;
  stem_type: string;
  file_path: string;
  quality_score: number | null;
}

export interface AnalysisResult {
  id: string;
  pipeline_version: string;
  overall_bpm: number | null;
  bpm_stable: boolean | null;
  time_signature: string | null;
  confidence_stem: ConfidenceLevel | null;
  confidence_beat: ConfidenceLevel | null;
  confidence_downbeat: ConfidenceLevel | null;
  confidence_meter: ConfidenceLevel | null;
  confidence_sections: ConfidenceLevel | null;
  beats_json: number[] | null;
  downbeats_json: number[] | null;
  tempo_curve_json: { time: number; bpm: number }[] | null;
  analysis_duration_ms: number | null;
}

export interface ClickTrack {
  id: string;
  file_path: string;
  mode: string;
}

export interface Project {
  id: string;
  name: string;
  status: ProjectStatus;
  status_message: string | null;
  created_at: string;
  updated_at: string;
  original_filename: string;
  duration_seconds: number | null;
  file_hash_sha256: string | null;
  analysis: AnalysisResult | null;
  stems: Stem[];
  sections: Section[];
  click_track: ClickTrack | null;
}

export interface ProjectListItem {
  id: string;
  name: string;
  status: ProjectStatus;
  created_at: string;
  original_filename: string;
  duration_seconds: number | null;
}

export interface WaveformData {
  peaks: { min: number; max: number; rms: number }[];
  duration: number;
  sample_rate: number;
  points_per_second: number;
  total_points: number;
}

/* ─── Playback Mode ───────────────────────────────────────────────────── */

export type PlaybackMode = "mix" | "drums" | "click" | "click_drums" | "vocals" | "bass" | "other";

export const PLAYBACK_MODES: { key: PlaybackMode; label: string }[] = [
  { key: "mix", label: "Original Mix" },
  { key: "vocals", label: "Vocals" },
  { key: "drums", label: "Drums" },
  { key: "bass", label: "Bass" },
  { key: "other", label: "Other" },
  { key: "click", label: "Click Only" },
  { key: "click_drums", label: "Click + Drums" },
];

/* ─── Processing Steps ────────────────────────────────────────────────── */

export const PROCESSING_STEPS: Record<ProjectStatus, { label: string; progress: number }> = {
  uploading: { label: "Uploading file...", progress: 5 },
  extracting: { label: "Extracting audio...", progress: 15 },
  separating: { label: "Separating stems...", progress: 40 },
  analyzing: { label: "Analyzing beats & sections...", progress: 65 },
  generating_click: { label: "Generating click track...", progress: 85 },
  complete: { label: "Analysis complete", progress: 100 },
  failed: { label: "Analysis failed", progress: 0 },
};
