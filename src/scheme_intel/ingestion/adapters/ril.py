"""
Reliance Industries (RIL) Source Adapter (Stage 4B).
Parses KG-D6 deepwater gas developments, upstream production, and E&P investor disclosures.
Strictly filters out non-upstream consumer / retail / telecom noise.
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


class RILAdapter(BaseSourceAdapter):
    """Source adapter for Reliance Industries Upstream & Investor Disclosures."""

    def __init__(
        self,
        source_id: str = "ril_investor_updates",
        scheme_id: str = "samudra_manthan",
        url: str = "https://www.ril.com/news-media/press-releases",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="html",
            name="Reliance Industries Investor Disclosures",
            url=url,
            timeout=timeout,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content or not raw_content.strip():
            return records

        soup = BeautifulSoup(raw_content, "html.parser")

        # 1. Parse article cards, list items, or media release links
        for a in soup.find_all("a", href=True):
            h = a["href"]
            t = a.get_text(" ", strip=True)
            if len(t) < 15:
                continue

            # Look for press release or PDF document
            if ".pdf" in h.lower() or "press-release" in h.lower() or "media" in h.lower():
                # Filter out pure telecom/retail keywords from raw parsing
                if any(x in t.lower() for x in ["jio cinema", "trends fashion", "ajio", "retail stores", "5g rollout"]):
                    continue

                full_url = urljoin(self.url, h)

                # Look for date in text or URL (e.g. 14082026 or 2026-07)
                date_str = ""
                m_date = re.search(r"(\d{4}[-_]\d{2}(?:[-_]\d{2})?|\d{2}\s+[A-Za-z]{3}\s+\d{4})", f"{t} {h}")
                if m_date:
                    date_str = m_date.group(1)

                records.append(RawExtractedRecord(
                    title=t,
                    url=full_url,
                    content=t,
                    published_at=date_str or None,
                    raw_metadata={"company": "Reliance Industries", "symbol": "RELIANCE.NS"},
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
            for p in ["KG-D6", "MJ Field", "R-Cluster", "Satellite Cluster", "CBM"]:
                if p.lower() in f"{rec.title} {rec.content}".lower():
                    projects.append(p)

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
                entities=["Reliance Industries"] + projects,
                companies=["Reliance Industries"],
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
                    "company": "Reliance Industries",
                    "confidence": conf,
                }],
            ))

        return events
