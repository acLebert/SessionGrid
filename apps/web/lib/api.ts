/* ─── SessionGrid API Client ──────────────────────────────────────────── */

import type { Project, ProjectListItem, WaveformData } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }

  return res.json();
}

/* ─── Projects ────────────────────────────────────────────────────────── */

export async function listProjects(): Promise<ProjectListItem[]> {
  return request<ProjectListItem[]>("/api/projects");
}

export async function createProject(
  name: string,
  file: File,
  rightsConfirmed: boolean
): Promise<Project> {
  const formData = new FormData();
  formData.append("name", name);
  formData.append("rights_confirmed", String(rightsConfirmed));
  formData.append("file", file);

  return request<Project>("/api/projects", {
    method: "POST",
    body: formData,
  });
}

export async function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/api/projects/${projectId}`);
}

export async function getProjectStatus(
  projectId: string
): Promise<{ id: string; status: string; status_message: string | null }> {
  return request(`/api/projects/${projectId}/status`);
}

export async function triggerAnalysis(
  projectId: string
): Promise<{ task_id: string; project_id: string; status: string }> {
  return request(`/api/projects/${projectId}/analyze`, { method: "POST" });
}

export async function deleteProject(projectId: string): Promise<void> {
  await request(`/api/projects/${projectId}`, { method: "DELETE" });
}

/* ─── Files ───────────────────────────────────────────────────────────── */

export function getAudioUrl(projectId: string): string {
  return `${API_BASE}/api/projects/${projectId}/audio`;
}

export function getStemUrl(projectId: string, stemType: string): string {
  return `${API_BASE}/api/projects/${projectId}/stems/${stemType}`;
}

export function getClickUrl(projectId: string): string {
  return `${API_BASE}/api/projects/${projectId}/click`;
}

export async function getWaveformData(
  projectId: string,
  stem: string = "mix"
): Promise<WaveformData> {
  return request<WaveformData>(
    `/api/projects/${projectId}/waveform?stem=${stem}`
  );
}

/* ─── Sections ────────────────────────────────────────────────────────── */

export async function updateSection(
  projectId: string,
  sectionId: string,
  data: Record<string, unknown>
): Promise<void> {
  await request(`/api/projects/${projectId}/sections/${sectionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/* ─── Export ──────────────────────────────────────────────────────────── */

export function getExportJsonUrl(projectId: string): string {
  return `${API_BASE}/api/projects/${projectId}/export/json`;
}

/* ─── Rhythm Debug (DEBUG ONLY) ───────────────────────────────────────── */

export interface RhythmDebugData {
  unique_meters: string[];
  confidence_min: number | null;
  confidence_max: number | null;
  modulation_count: number;
  polyrhythm_count: number;
  ambiguous_window_count: number;
  total_windows: number;
  sample_windows: {
    start_time: number;
    end_time: number;
    beat_count: number | null;
    grouping: number[] | null;
    confidence: number | null;
  }[];
}

export async function getRhythmDebug(
  projectId: string
): Promise<RhythmDebugData> {
  return request<RhythmDebugData>(`/api/projects/${projectId}/rhythm-debug`);
}
