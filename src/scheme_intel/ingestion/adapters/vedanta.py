"""
Vedanta / Cairn Oil & Gas Source Adapter (Stage 4B).
Parses Cairn Oil & Gas offshore disclosures, Ravva field updates, Cambay basin, and OALP acreage.
Filters out non-hydrocarbon mining, aluminum, zinc, and copper operations.
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


class VedantaAdapter(BaseSourceAdapter):
    """Source adapter for Vedanta / Cairn Oil & Gas Disclosures."""

    def __init__(
        self,
        source_id: str = "vedanta_corporate",
        scheme_id: str = "samudra_manthan",
        url: str = "https://www.vedantalimited.com/eng/investor-relations-stock-exchange-announcements.php",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="html",
            name="Vedanta / Cairn Oil & Gas Corporate Disclosures",
            url=url,
            timeout=timeout,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content or not raw_content.strip():
            return records

        soup = BeautifulSoup(raw_content, "html.parser")

        # 1. Parse table rows (from Stock Exchange Announcements)
        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                text = tr.get_text(" ", strip=True)
                if len(text) < 15 or "screen reader" in text.lower():
                    continue

                # Skip non-hydrocarbon operations
                if any(k in text.lower() for k in ["zinc", "aluminium", "aluminum", "iron ore", "copper smelter", "power plant"]):
                    continue

                a_tag = tr.find("a", href=True)
                link = urljoin(self.url, a_tag["href"]) if a_tag else self.url
                title = a_tag.get_text(" ", strip=True) if a_tag else text

                date_str = ""
                m_date = re.search(r"([A-Za-z]{3}\s+\d{1,2},\s*\d{4}|\d{1,2}[-/.][A-Za-z0-9]{2,3}[-/.]\d{4})", text)
                if m_date:
                    date_str = m_date.group(1)

                records.append(RawExtractedRecord(
                    title=title,
                    url=link,
                    content=text,
                    published_at=date_str or None,
                    raw_metadata={"company": "Vedanta Limited", "division": "Cairn Oil & Gas", "symbol": "VEDL.NS"},
                ))

        # 2. Parse general media release cards
        for a in soup.find_all("a", href=True):
            h = a["href"]
            t = a.get_text(" ", strip=True)
            if len(t) < 20:
                continue

            if ".pdf" in h.lower() or "press-release" in h.lower():
                if any(k in t.lower() for k in ["zinc", "aluminium", "iron ore", "copper"]):
                    continue
                records.append(RawExtractedRecord(
                    title=t,
                    url=urljoin(self.url, h),
                    content=t,
                    raw_metadata={"company": "Vedanta Limited", "division": "Cairn Oil & Gas", "symbol": "VEDL.NS"},
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
            for p in ["Ravva", "Cambay", "Barmer", "OALP", "Rajasthan"]:
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
                entities=["Vedanta Limited", "Cairn Oil & Gas"] + projects,
                companies=["Vedanta Limited"],
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
                    "company": "Vedanta Limited",
                    "confidence": conf,
                }],
            ))

        return events
