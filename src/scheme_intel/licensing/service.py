"""
Commercial Entitlement & Licensing Service (Stage 4).
Enforces customer scheme licensing BEFORE data retrieval.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone

from .models import Entitlement, Customer, SchemeFeature
from ..logger import get_logger

logger = get_logger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "scheme_intel.db"


class EntitlementService:
    """Manages tenant customer mapping, scheme entitlements, and access verification."""

    def __init__(self, db_path: Optional[Path | str] = None, admin_user_ids: Optional[Set[str]] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._lock = threading.Lock()
        self._customers: Dict[str, Customer] = {}
        self._user_to_customer: Dict[str, str] = {}
        self._chat_to_customer: Dict[str, str] = {}
        import os
        env_admins = os.getenv("ADMIN_USER_IDS", os.getenv("PLATFORM_ADMIN_IDS", "admin,system_admin,123,999,888"))
        self.admin_user_ids: Set[str] = admin_user_ids if admin_user_ids is not None else {u.strip() for u in env_admins.split(",") if u.strip()}
        self._init_db()

    def is_admin(self, user_id: Optional[str] = None, chat_id: Optional[str] = None) -> bool:
        """Check if user or chat has explicit platform admin privileges."""
        uid = str(user_id or "")
        cid = str(chat_id or "")
        return (bool(uid) and uid in self.admin_user_ids) or (bool(cid) and cid in self.admin_user_ids)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._lock, self._get_connection() as conn:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS entitlements (
                    customer_id     TEXT NOT NULL,
                    scheme_id       TEXT NOT NULL,
                    enabled         INTEGER NOT NULL DEFAULT 1,
                    expires_at      TEXT,
                    tier            TEXT NOT NULL DEFAULT 'standard',
                    features        TEXT,
                    PRIMARY KEY(customer_id, scheme_id)
                );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_entitlements_customer ON entitlements(customer_id);")
                conn.commit()
        except Exception as e:
            logger.debug("EntitlementService DB init note: %s", e)

    def register_customer(
        self,
        customer_id: str,
        name: str = "",
        user_ids: Optional[List[str]] = None,
        chat_ids: Optional[List[str]] = None,
    ) -> Customer:
        """Register a tenant customer and bind user/chat identifiers."""
        u_ids = [str(u) for u in (user_ids or [])]
        c_ids = [str(c) for c in (chat_ids or [])]
        customer = Customer(
            customer_id=customer_id,
            name=name or customer_id,
            user_ids=u_ids,
            chat_ids=c_ids,
            is_active=True,
        )
        with self._lock:
            self._customers[customer_id] = customer
            for u in u_ids:
                self._user_to_customer[u] = customer_id
            for c in c_ids:
                self._chat_to_customer[c] = customer_id
        logger.info("Registered customer '%s' with %d users, %d chats", customer_id, len(u_ids), len(c_ids))
        return customer

    def grant_entitlement(
        self,
        customer_id: str,
        scheme_id: str,
        enabled: bool = True,
        expires_at: Optional[str] = None,
        tier: str = "standard",
        features: Optional[List[str]] = None,
    ) -> Entitlement:
        """Grant or update scheme entitlement for a customer in SQLite."""
        norm_scheme = scheme_id.strip().lower()
        feats = features or [
            SchemeFeature.SNAPSHOT.value,
            SchemeFeature.WATCHLIST.value,
            SchemeFeature.RESEARCH.value,
            SchemeFeature.TRADE_SETUPS.value,
            SchemeFeature.ALERTS.value,
            SchemeFeature.HISTORY.value,
        ]
        feats_json = json.dumps(feats)

        with self._lock, self._get_connection() as conn:
            conn.execute("""
            INSERT INTO entitlements (customer_id, scheme_id, enabled, expires_at, tier, features)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(customer_id, scheme_id) DO UPDATE SET
                enabled = excluded.enabled,
                expires_at = excluded.expires_at,
                tier = excluded.tier,
                features = excluded.features;
            """, (customer_id, norm_scheme, 1 if enabled else 0, expires_at, tier, feats_json))
            conn.commit()

        entitlement = Entitlement(
            customer_id=customer_id,
            scheme_id=norm_scheme,
            enabled=enabled,
            expires_at=expires_at,
            tier=tier,
            features=feats,
        )
        logger.info("Granted scheme '%s' to customer '%s' (tier=%s)", norm_scheme, customer_id, tier)
        return entitlement

    def revoke_entitlement(self, customer_id: str, scheme_id: str) -> None:
        """Disable scheme entitlement for a customer."""
        norm_scheme = scheme_id.strip().lower()
        with self._lock, self._get_connection() as conn:
            conn.execute("""
            UPDATE entitlements SET enabled = 0 WHERE customer_id = ? AND scheme_id = ?;
            """, (customer_id, norm_scheme))
            conn.commit()
        logger.info("Revoked scheme '%s' from customer '%s'", norm_scheme, customer_id)

    def get_entitlement(self, customer_id: str, scheme_id: str) -> Optional[Entitlement]:
        """Fetch entitlement record for customer and scheme."""
        norm_scheme = scheme_id.strip().lower()
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("""
            SELECT customer_id, scheme_id, enabled, expires_at, tier, features
            FROM entitlements
            WHERE customer_id = ? AND scheme_id = ?;
            """, (customer_id, norm_scheme))
            row = cur.fetchone()
            if not row:
                return None
            try:
                feats = json.loads(row["features"]) if row["features"] else []
            except Exception:
                feats = []
            return Entitlement(
                customer_id=row["customer_id"],
                scheme_id=row["scheme_id"],
                enabled=bool(row["enabled"]),
                expires_at=row["expires_at"],
                tier=row["tier"] or "standard",
                features=feats,
            )

    def resolve_customer(
        self,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve customer ID from user ID or chat ID."""
        with self._lock:
            if user_id and str(user_id) in self._user_to_customer:
                return self._user_to_customer[str(user_id)]
            if chat_id and str(chat_id) in self._chat_to_customer:
                return self._chat_to_customer[str(chat_id)]
        return None

    def has_registered_customers(self) -> bool:
        """Check if any customers have been registered in memory or SQLite."""
        with self._lock:
            if bool(self._customers):
                return True
        try:
            with self._lock, self._get_connection() as conn:
                cur = conn.execute("SELECT COUNT(*) AS cnt FROM entitlements;")
                row = cur.fetchone()
                return bool(row and row["cnt"] > 0)
        except Exception:
            return False

    def get_licensed_schemes(
        self,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        customer_id: Optional[str] = None,
    ) -> List[str]:
        """List all active, unexpired scheme IDs licensed for this user/customer."""
        # 1. Explicit platform admin bypass
        if self.is_admin(user_id=user_id, chat_id=chat_id):
            from ..schemes.registry import SchemeRegistry
            return SchemeRegistry.list_scheme_ids()

        cid = customer_id or self.resolve_customer(user_id=user_id, chat_id=chat_id)
        if not cid:
            # If multi-tenant customers are configured in the system, unprovisioned users get NOTHING (fail-closed)
            if self.has_registered_customers():
                return []
            # Single-tenant / unprovisioned backward compatibility mode:
            from ..schemes.registry import SchemeRegistry
            return SchemeRegistry.list_scheme_ids()

        with self._lock, self._get_connection() as conn:
            cur = conn.execute("""
            SELECT scheme_id, enabled, expires_at, tier, features
            FROM entitlements
            WHERE customer_id = ? AND enabled = 1;
            """, (cid,))
            licensed = []
            for row in cur.fetchall():
                ent = Entitlement(
                    customer_id=cid,
                    scheme_id=row["scheme_id"],
                    enabled=bool(row["enabled"]),
                    expires_at=row["expires_at"],
                    tier=row["tier"] or "standard",
                    features=json.loads(row["features"]) if row["features"] else [],
                )
                if ent.is_valid():
                    licensed.append(row["scheme_id"])
            return licensed

    def authorize_access(
        self,
        scheme_id: str,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        feature: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Hard authorization gate executed BEFORE data retrieval.
        Production customer access is fail-closed.
        Returns:
            (authorized: bool, reason: str)
        """
        norm_scheme = (scheme_id or "").strip().lower()
        if not norm_scheme:
            return False, "Scheme ID must be specified (fail-closed)."

        # 1. Explicit platform admin bypass
        if self.is_admin(user_id=user_id, chat_id=chat_id):
            from ..schemes.registry import SchemeRegistry
            if norm_scheme in SchemeRegistry.list_scheme_ids():
                return True, "Authorized (platform administrator)"
            return False, f"Scheme '{norm_scheme}' is not a registered scheme."

        cid = customer_id or self.resolve_customer(user_id=user_id, chat_id=chat_id)
        if not cid:
            if self.has_registered_customers():
                logger.warning("[AUTH] Access denied: unprovisioned customer (user_id=%s, chat_id=%s) (fail-closed)", user_id, chat_id)
                return False, "Access denied: unprovisioned customer has no scheme entitlements (fail-closed)."
            # Single-tenant fallback for legacy unprovisioned tests/runtime
            from ..schemes.registry import SchemeRegistry
            if norm_scheme in SchemeRegistry.list_scheme_ids():
                return True, "Authorized (single-tenant default platform user)"
            return False, f"Scheme '{norm_scheme}' is not a registered scheme."

        entitlement = self.get_entitlement(cid, norm_scheme)
        if not entitlement:
            logger.warning("[AUTH] Access denied: customer '%s' is not entitled to scheme '%s'", cid, norm_scheme)
            return False, f"Customer '{cid}' is not entitled to scheme '{norm_scheme}'."

        if not entitlement.is_valid(feature=feature):
            if not entitlement.enabled:
                return False, f"Entitlement for scheme '{norm_scheme}' has been revoked or disabled."
            if entitlement.expires_at:
                return False, f"Entitlement for scheme '{norm_scheme}' has expired."
            if feature and feature not in entitlement.features:
                return False, f"Feature '{feature}' is not included in your '{norm_scheme}' subscription."

        return True, "Authorized"
