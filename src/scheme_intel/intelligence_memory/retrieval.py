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
            p = Path(data_dir)
            if (p / "intelligence" / "latest.json").exists():
                self.store = IntelligenceStore(snapshot_path=p / "intelligence" / "latest.json")
            else:
                self.store = IntelligenceStore(snapshot_path=p / "latest.json")
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

    def get_status(self, force_reload: bool = False, scheme_id: Optional[str] = None) -> Tuple[SnapshotHealthStatus, Optional[IntelligenceSnapshot], str]:
        """Determine health status: READY, STALE, MISSING, or INVALID."""
        if self.store and self.store.snapshot_path != DEFAULT_SNAPSHOT_PATH:
            return self.store.load_with_status(
                force_reload=force_reload,
                max_age_hours=self.freshness_threshold_hours,
            )

        if scheme_id:
            store = IntelligenceStore.get_store_for_scheme(scheme_id)
            status, snap, msg = store.load_with_status(
                force_reload=force_reload,
                max_age_hours=self.freshness_threshold_hours,
            )
            if status != SnapshotHealthStatus.MISSING or not self.store:
                return status, snap, msg

        return self.store.load_with_status(
            force_reload=force_reload,
            max_age_hours=self.freshness_threshold_hours,
        )

    def get_snapshot(self, scheme_id: Optional[str] = None) -> Optional[IntelligenceSnapshot]:
        """
        Fetch current snapshot from in-memory cache or disk.
        If scheme_id is provided, loads the scheme-specific snapshot.
        """
        if self.store and self.store.snapshot_path != DEFAULT_SNAPSHOT_PATH:
            snap = self.store.load()
            if snap:
                return snap

        if scheme_id:
            store = IntelligenceStore.get_store_for_scheme(scheme_id)
            snapshot = store.load()
            if snapshot:
                return snapshot

        snapshot = self.store.load()
        if not snapshot and self.auto_build_if_missing:
            logger.info("auto_build_if_missing enabled: Building initial snapshot...")
            try:
                self.builder.build_and_save(scheme_id=scheme_id)
                snapshot = self.store.load()
            except Exception as e:
                logger.error("Failed building initial snapshot: %s", e)
        return snapshot

    def get_company(self, symbol_or_short: str, scheme_id: Optional[str] = None) -> Optional[CompanyIntelligence]:
        """Fetch company intelligence by ticker, short symbol, or name within optional scheme scope."""
        snapshot = self.get_snapshot(scheme_id=scheme_id)
        if not snapshot:
            return None

        # Verify scheme membership if scheme_id is specified
        if scheme_id:
            from ..schemes.registry import SchemeRegistry
            scfg = SchemeRegistry.get(scheme_id)
            if scfg and not scfg.is_company_in_universe(symbol_or_short):
                # Hard isolation: company is NOT in this scheme's universe!
                return None

        key = symbol_or_short.strip().upper()
        # 1. Exact dictionary key match
        if key in snapshot.companies:
            comp = snapshot.companies[key]
            if not scheme_id or (comp.scheme_id and comp.scheme_id.lower() == scheme_id.lower()):
                return comp

        # 2. Sans-suffix match (e.g. TRUALT.NS -> TRUALT)
        base_sym = key.split(".")[0]
        if base_sym in snapshot.companies:
            comp = snapshot.companies[base_sym]
            if not scheme_id or (comp.scheme_id and comp.scheme_id.lower() == scheme_id.lower()):
                return comp

        # 3. Add-suffix match (e.g. TRUALT -> TRUALT.NS or TRUALT.BO)
        if f"{base_sym}.NS" in snapshot.companies:
            comp = snapshot.companies[f"{base_sym}.NS"]
            if not scheme_id or (comp.scheme_id and comp.scheme_id.lower() == scheme_id.lower()):
                return comp
        if f"{base_sym}.BO" in snapshot.companies:
            comp = snapshot.companies[f"{base_sym}.BO"]
            if not scheme_id or (comp.scheme_id and comp.scheme_id.lower() == scheme_id.lower()):
                return comp

        # 4. Search across all stored company records
        for comp in snapshot.companies.values():
            if scheme_id and comp.scheme_id and comp.scheme_id.lower() != scheme_id.lower():
                continue
            if comp.short_symbol.upper() == base_sym or comp.symbol.upper() == key:
                return comp
            if comp.name.upper() == key or comp.name.upper().startswith(base_sym):
                return comp

        return None

    def get_watchlist(self, scheme_id: Optional[str] = None) -> List[CompanyIntelligence]:
        """Fetch all companies for the active scheme watchlist."""
        snapshot = self.get_snapshot(scheme_id=scheme_id)
        if not snapshot:
            return []
        if not scheme_id:
            return list(snapshot.companies.values())
        norm_sid = scheme_id.strip().lower()
        return [c for c in snapshot.companies.values() if (c.scheme_id or "").lower() == norm_sid]

    def get_scheme(self, scheme_id: str) -> Optional[SchemeIntelligence]:
        """Fetch scheme intelligence by scheme ID."""
        snapshot = self.get_snapshot(scheme_id=scheme_id)
        if not snapshot:
            return None
        return snapshot.schemes.get(scheme_id.strip().lower())

    def list_schemes(self) -> List[SchemeIntelligence]:
        """List all active schemes in snapshot."""
        snapshot = self.get_snapshot()
        if snapshot and snapshot.schemes:
            return list(snapshot.schemes.values())
        from ..schemes.registry import SchemeRegistry
        from .models import SchemeIntelligence
        return [
            SchemeIntelligence(
                scheme_id=s.id,
                name=s.name,
                description=s.description,
                ministry=", ".join(s.ministries) if s.ministries else "",
                status="ACTIVE" if s.enabled else "INACTIVE",
                total_watchlist_stocks=len(s.watchlist),
                important_sources=[src.name for src in s.sources[:3]],
            )
            for s in SchemeRegistry.list_schemes()
        ]

    def get_qualified_setups(self, scheme_id: Optional[str] = None) -> List[CompanyIntelligence]:
        """Fetch list of companies currently in QUALIFIED_SETUP status for scheme."""
        snapshot = self.get_snapshot(scheme_id=scheme_id)
        if not snapshot:
            return []
        results = []
        seen = set()
        norm_sid = scheme_id.strip().lower() if scheme_id else None
        for sym in snapshot.qualified_setups:
            comp = snapshot.companies.get(sym)
            if comp and comp.symbol not in seen:
                if norm_sid and comp.scheme_id and comp.scheme_id.lower() != norm_sid:
                    continue
                seen.add(comp.symbol)
                results.append(comp)
        return results

    def get_waiting_setups(self, scheme_id: Optional[str] = None) -> List[CompanyIntelligence]:
        """Fetch list of companies currently in WAIT status for scheme."""
        snapshot = self.get_snapshot(scheme_id=scheme_id)
        if not snapshot:
            return []
        results = []
        seen = set()
        norm_sid = scheme_id.strip().lower() if scheme_id else None
        for sym in snapshot.waiting_setups:
            comp = snapshot.companies.get(sym)
            if comp and comp.symbol not in seen:
                if norm_sid and comp.scheme_id and comp.scheme_id.lower() != norm_sid:
                    continue
                seen.add(comp.symbol)
                results.append(comp)
        return results

    def get_performance(self, scheme_id: Optional[str] = None) -> PerformanceIntelligence:
        """Fetch forward performance intelligence."""
        snapshot = self.get_snapshot(scheme_id=scheme_id)
        if not snapshot:
            return PerformanceIntelligence()
        return snapshot.performance

    def get_benchmark(self, scheme_id: Optional[str] = None) -> BenchmarkIntelligence:
        """Fetch Nifty 50 benchmark comparative intelligence."""
        snapshot = self.get_snapshot(scheme_id=scheme_id)
        if not snapshot:
            return BenchmarkIntelligence()
        return snapshot.benchmark


# Alias for backward and architectural compatibility
IntelligenceRetrieval = FastIntelligenceRetriever

