"""
ONGC (Oil and Natural Gas Corporation) Source Adapter (Stage 4B).
Parses offshore project disclosures, KG Basin / Mumbai High developments, drilling awards, and discoveries.
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


class ONGCAdapter(BaseSourceAdapter):
    """Source adapter for ONGC corporate and project disclosures."""

    def __init__(
        self,
        source_id: str = "ongc_corporate",
        scheme_id: str = "samudra_manthan",
        url: str = "https://ongcindia.com/web/eng/media/press-release",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="html",
            name="ONGC Corporate & Offshore Project Disclosures",
            url=url,
            timeout=timeout,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content or not raw_content.strip():
            return records

        soup = BeautifulSoup(raw_content, "html.parser")

        # 1. Parse table rows if structured
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                a_tag = row.find("a", href=True)
                if not a_tag:
                    continue
                title = a_tag.get_text(" ", strip=True)
                if len(title) < 10 or "screen reader" in title.lower() or "audio" in title.lower():
                    continue

                link = urljoin(self.url, a_tag["href"])
                row_text = row.get_text(" ", strip=True)

                date_str = ""
                d_match = re.search(r"(\d{1,2}[-/.][A-Za-z0-9]{2,3}[-/.](?:\d{4}|\d{2})|\d{1,2}\s+[A-Za-z]{3}\s+\d{4})", row_text)
                if d_match:
                    date_str = d_match.group(1)

                records.append(RawExtractedRecord(
                    title=title,
                    url=link,
                    content=row_text,
                    published_at=date_str or None,
                    raw_metadata={"company": "ONGC", "symbol": "ONGC.NS"},
                ))

        seen_urls = set()

        # 2. Parse press release cards / divs / list items
        elements = soup.find_all(lambda tag: tag.name in ["div", "li", "article"] and any(
            k in str(tag.get("class", "")).lower() for k in ["press", "release", "media", "card", "news-item"]
        ))
        for el in elements:
            # Skip container if it contains child press cards
            if el.find(lambda tag: tag.name in ["div", "li", "article"] and any(
                k in str(tag.get("class", "")).lower() for k in ["press", "release", "media", "card", "news-item"]
            )):
                continue

            a_tag = el.find("a", href=True)
            if not a_tag:
                continue
            title = a_tag.get_text(" ", strip=True)
            if len(title) < 10 or any(x in title.lower() for x in ["print media", "gallery", "brochure", "logo", "song"]):
                continue

            link = urljoin(self.url, a_tag["href"])
            if link in seen_urls:
                continue
            seen_urls.add(link)

            text = el.get_text(" ", strip=True)

            date_str = ""
            d_match = re.search(r"(\d{1,2}[-/.][A-Za-z0-9]{2,3}[-/.](?:\d{4}|\d{2})|\d{1,2}\s+[A-Za-z]{3}\s+\d{4})", text)
            if d_match:
                date_str = d_match.group(1)

            records.append(RawExtractedRecord(
                title=title,
                url=link,
                content=text,
                published_at=date_str or None,
                raw_metadata={"company": "ONGC", "symbol": "ONGC.NS"},
            ))

        # 3. Fallback: all links pointing to press releases or PDF documents
        if not records:
            for a in soup.find_all("a", href=True):
                h = a["href"]
                t = a.get_text(" ", strip=True)
                if len(t) > 15 and (".pdf" in h.lower() or "press-release" in h.lower()):
                    records.append(RawExtractedRecord(
                        title=t,
                        url=urljoin(self.url, h),
                        content=t,
                        raw_metadata={"company": "ONGC", "symbol": "ONGC.NS"},
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

            # Discover projects
            projects = []
            for p in ["KG-DWN-98/2", "KG Basin", "Mumbai High", "Bassein", "Neelam-Heera", "Cluster-2", "Daman Offshore"]:
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
                entities=["ONGC"] + projects,
                companies=["ONGC"],
                projects=projects,
                contracts=[],
                importance=importance,
                confidence=conf,
                url=rec.url,
                external_id=rec.external_id,
                relevance_reason=reason,
                water_depth=water_depth.value,
                evidence=[{
                    "source": self.name,
                    "url": rec.url,
                    "published_at": rec.published_at or now_utc,
                    "claim": rec.title,
                    "company": "ONGC",
                    "confidence": conf,
                }],
            ))

        return events
