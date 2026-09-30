"""
PMO (Prime Minister's Office) Source Adapter (Stage 4B).
Parses Cabinet decisions, national strategic energy announcements, and PMO press releases.
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


class PMOAdapter(BaseSourceAdapter):
    """Source adapter for Prime Minister's Office Press Releases."""

    def __init__(
        self,
        source_id: str = "pmo_releases",
        scheme_id: str = "samudra_manthan",
        url: str = "https://www.pmindia.gov.in/en/news-updates/",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="html",
            name="Prime Minister's Office Press Releases",
            url=url,
            timeout=timeout,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content or not raw_content.strip():
            return records

        soup = BeautifulSoup(raw_content, "html.parser")

        # PMO uses div.news-description containing title link, date, and description
        items = soup.find_all("div", class_="news-description")
        for div in items:
            a_tag = div.find("a", href=True)
            if not a_tag:
                continue

            title = a_tag.get_text(" ", strip=True)
            link = urljoin(self.url, a_tag["href"])
            full_text = div.get_text(" ", strip=True)

            # Extract date format like "30 Sep, 2026"
            date_str = ""
            d_match = re.search(r"(\d{1,2}\s+[A-Za-z]{3},\s*\d{4})", full_text)
            if d_match:
                date_str = d_match.group(1)

            records.append(RawExtractedRecord(
                title=title,
                url=link,
                content=full_text,
                summary=full_text[:300],
                published_at=date_str or None,
            ))

        # Fallback: article tags or generic news-item
        if not records:
            for art in soup.find_all(["article", "li"], class_=lambda c: c and "news" in str(c).lower()):
                a_tag = art.find("a", href=True)
                if not a_tag:
                    continue
                title = a_tag.get_text(" ", strip=True)
                link = urljoin(self.url, a_tag["href"])
                records.append(RawExtractedRecord(
                    title=title,
                    url=link,
                    content=art.get_text(" ", strip=True),
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

            events.append(NormalizedSchemeEvent(
                event_id=evt_id,
                scheme_id=self.scheme_id,
                source_id=self.source_id,
                event_type="CABINET_DIRECTIVE" if "cabinet" in rec.title.lower() else "STRATEGIC_ANNOUNCEMENT",
                title=rec.title,
                content=rec.content or rec.title,
                summary=rec.summary or rec.title[:200],
                published_at=rec.published_at or now_utc,
                retrieved_at=now_utc,
                entities=["PMO"],
                companies=[],
                projects=[],
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
                    "confidence": conf,
                }],
            ))

        return events
