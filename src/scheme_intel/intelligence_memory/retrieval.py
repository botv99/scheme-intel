"""
Fast In-Memory Intelligence Retrieval Layer.
Provides sub-second querying over prebuilt IntelligenceSnapshots without web calls or strategy recalculation.
"""
from __future__ import annotations

from typing import List, Optional
from pathlib import Path

from .models import (
    IntelligenceSnapshot,
    CompanyIntelligence,
    SchemeIntelligence,
    PerformanceIntelligence,
    BenchmarkIntelligence,
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
        auto_build_if_missing: bool = True,
    ):
        self.store = store or IntelligenceStore()
        self.builder = builder or IntelligenceSnapshotBuilder(store=self.store)
        self.auto_build_if_missing = auto_build_if_missing

    def get_snapshot(self) -> Optional[IntelligenceSnapshot]:
        """Fetch current snapshot from in-memory cache or disk. Auto-builds once if missing."""
        snapshot = self.store.load()
        if not snapshot and self.auto_build_if_missing:
            logger.info("No prebuilt intelligence snapshot found. Building initial snapshot...")
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
