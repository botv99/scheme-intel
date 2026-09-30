"""
Intelligence Snapshot Persistence & Fast In-Memory Store.
Provides atomic file writes, corruption guards, scheme-isolated snapshot namespaces,
and cached in-memory retrieval.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timezone

from .models import IntelligenceSnapshot, SnapshotHealthStatus
from ..logger import get_logger

logger = get_logger(__name__)

DEFAULT_SNAPSHOT_DIR = Path(__file__).resolve().parents[3] / "data" / "intelligence"
DEFAULT_SNAPSHOT_PATH = DEFAULT_SNAPSHOT_DIR / "latest.json"


class IntelligenceStore:
    """Manages serialization, atomic persistence, and cached loading of IntelligenceSnapshots per scheme."""

    _cached_snapshots: Dict[str, IntelligenceSnapshot] = {}
    _cached_mtimes: Dict[str, float] = {}

    def __init__(
        self,
        snapshot_path: Optional[Path | str] = None,
        scheme_id: Optional[str] = None,
    ):
        self.scheme_id = scheme_id.strip().lower() if scheme_id else None
        if snapshot_path:
            self.snapshot_path = Path(snapshot_path)
        elif self.scheme_id:
            self.snapshot_path = DEFAULT_SNAPSHOT_DIR / self.scheme_id / "latest.json"
        else:
            self.snapshot_path = DEFAULT_SNAPSHOT_PATH

        self.last_load_status: SnapshotHealthStatus = SnapshotHealthStatus.MISSING
        self.last_error: Optional[str] = None

    @property
    def _cached_snapshot(self) -> Optional[IntelligenceSnapshot]:
        key = str(self.snapshot_path.resolve())
        return self._cached_snapshots.get(key)

    @_cached_snapshot.setter
    def _cached_snapshot(self, val: Optional[IntelligenceSnapshot]) -> None:
        key = str(self.snapshot_path.resolve())
        if val is None:
            self._cached_snapshots.pop(key, None)
        else:
            self._cached_snapshots[key] = val

    @property
    def _cached_mtime(self) -> float:
        key = str(self.snapshot_path.resolve())
        return self._cached_mtimes.get(key, 0.0)

    @_cached_mtime.setter
    def _cached_mtime(self, val: float) -> None:
        key = str(self.snapshot_path.resolve())
        self._cached_mtimes[key] = val

    @classmethod
    def get_store_for_scheme(cls, scheme_id: str) -> "IntelligenceStore":
        """Factory creating a store targeted to a specific scheme's namespace."""
        return cls(scheme_id=scheme_id)

    def save(self, snapshot: IntelligenceSnapshot, also_save_to_root: bool = False) -> Path:
        """
        Atomically save snapshot to disk using a temporary file and rename.
        Validates the serialized content before replacement.
        Prevents readers from reading partially written JSON files.
        """
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.snapshot_path.with_suffix(f".tmp.{os.getpid()}")
        try:
            data = snapshot.model_dump_json(indent=2)
            # Integrity verification before writing to live path
            IntelligenceSnapshot.model_validate_json(data)
            temp_file.write_text(data, encoding="utf-8")
            os.replace(temp_file, self.snapshot_path)
            logger.info("Atomically saved intelligence snapshot to %s (snapshot_id=%s)", self.snapshot_path, snapshot.snapshot_id)

            key = str(self.snapshot_path.resolve())
            IntelligenceStore._cached_snapshots[key] = snapshot
            IntelligenceStore._cached_mtimes[key] = self.snapshot_path.stat().st_mtime
            self.last_load_status = SnapshotHealthStatus.READY
            self.last_error = None

            # Also maintain historical record in history/ subdirectory
            history_dir = self.snapshot_path.parent / "history"
            try:
                history_dir.mkdir(parents=True, exist_ok=True)
                history_file = history_dir / f"{snapshot.snapshot_id}.json"
                history_file.write_text(data, encoding="utf-8")
            except Exception as e:
                logger.debug("Failed writing history snapshot: %s", e)

            # Backward-compatibility: also update root data/intelligence/latest.json if requested
            if also_save_to_root and self.snapshot_path.resolve() != DEFAULT_SNAPSHOT_PATH.resolve():
                try:
                    DEFAULT_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
                    root_tmp = DEFAULT_SNAPSHOT_PATH.with_suffix(f".tmp.{os.getpid()}")
                    root_tmp.write_text(data, encoding="utf-8")
                    os.replace(root_tmp, DEFAULT_SNAPSHOT_PATH)
                    root_key = str(DEFAULT_SNAPSHOT_PATH.resolve())
                    IntelligenceStore._cached_snapshots[root_key] = snapshot
                    IntelligenceStore._cached_mtimes[root_key] = DEFAULT_SNAPSHOT_PATH.stat().st_mtime
                except Exception as e:
                    logger.debug("Failed saving compatibility snapshot to root: %s", e)

            return self.snapshot_path
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def load_with_status(
        self,
        force_reload: bool = False,
        max_age_hours: float = 26.0,
        freshness_threshold_hours: Optional[float] = None,
    ) -> tuple[SnapshotHealthStatus, Optional[IntelligenceSnapshot], str]:
        """
        Load snapshot from disk with health status classification:
        READY, STALE, MISSING, or INVALID.
        """
        if freshness_threshold_hours is not None:
            max_age_hours = freshness_threshold_hours

        # Fallback check: if scheme-specific snapshot is missing, check root snapshot for compatibility
        effective_path = self.snapshot_path
        if not effective_path.exists() and self.scheme_id and DEFAULT_SNAPSHOT_PATH.exists():
            effective_path = DEFAULT_SNAPSHOT_PATH

        if not effective_path.exists():
            self.last_load_status = SnapshotHealthStatus.MISSING
            self.last_error = "Snapshot file not found"
            logger.debug("No intelligence snapshot found at %s", self.snapshot_path)
            return SnapshotHealthStatus.MISSING, None, "Intelligence snapshot file not found."

        try:
            mtime = effective_path.stat().st_mtime
            key = str(effective_path.resolve())
            cached = IntelligenceStore._cached_snapshots.get(key)
            cached_mtime = IntelligenceStore._cached_mtimes.get(key, 0.0)

            if not force_reload and cached is not None and mtime == cached_mtime:
                status = cached.get_health_status(max_age_hours=max_age_hours)
                self.last_load_status = status
                self.last_error = None
                return status, cached, f"Loaded from cache (age: {cached.get_age_display()})"

            text = effective_path.read_text(encoding="utf-8")
            snapshot = IntelligenceSnapshot.model_validate_json(text)
            IntelligenceStore._cached_snapshots[key] = snapshot
            IntelligenceStore._cached_mtimes[key] = mtime
            self.last_load_status = snapshot.get_health_status(max_age_hours=max_age_hours)
            self.last_error = None
            return self.last_load_status, snapshot, f"Loaded from disk (age: {snapshot.get_age_display()})"

        except Exception as e:
            logger.error("Failed loading intelligence snapshot from %s: %s", effective_path, e)
            self.last_load_status = SnapshotHealthStatus.INVALID
            self.last_error = str(e)
            return SnapshotHealthStatus.INVALID, None, f"Invalid intelligence snapshot: {str(e)[:100]}"

    def load(self, force_reload: bool = False) -> Optional[IntelligenceSnapshot]:
        """Convenience method returning snapshot or None."""
        status, snapshot, _ = self.load_with_status(force_reload=force_reload)
        return snapshot if status in (SnapshotHealthStatus.READY, SnapshotHealthStatus.STALE) else None

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all in-memory snapshot caches (useful in tests)."""
        cls._cached_snapshots.clear()
        cls._cached_mtimes.clear()
