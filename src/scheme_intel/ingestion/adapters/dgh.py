"""
DGH (Directorate General of Hydrocarbons) Source Adapter (Stage 4B).
Parses OALP bidding rounds, offshore exploration notices, discoveries, and regulatory circulars.
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


class DGHAdapter(BaseSourceAdapter):
    """Source adapter for Directorate General of Hydrocarbons (DGH)."""

    def __init__(
        self,
        source_id: str = "dgh_portal",
        scheme_id: str = "samudra_manthan",
        url: str = "https://dghindia.gov.in",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="html",
            name="Directorate General of Hydrocarbons (DGH)",
            url=url,
            timeout=timeout,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        """
        Parse DGH notices, circulars, OALP bidding updates, and discovery tables.
        Supports HTML table rows, announcement lists, and notice cards.
        """
        records: List[RawExtractedRecord] = []
        if not raw_content or not raw_content.strip():
            return records

        soup = BeautifulSoup(raw_content, "html.parser")

        # 1. Parse structured tables (e.g. OALP rounds, tender tables, notice boards)
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue

                # Extract link and title
                a_tag = row.find("a", href=True)
                title = ""
                link = ""
                if a_tag:
                    title = a_tag.get_text(" ", strip=True)
                    link = urljoin(self.url, a_tag["href"])
                else:
                    title = " ".join(c.get_text(" ", strip=True) for c in cells[:3])
                    link = self.url

                if not title or len(title) < 5:
                    continue

                # Date extraction
                date_str = ""
                for cell in cells:
                    txt = cell.get_text(strip=True)
                    d_match = re.search(r"\b(\d{1,2}[-/.][A-Za-z0-9]{2,3}[-/.](?:\d{4}|\d{2}))\b", txt)
                    if d_match:
                        date_str = d_match.group(1)
                        break

                # Document ID or Notice ID
                doc_id = ""
                m_doc = re.search(r"\b(DGH/[A-Za-z0-9/_.-]+|OALP-[IVXLCDM]+|NOTICE[-_/\d]+)\b", title, re.IGNORECASE)
                if m_doc:
                    doc_id = m_doc.group(1)

                records.append(RawExtractedRecord(
                    title=title,
                    url=link,
                    content=row.get_text(" ", strip=True),
                    published_at=date_str or None,
                    external_id=doc_id or None,
                    raw_metadata={"source_category": "dgh_table"},
                ))

        # 2. Parse notice / news list cards or list elements
        containers = soup.find_all(["div", "li"], class_=lambda c: c and any(k in str(c).lower() for k in ["notice", "news", "announcement", "circular", "update", "item"]))
        for container in containers:
            a_tag = container.find("a", href=True)
            if not a_tag:
                continue
            title = a_tag.get_text(" ", strip=True)
            if not title or len(title) < 10:
                continue

            link = urljoin(self.url, a_tag["href"])
            text = container.get_text(" ", strip=True)

            date_str = ""
            d_match = re.search(r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{1,2}[-/.](?:\d{2}|[A-Za-z]{3})[-/.]\d{4})\b", text)
            if d_match:
                date_str = d_match.group(1)

            records.append(RawExtractedRecord(
                title=title,
                url=link,
                content=text,
                published_at=date_str or None,
                raw_metadata={"source_category": "dgh_card"},
            ))

        return records

    def normalize(self, records: List[RawExtractedRecord]) -> List[NormalizedSchemeEvent]:
        """Normalize extracted DGH records into scheme events with relevance and importance."""
        now_utc = datetime.now(timezone.utc).isoformat()
        events: List[NormalizedSchemeEvent] = []

        for rec in records:
            is_rel, cat, reason, conf = SamudraRelevanceFilter.evaluate(rec.title, rec.content)
            if not is_rel:
                continue

            importance = SamudraRelevanceFilter.determine_importance(rec.title, rec.content, cat)

            # Extract companies (ONGC, OIL, RIL, Vedanta)
            comp_list = []
            for c_name in ["ONGC", "Oil India", "Reliance", "Vedanta", "Cairn", "BP", "TotalEnergies"]:
                if re.search(rf"\b{re.escape(c_name)}\b", f"{rec.title} {rec.content}", re.IGNORECASE):
                    comp_list.append(c_name)

            # Extract blocks / projects (e.g. KG-DWN-98/2, OALP-IX)
            projects = []
            block_matches = re.findall(r"\b([A-Z]{2,3}-[A-Z0-9/_-]+)\b", f"{rec.title} {rec.content}")
            for b in block_matches:
                if any(x in b for x in ["DWN", "OSN", "OSHP", "OALP", "D6"]):
                    projects.append(b)

            water_depth = classify_water_depth_strict(f"{rec.title} {rec.content}")

            evt_id = self.generate_event_id(rec.external_id, rec.title, rec.published_at)

            events.append(NormalizedSchemeEvent(
                event_id=evt_id,
                scheme_id=self.scheme_id,
                source_id=self.source_id,
                event_type="REGULATORY_DIRECTIVE" if "circular" in rec.title.lower() or "policy" in rec.title.lower() else "EXPLORATION_UPDATE",
                title=rec.title,
                content=rec.content or rec.title,
                summary=rec.summary or rec.title[:200],
                published_at=rec.published_at or now_utc,
                retrieved_at=now_utc,
                entities=comp_list + projects,
                companies=comp_list,
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
                    "confidence": conf,
                }],
            ))

        return events
