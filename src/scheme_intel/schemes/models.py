"""
Scheme Models and Contracts for Multi-Scheme Architecture.
Defines metadata, sources, watchlists, relationship classifications, and taxonomy for government policy schemes.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BeneficiaryRelationshipType(str, Enum):
    """Classification of how a company is exposed to or benefits from a government scheme."""
    DIRECT_OPERATOR = "DIRECT_OPERATOR"
    BLOCK_HOLDER = "BLOCK_HOLDER"
    JV_PARTNER = "JV_PARTNER"
    DEEPWATER_EXPLORER = "DEEPWATER_EXPLORER"
    DRILLING_CONTRACTOR = "DRILLING_CONTRACTOR"
    SEISMIC_PROVIDER = "SEISMIC_PROVIDER"
    OFFSHORE_ENGINEERING = "OFFSHORE_ENGINEERING"
    SUBSEA = "SUBSEA"
    OFFSHORE_INFRASTRUCTURE = "OFFSHORE_INFRASTRUCTURE"
    EQUIPMENT_SUPPLIER = "EQUIPMENT_SUPPLIER"
    MARINE_LOGISTICS = "MARINE_LOGISTICS"
    OILFIELD_SERVICES = "OILFIELD_SERVICES"
    EPC = "EPC"
    SECOND_ORDER_BENEFICIARY = "SECOND_ORDER_BENEFICIARY"
    TECHNOLOGY_PROVIDER = "TECHNOLOGY_PROVIDER"
    UTILITY_OFFTAKER = "UTILITY_OFFTAKER"
    BENEFICIARY = "BENEFICIARY"


class CompanyWatchlistStatus(str, Enum):
    """Status tier for companies evaluated for scheme inclusion."""
    CORE = "CORE"
    CANDIDATE = "CANDIDATE"
    WATCH = "WATCH"
    EXCLUDED = "EXCLUDED"


class CompanySchemeRelationship(BaseModel):
    """Structured evidence-backed relationship between a company and a scheme."""
    company: str
    symbol: Optional[str] = None
    scheme_id: str
    relationship_type: str = BeneficiaryRelationshipType.DIRECT_OPERATOR.value
    evidence: str = ""
    source: str = ""
    source_date: Optional[str] = None
    confidence: float = 1.0
    status: str = CompanyWatchlistStatus.CORE.value

    @property
    def company_symbol(self) -> Optional[str]:
        return self.symbol


class SchemeSource(BaseModel):
    id: str
    name: str
    type: str  # rss, html, tender, filing
    url: str
    tier: int = 2
    enabled: bool = True
    poll_interval_hours: int = 4
    categories: List[str] = Field(default_factory=list)
    trust_level: int = 1
    refresh_frequency: str = "4h"
    parser: Optional[str] = None

    @property
    def source_type(self) -> str:
        return self.type


class SchemeStock(BaseModel):
    name: str
    symbol: str
    aliases: List[str] = Field(default_factory=list)
    screener_id: Optional[str] = None
    sectors: List[str] = Field(default_factory=list)
    rationale: str = ""
    relationship_type: str = BeneficiaryRelationshipType.BENEFICIARY.value
    status: str = CompanyWatchlistStatus.CORE.value
    confidence: float = 1.0
    evidence: str = ""
    source: str = ""
    last_verified: Optional[str] = None


class SchemeConfig(BaseModel):
    id: str
    name: str
    enabled: bool = True
    description: str = ""
    ministries: List[str] = Field(default_factory=list)
    sources: List[SchemeSource] = Field(default_factory=list)
    watchlist: List[SchemeStock] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    industries: List[str] = Field(default_factory=list)
    company_mappings: Dict[str, List[str]] = Field(default_factory=dict)
    event_taxonomy: List[str] = Field(default_factory=list)
    structured_knowledge: Dict[str, Any] = Field(default_factory=dict)
    rules: Dict[str, Any] = Field(default_factory=dict)

    @property
    def scheme_id(self) -> str:
        return self.id

    @property
    def is_active(self) -> bool:
        return self.enabled

    def get_stock(self, symbol_or_name: str) -> Optional[SchemeStock]:
        clean = (symbol_or_name or "").strip().upper()
        if not clean:
            return None
        clean_short = clean.split(".")[0]
        for s in self.watchlist:
            sym_upper = s.symbol.upper()
            sym_short = sym_upper.split(".")[0]
            if sym_upper == clean or sym_short == clean_short or s.name.upper() == clean:
                return s
            if any(alias.upper() == clean for alias in s.aliases):
                return s
        return None

    def is_company_in_universe(self, symbol_or_name: str) -> bool:
        """Verify whether a company is an authorized member of this scheme's research universe."""
        return self.get_stock(symbol_or_name) is not None
