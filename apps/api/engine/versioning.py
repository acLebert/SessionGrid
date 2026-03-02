"""
Analysis Versioning — Engine version tracking, artifact caching,
and backward compatibility.

Design:
  - Every analysis run is tagged with engine_version (semver).
  - Intermediate artifacts (onset arrays, feature matrices) are cached
    as .npz files in the project's storage directory.
  - When re-running analysis on old projects:
    1. Check if engine_version has changed.
    2. Determine which stages are affected by the version bump.
    3. Only re-run affected stages; reuse cached artifacts for others.
  - Cached artifacts include a version tag so stale caches are invalidated.

Version format: MAJOR.MINOR.PATCH
  - MAJOR: breaking change (full re-analysis required)
  - MINOR: new stage or improved algorithm (re-run affected stages)
  - PATCH: bug fix (no re-analysis needed unless explicitly requested)

Stage versioning:
  Each stage has its own sub-version (e.g., separation_stage=1.0, signal_stage=2.0).
  A stage is re-run only if its sub-version has changed.
"""

import logging
import json
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np

from engine import ENGINE_VERSION

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage versions — bump when algorithm changes
# ---------------------------------------------------------------------------

STAGE_VERSIONS = {
    "separation": "2.0.0",   # stereo extraction + spectral SNR
    "signal": "2.0.0",       # sample-level transient refinement
    "temporal": "2.0.0",     # tempo octave correction
    "groove": "2.0.0",       # new stage
    "hits": "2.0.0",         # new stage
    "export": "2.0.0",       # new stage
}

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class AnalysisManifest:
    """Tracks what was computed and at which version."""
    engine_version: str = ENGINE_VERSION
    stage_versions: dict = field(default_factory=lambda: dict(STAGE_VERSIONS))
    stages_completed: list[str] = field(default_factory=list)
    artifact_paths: dict = field(default_factory=dict)
    config_snapshot: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "engine_version": self.engine_version,
            "stage_versions": self.stage_versions,
            "stages_completed": self.stages_completed,
            "artifact_paths": self.artifact_paths,
            "config_snapshot": self.config_snapshot,
        }

    def is_stage_stale(self, stage_name: str, current_versions: dict = None) -> bool:
        """Check if a stage needs re-running."""
        if current_versions is None:
            current_versions = STAGE_VERSIONS

        if stage_name not in self.stages_completed:
            return True

        cached_version = self.stage_versions.get(stage_name, "0.0.0")
        current_version = current_versions.get(stage_name, "0.0.0")
        return cached_version != current_version


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_manifest(project_dir: str) -> AnalysisManifest:
    """Load analysis manifest from project directory, or create new one."""
    manifest_path = Path(project_dir) / "analysis_manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                data = json.load(f)
            manifest = AnalysisManifest(
                engine_version=data.get("engine_version", "0.0.0"),
                stage_versions=data.get("stage_versions", {}),
                stages_completed=data.get("stages_completed", []),
                artifact_paths=data.get("artifact_paths", {}),
                config_snapshot=data.get("config_snapshot", {}),
            )
            logger.info(f"Loaded manifest: engine v{manifest.engine_version}")
            return manifest
        except Exception as e:
            logger.warning(f"Failed to load manifest: {e}")

    return AnalysisManifest()


def save_manifest(project_dir: str, manifest: AnalysisManifest):
    """Save analysis manifest."""
    manifest_path = Path(project_dir) / "analysis_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(manifest.to_dict(), f, indent=2)
    logger.info(f"Saved manifest: engine v{manifest.engine_version}")


def get_stale_stages(manifest: AnalysisManifest) -> list[str]:
    """Determine which stages need re-running."""
    stale = []
    ordered_stages = ["separation", "signal", "temporal", "groove", "hits", "export"]

    for stage in ordered_stages:
        if manifest.is_stage_stale(stage):
            stale.append(stage)

    # If any stage is stale, all downstream stages must also re-run
    if stale:
        first_stale_idx = ordered_stages.index(stale[0])
        stale = ordered_stages[first_stale_idx:]

    return stale


def mark_stage_complete(manifest: AnalysisManifest, stage_name: str):
    """Mark a stage as completed with the current version."""
    if stage_name not in manifest.stages_completed:
        manifest.stages_completed.append(stage_name)
    manifest.stage_versions[stage_name] = STAGE_VERSIONS.get(stage_name, "0.0.0")


# ---------------------------------------------------------------------------
# Artifact caching
# ---------------------------------------------------------------------------


def cache_artifact(
    project_dir: str,
    stage_name: str,
    artifact_name: str,
    data: np.ndarray | dict | list,
    manifest: AnalysisManifest,
):
    """
    Cache an intermediate artifact to disk.

    Supports numpy arrays (.npz) and JSON-serializable data (.json).
    """
    cache_dir = Path(project_dir) / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(data, np.ndarray):
        path = cache_dir / f"{stage_name}_{artifact_name}.npz"
        np.savez_compressed(str(path), data=data,
                           version=STAGE_VERSIONS.get(stage_name, "0.0.0"))
    else:
        path = cache_dir / f"{stage_name}_{artifact_name}.json"
        with open(path, "w") as f:
            json.dump({
                "data": data,
                "version": STAGE_VERSIONS.get(stage_name, "0.0.0"),
            }, f)

    manifest.artifact_paths[f"{stage_name}.{artifact_name}"] = str(path)


def load_cached_artifact(
    project_dir: str,
    stage_name: str,
    artifact_name: str,
    expected_version: str = None,
):
    """
    Load a cached artifact if it exists and is at the expected version.

    Returns None if cache miss or version mismatch.
    """
    if expected_version is None:
        expected_version = STAGE_VERSIONS.get(stage_name, "0.0.0")

    cache_dir = Path(project_dir) / "cache"

    # Try .npz
    npz_path = cache_dir / f"{stage_name}_{artifact_name}.npz"
    if npz_path.exists():
        try:
            loaded = np.load(str(npz_path), allow_pickle=True)
            version = str(loaded.get("version", "0.0.0"))
            if version == expected_version:
                return loaded["data"]
            else:
                logger.info(f"Cache stale: {npz_path.name} v{version} vs v{expected_version}")
        except Exception:
            pass

    # Try .json
    json_path = cache_dir / f"{stage_name}_{artifact_name}.json"
    if json_path.exists():
        try:
            with open(json_path) as f:
                loaded = json.load(f)
            version = loaded.get("version", "0.0.0")
            if version == expected_version:
                return loaded["data"]
        except Exception:
            pass

    return None
