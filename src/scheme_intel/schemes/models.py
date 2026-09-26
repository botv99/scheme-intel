"""
Scheme Models and Contracts for Multi-Scheme Architecture.
Defines metadata, sources, watchlists, and taxonomy for government policy schemes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SchemeSource(BaseModel):
    id: str
    name: str
    type: str  # rss, html, tender, filing
    url: str
    tier: int = 2
    enabled: bool = True
    poll_interval_hours: int = 4
    categories: List[str] = Field(default_factory=list)

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

    @property
    def scheme_id(self) -> str:
        return self.id

    @property
    def is_active(self) -> bool:
        return self.enabled

    def get_stock(self, symbol: str) -> Optional[SchemeStock]:
        for s in self.watchlist:
            if s.symbol.upper() == symbol.upper():
                return s
        return None
