"""
Intelligence Snapshot Persistence & Fast In-Memory Store.
Provides atomic file writes, corruption guards, and cached in-memory retrieval.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from .models import IntelligenceSnapshot
from ..logger import get_logger

logger = get_logger(__name__)

DEFAULT_SNAPSHOT_DIR = Path(__file__).resolve().parents[3] / "data" / "intelligence"
DEFAULT_SNAPSHOT_PATH = DEFAULT_SNAPSHOT_DIR / "latest.json"


class IntelligenceStore:
    """Manages serialization, atomic persistence, and cached loading of IntelligenceSnapshots."""

    _cached_snapshot: Optional[IntelligenceSnapshot] = None
    _cached_mtime: float = 0.0

    def __init__(self, snapshot_path: Optional[Path | str] = None):
        self.snapshot_path = Path(snapshot_path) if snapshot_path else DEFAULT_SNAPSHOT_PATH

    def save(self, snapshot: IntelligenceSnapshot) -> Path:
        """
        Atomically save snapshot to disk using a temporary file and rename.
        Prevents readers from reading partially written JSON files.
        """
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.snapshot_path.with_suffix(f".tmp.{os.getpid()}")
        try:
            data = snapshot.model_dump_json(indent=2)
            temp_file.write_text(data, encoding="utf-8")
            os.replace(temp_file, self.snapshot_path)
            logger.info("Atomically saved intelligence snapshot to %s (snapshot_id=%s)", self.snapshot_path, snapshot.snapshot_id)
            IntelligenceStore._cached_snapshot = snapshot
            IntelligenceStore._cached_mtime = self.snapshot_path.stat().st_mtime
            return self.snapshot_path
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def load(self, force_reload: bool = False) -> Optional[IntelligenceSnapshot]:
        """
        Load snapshot from disk with in-memory caching based on file modification timestamp.
        """
        if not self.snapshot_path.exists():
            logger.debug("No intelligence snapshot found at %s", self.snapshot_path)
            return None

        try:
            mtime = self.snapshot_path.stat().st_mtime
            if not force_reload and IntelligenceStore._cached_snapshot is not None and mtime == IntelligenceStore._cached_mtime:
                return IntelligenceStore._cached_snapshot

            text = self.snapshot_path.read_text(encoding="utf-8")
            snapshot = IntelligenceSnapshot.model_validate_json(text)
            IntelligenceStore._cached_snapshot = snapshot
            IntelligenceStore._cached_mtime = mtime
            logger.debug("Loaded intelligence snapshot %s from %s", snapshot.snapshot_id, self.snapshot_path)
            return snapshot
        except Exception as e:
            logger.error("Failed to load intelligence snapshot from %s: %s", self.snapshot_path, e)
            return None

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached in-memory snapshot (primarily for testing)."""
        cls._cached_snapshot = None
        cls._cached_mtime = 0.0
