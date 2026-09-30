"""
Oil India Source Adapter (Stage 4B).
Parses offshore acreage, Andaman deepwater exploration, and OALP awards disclosures.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from .base import BaseSourceAdapter, RawExtractedRecord
from ..models import NormalizedSchemeEvent
from ...schemes.samudra_manthan.relevance import SamudraRelevanceFilter
from ...schemes.samudra_manthan.entities import classify_water_depth_strict
from ...logger import get_logger

logger = get_logger(__name__)


class OilIndiaAdapter(BaseSourceAdapter):
    """Source adapter for Oil India Corporate Press Releases."""

    def __init__(
        self,
        source_id: str = "oil_india_corporate",
        scheme_id: str = "samudra_manthan",
        url: str = "https://www.oil-india.com/press-release",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="html",
            name="Oil India Corporate Press Releases",
            url=url,
            timeout=timeout,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content or not raw_content.strip():
            return records

        soup = BeautifulSoup(raw_content, "html.parser")

        # 1. Parse table rows or document lists
        for a in soup.find_all("a", href=True):
            h = a["href"]
            t = a.get_text(" ", strip=True)
            if len(t) < 10:
                continue

            if any(k in h.lower() for k in ["press_release", "press-release", "document", ".pdf"]):
                # Skip irrelevant documents (CSR, pension, vendor list)
                if any(x in t.lower() for x in ["csr policy", "pensioner", "neft mandate", "debarred vendor"]):
                    continue

                full_url = urljoin(self.url, h)

                # Look for date in text or URL (e.g. 2026-08)
                date_str = ""
                m_date = re.search(r"\b(202[0-9][-/_]\d{2}(?:[-/_]\d{2})?)\b", h)
                if m_date:
                    date_str = m_date.group(1).replace("_", "-").replace("/", "-")

                parent = a.find_parent(["li", "div", "article", "tr"])
                full_text = parent.get_text(" ", strip=True) if parent else t

                records.append(RawExtractedRecord(
                    title=t,
                    url=full_url,
                    content=full_text,
                    published_at=date_str or None,
                    raw_metadata={"company": "Oil India Limited", "symbol": "OIL.NS"},
                ))

        return records

    def normalize(self, records: List[RawExtractedRecord]) -> List[NormalizedSchemeEvent]:
        now_utc = datetime.now(timezone.utc).isoformat()
        events: List[NormalizedSchemeEvent] = []

        for rec in records:
            is_rel, cat, reason, conf = SamudraRelevanceFilter.evaluate(rec.title, rec.content)
            if not is_rel:
                continue

            importance = SamudraRelevanceFilter.determine_importance(rec.title, rec.content, cat)
            water_depth = classify_water_depth_strict(f"{rec.title} {rec.content}")
            evt_id = self.generate_event_id(rec.external_id, rec.title, rec.published_at)

            projects = []
            for p in ["Andaman", "Mahanadi", "OALP", "Krishna-Godavari"]:
                if p.lower() in f"{rec.title} {rec.content}".lower():
                    projects.append(p)

            companies = ["Oil India Limited"]
            for cand in ["Alphageo", "Larsen & Toubro", "L&T", "Deep Industries", "Asian Energy"]:
                if cand.lower() in f"{rec.title} {rec.content}".lower():
                    companies.append(cand)

            events.append(NormalizedSchemeEvent(
                event_id=evt_id,
                scheme_id=self.scheme_id,
                source_id=self.source_id,
                event_type="OPERATOR_DISCLOSURE",
                title=rec.title,
                content=rec.content or rec.title,
                summary=rec.summary or rec.title[:200],
                published_at=rec.published_at or now_utc,
                retrieved_at=now_utc,
                entities=companies + projects,
                companies=companies,
                projects=projects,
                contracts=[],
                importance=importance,
                confidence=conf,
                url=rec.url,
                relevance_reason=reason,
                water_depth=water_depth.value,
                evidence=[{
                    "source": self.name,
                    "url": rec.url,
                    "published_at": rec.published_at or now_utc,
                    "claim": rec.title,
                    "company": "Oil India Limited",
                    "confidence": conf,
                }],
            ))

        return events
