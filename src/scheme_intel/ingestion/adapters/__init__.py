"""
Scheme-Intel Source Adapters Registry (Stage 4B).
Provides registry and lookup for scheme source adapters.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Type

from .base import BaseSourceAdapter, FetchResult, RawExtractedRecord, SourceHealthRecord
from .dgh import DGHAdapter
from .pib import PIBMoPNGAdapter, PIBNationalEnergyAdapter
from .pmo import PMOAdapter
from .cppp import CPPPAdapter
from .ongc import ONGCAdapter
from .oil_india import OilIndiaAdapter
from .ril import RILAdapter
from .vedanta import VedantaAdapter
from .exchanges import NSEFilingAdapter, BSEAnnouncementAdapter
from .news import (
    ETEnergyWorldAdapter,
    ReutersEnergyAdapter,
    BusinessStandardEnergyAdapter,
    MintEnergyAdapter,
    OffshoreTechnologyAdapter,
    LegacyDGHArchiveAdapter,
)

SAMUDRA_ADAPTER_MAP: Dict[str, Type[BaseSourceAdapter]] = {
    "dgh_portal": DGHAdapter,
    "pib_mopng_samudra": PIBMoPNGAdapter,
    "pib_national_energy": PIBNationalEnergyAdapter,
    "pmo_releases": PMOAdapter,
    "cppp_hydrocarbons": CPPPAdapter,
    "ongc_corporate": ONGCAdapter,
    "oil_india_corporate": OilIndiaAdapter,
    "ril_investor_updates": RILAdapter,
    "vedanta_corporate": VedantaAdapter,
    "nse_energy_filings": NSEFilingAdapter,
    "bse_energy_announcements": BSEAnnouncementAdapter,
    # Redundant / Alternative news and specialist sources
    "et_energyworld": ETEnergyWorldAdapter,
    "reuters_energy": ReutersEnergyAdapter,
    "business_standard_energy": BusinessStandardEnergyAdapter,
    "mint_energy": MintEnergyAdapter,
    "offshore_technology": OffshoreTechnologyAdapter,
    "legacy_dgh_archive": LegacyDGHArchiveAdapter,
}


class AdapterRegistry:
    """Registry for instantiating source adapters by scheme and source ID."""

    @classmethod
    def get_adapter(cls, scheme_id: str, source_id: str) -> Optional[BaseSourceAdapter]:
        norm_scheme = (scheme_id or "").strip().lower()
        if norm_scheme == "samudra_manthan":
            adapter_cls = SAMUDRA_ADAPTER_MAP.get(source_id)
            if adapter_cls:
                return adapter_cls(source_id=source_id, scheme_id=norm_scheme)
        return None

    @classmethod
    def list_supported_sources(cls, scheme_id: str) -> List[str]:
        norm_scheme = (scheme_id or "").strip().lower()
        if norm_scheme == "samudra_manthan":
            return list(SAMUDRA_ADAPTER_MAP.keys())
        return []


__all__ = [
    "BaseSourceAdapter",
    "SourceHealthRecord",
    "FetchResult",
    "RawExtractedRecord",
    "DGHAdapter",
    "PIBMoPNGAdapter",
    "PIBNationalEnergyAdapter",
    "PMOAdapter",
    "CPPPAdapter",
    "ONGCAdapter",
    "OilIndiaAdapter",
    "RILAdapter",
    "VedantaAdapter",
    "NSEFilingAdapter",
    "BSEAnnouncementAdapter",
    "ETEnergyWorldAdapter",
    "ReutersEnergyAdapter",
    "BusinessStandardEnergyAdapter",
    "MintEnergyAdapter",
    "OffshoreTechnologyAdapter",
    "LegacyDGHArchiveAdapter",
    "AdapterRegistry",
    "SAMUDRA_ADAPTER_MAP",
]
