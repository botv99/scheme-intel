"""
Fast In-Memory Intelligence Retrieval Layer.
Provides sub-second querying over prebuilt IntelligenceSnapshots without web calls or strategy recalculation.
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple
from pathlib import Path

from .models import (
    IntelligenceSnapshot,
    CompanyIntelligence,
    SchemeIntelligence,
    PerformanceIntelligence,
    BenchmarkIntelligence,
    SnapshotHealthStatus,
)
from .store import IntelligenceStore, DEFAULT_SNAPSHOT_PATH
from .builder import IntelligenceSnapshotBuilder
from ..logger import get_logger

logger = get_logger(__name__)


class FastIntelligenceRetriever:
    """Retrieval interface over prebuilt intelligence memory."""

    def __init__(
        self,
        store: Optional[IntelligenceStore] = None,
        builder: Optional[IntelligenceSnapshotBuilder] = None,
        auto_build_if_missing: bool = False,
        freshness_threshold_hours: Optional[float] = None,
        data_dir: Optional[str | Path] = None,
    ):
        if store is None and data_dir is not None:
            self.store = IntelligenceStore(snapshot_path=Path(data_dir) / "latest.json")
        else:
            self.store = store or IntelligenceStore()
        self.builder = builder or IntelligenceSnapshotBuilder(store=self.store)
        self.auto_build_if_missing = auto_build_if_missing
        if freshness_threshold_hours is not None:
            self.freshness_threshold_hours = freshness_threshold_hours
        else:
            try:
                self.freshness_threshold_hours = float(os.getenv("INTELLIGENCE_FRESHNESS_HOURS", "26.0"))
            except Exception:
                self.freshness_threshold_hours = 26.0

    def get_status(self, force_reload: bool = False) -> Tuple[SnapshotHealthStatus, Optional[IntelligenceSnapshot], str]:
        """Determine health status: READY, STALE, MISSING, or INVALID."""
        return self.store.load_with_status(
            force_reload=force_reload,
            max_age_hours=self.freshness_threshold_hours,
        )

    def get_snapshot(self) -> Optional[IntelligenceSnapshot]:
        """
        Fetch current snapshot from in-memory cache or disk.
        Does NOT build on missing unless auto_build_if_missing is explicitly enabled.
        """
        snapshot = self.store.load()
        if not snapshot and self.auto_build_if_missing:
            logger.info("auto_build_if_missing enabled: Building initial snapshot...")
            try:
                self.builder.build_and_save()
                snapshot = self.store.load()
            except Exception as e:
                logger.error("Failed building initial snapshot: %s", e)
        return snapshot

    def get_company(self, symbol_or_short: str) -> Optional[CompanyIntelligence]:
        """Fetch company intelligence by ticker or short symbol."""
        snapshot = self.get_snapshot()
        if not snapshot:
            return None
        key = symbol_or_short.strip().upper()
        return snapshot.companies.get(key)

    def get_scheme(self, scheme_id: str) -> Optional[SchemeIntelligence]:
        """Fetch scheme intelligence by scheme ID."""
        snapshot = self.get_snapshot()
        if not snapshot:
            return None
        return snapshot.schemes.get(scheme_id.strip().lower())

    def list_schemes(self) -> List[SchemeIntelligence]:
        """List all active schemes in snapshot."""
        snapshot = self.get_snapshot()
        if not snapshot:
            return []
        return list(snapshot.schemes.values())

    def get_qualified_setups(self) -> List[CompanyIntelligence]:
        """Fetch list of companies currently in QUALIFIED_SETUP status."""
        snapshot = self.get_snapshot()
        if not snapshot:
            return []
        results = []
        seen = set()
        for sym in snapshot.qualified_setups:
            comp = snapshot.companies.get(sym)
            if comp and comp.symbol not in seen:
                seen.add(comp.symbol)
                results.append(comp)
        return results

    def get_waiting_setups(self) -> List[CompanyIntelligence]:
        """Fetch list of companies currently in WAIT status."""
        snapshot = self.get_snapshot()
        if not snapshot:
            return []
        results = []
        seen = set()
        for sym in snapshot.waiting_setups:
            comp = snapshot.companies.get(sym)
            if comp and comp.symbol not in seen:
                seen.add(comp.symbol)
                results.append(comp)
        return results

    def get_performance(self) -> PerformanceIntelligence:
        """Fetch forward performance intelligence."""
        snapshot = self.get_snapshot()
        if not snapshot:
            return PerformanceIntelligence()
        return snapshot.performance

    def get_benchmark(self) -> BenchmarkIntelligence:
        """Fetch Nifty 50 benchmark comparative intelligence."""
        snapshot = self.get_snapshot()
        if not snapshot:
            return BenchmarkIntelligence()
        return snapshot.benchmark


# Alias for backward and architectural compatibility
IntelligenceRetrieval = FastIntelligenceRetriever

