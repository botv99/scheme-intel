"""
Commercial Licensing and Entitlement Subsystem for Scheme-Intel (Stage 4).
Provides scheme-wise entitlements, tenant isolation, and feature-level access gates.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class SchemeFeature(str, Enum):
    SNAPSHOT = "snapshot"
    WATCHLIST = "watchlist"
    RESEARCH = "research"
    TRADE_SETUPS = "trade_setups"
    ALERTS = "alerts"
    ADVANCED_RESEARCH = "advanced_research"
    HISTORY = "history"


class Entitlement(BaseModel):
    """Customer license record for a specific scheme."""
    customer_id: str
    scheme_id: str
    enabled: bool = True
    expires_at: Optional[str] = None
    tier: str = "standard"  # standard, premium, enterprise
    features: List[str] = Field(
        default_factory=lambda: [
            SchemeFeature.SNAPSHOT.value,
            SchemeFeature.WATCHLIST.value,
            SchemeFeature.RESEARCH.value,
            SchemeFeature.TRADE_SETUPS.value,
            SchemeFeature.ALERTS.value,
            SchemeFeature.HISTORY.value,
        ]
    )

    def is_valid(self, feature: Optional[str] = None) -> bool:
        """Check if entitlement is active, unexpired, and covers requested feature."""
        if not self.enabled:
            return False
        if self.expires_at:
            try:
                exp_dt = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > exp_dt:
                    return False
            except Exception:
                pass
        if feature:
            return feature in self.features
        return True


class Customer(BaseModel):
    """Customer / Tenant entity mapped to Telegram users and chats."""
    customer_id: str
    name: str
    user_ids: List[str] = Field(default_factory=list)
    chat_ids: List[str] = Field(default_factory=list)
    is_active: bool = True
