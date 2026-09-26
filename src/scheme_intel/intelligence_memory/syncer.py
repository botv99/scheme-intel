"""
Snapshot Synchronization Client (Stage 3).
Periodically pulls the latest validated IntelligenceSnapshot committed by GitHub Actions
(03-memory-refresh.yml) from the central repository into the local service memory store.

Ensures running Docker containers and long-running bot instances stay synchronized
with daily pipeline cycles without requiring container rebuilds or restarts.
"""
from __future__ import annotations

import os
import time
from typing import Optional
from pathlib import Path
import requests

from .models import IntelligenceSnapshot, SnapshotHealthStatus
from .store import IntelligenceStore, DEFAULT_SNAPSHOT_PATH
from ..logger import get_logger

logger = get_logger(__name__)

DEFAULT_REPO = "botv99/scheme-intel"
DEFAULT_BRANCH = "main"


class SnapshotSyncer:
    """Synchronizes intelligence snapshot from GitHub repository into local store."""

    def __init__(
        self,
        store: Optional[IntelligenceStore] = None,
        sync_url: Optional[str] = None,
        repo: Optional[str] = None,
        branch: Optional[str] = None,
        interval_seconds: float = 300.0,
        enabled: Optional[bool] = None,
    ):
        self.store = store or IntelligenceStore()
        effective_repo = repo or os.getenv("GITHUB_REPOSITORY") or os.getenv("SCHEME_INTEL_REPO", DEFAULT_REPO)
        effective_branch = branch or os.getenv("SNAPSHOT_SYNC_BRANCH", DEFAULT_BRANCH)

        self.sync_url = (
            sync_url
            or os.getenv("SNAPSHOT_SYNC_URL")
            or f"https://raw.githubusercontent.com/{effective_repo}/{effective_branch}/data/intelligence/latest.json"
        )

        env_interval = os.getenv("SNAPSHOT_SYNC_INTERVAL")
        if env_interval and env_interval.replace(".", "", 1).isdigit():
            self.interval_seconds = float(env_interval)
        else:
            self.interval_seconds = interval_seconds

        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = os.getenv("SNAPSHOT_SYNC_ENABLED", "true").lower() in ("true", "1", "yes")

        self.is_running = False
        self.last_sync_time: float = 0.0
        self.last_sync_status: str = "NEVER"
        self.last_error: Optional[str] = None

    def sync_once(self) -> bool:
        """
        Perform a single non-blocking check against the remote repository snapshot.
        Atomically updates the local store only if the remote snapshot is valid and newer.
        """
        if not self.enabled:
            logger.debug("[SNAPSHOT_SYNC] Sync is disabled by configuration.")
            return False

        logger.debug("[SNAPSHOT_SYNC] Checking for updated snapshot from: %s", self.sync_url)
        headers = {
            "User-Agent": "Scheme-Intel-Sync/1.0",
        }
        gh_token = os.getenv("GITHUB_TOKEN")
        if gh_token:
            headers["Authorization"] = f"Bearer {gh_token}"

        try:
            resp = requests.get(self.sync_url, headers=headers, timeout=15)
            if resp.status_code != 200:
                self.last_sync_status = f"HTTP_{resp.status_code}"
                logger.debug(
                    "[SNAPSHOT_SYNC] Remote repository returned HTTP %d for snapshot: %s",
                    resp.status_code,
                    self.sync_url,
                )
                return False

            remote_snapshot = IntelligenceSnapshot.model_validate_json(resp.text)
            self.last_sync_time = time.time()

            # Compare against current local snapshot
            local_status, local_snap, _ = self.store.load_with_status()
            should_update = False

            if local_status in (SnapshotHealthStatus.MISSING, SnapshotHealthStatus.INVALID) or not local_snap:
                should_update = True
                logger.info("[SNAPSHOT_SYNC] Local snapshot is %s; adopting remote snapshot.", local_status.value)
            elif remote_snapshot.snapshot_id != local_snap.snapshot_id:
                # Compare timestamps
                if remote_snapshot.generated_at > local_snap.generated_at:
                    should_update = True
                    logger.info(
                        "[SNAPSHOT_SYNC] Remote snapshot is newer (%s > %s). Updating local store.",
                        remote_snapshot.snapshot_id,
                        local_snap.snapshot_id,
                    )

            if should_update:
                self.store.save(remote_snapshot)
                self.last_sync_status = "UPDATED"
                self.last_error = None
                logger.info(
                    "[SNAPSHOT_SYNC] Successfully synchronized new snapshot: %s (age: %s)",
                    remote_snapshot.snapshot_id,
                    remote_snapshot.get_age_display(),
                )
                return True
            else:
                self.last_sync_status = "UP_TO_DATE"
                self.last_error = None
                return False

        except Exception as e:
            self.last_sync_status = "FAILED"
            self.last_error = str(e)
            logger.warning("[SNAPSHOT_SYNC] Snapshot sync check failed: %s", e)
            return False

    def run_forever(self, interval_seconds: Optional[float] = None) -> None:
        """Continuously sync snapshot at interval until stop() is called."""
        self.is_running = True
        poll_interval = interval_seconds or self.interval_seconds
        logger.info("[SNAPSHOT_SYNC] Background syncer loop started (interval=%.1fs)", poll_interval)

        # Immediate sync attempt on startup
        self.sync_once()

        while self.is_running:
            # Sleep in 1-second chunks for responsive stopping
            for _ in range(int(poll_interval)):
                if not self.is_running:
                    break
                time.sleep(1.0)

            if self.is_running:
                self.sync_once()

        logger.info("[SNAPSHOT_SYNC] Background syncer loop stopped.")

    def stop(self) -> None:
        """Signal syncer loop to terminate gracefully."""
        self.is_running = False
