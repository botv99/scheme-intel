"""
CPPP (Central Public Procurement Portal) Tender Adapter (Stage 4B).
Parses government tender notices, drilling/rig charters, seismic surveys, and subsea awards.
Extracts structured tender fields (tender_id, issuer, scope, closing_date, estimated_value).
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


class CPPPAdapter(BaseSourceAdapter):
    """Source adapter for CPPP Hydrocarbon & Offshore Tenders."""

    def __init__(
        self,
        source_id: str = "cppp_hydrocarbons",
        scheme_id: str = "samudra_manthan",
        url: str = "https://eprocure.gov.in/cppp/latestactivetendersnew",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="tender",
            name="Government eProcurement - Hydrocarbon & Offshore Tenders",
            url=url,
            timeout=timeout,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content or not raw_content.strip():
            return records

        soup = BeautifulSoup(raw_content, "html.parser")

        # CPPP tables contain: [Sl.No, e-Published Date, Bid Submission Closing Date, Tender Opening Date, Title/Ref.No./Tender Id]
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 4:
                    continue

                full_row_text = " ".join(c.get_text(" ", strip=True) for c in cells)

                # Skip header row
                if "e-Published Date" in full_row_text or "Sl.No" in full_row_text:
                    continue

                # Title and tender ID extraction
                a_tag = row.find("a", href=True)
                title = ""
                link = ""
                if a_tag:
                    title = a_tag.get_text(" ", strip=True)
                    link = urljoin(self.url, a_tag["href"])
                else:
                    title = cells[-1].get_text(" ", strip=True)
                    link = self.url

                if not title or len(title) < 5:
                    continue

                # Extract dates
                pub_date = cells[1].get_text(strip=True) if len(cells) > 1 else None
                close_date = cells[2].get_text(strip=True) if len(cells) > 2 else None

                # Extract tender ID and ref number from cells, link, or row text
                tender_id = None
                for c in cells:
                    c_text = c.get_text(strip=True)
                    if re.match(r"^[A-Z0-9_-]+/[A-Z0-9_/-]+$", c_text):
                        tender_id = c_text
                        break
                if not tender_id:
                    m_tid = re.search(r"\b([A-Z0-9_-]+/(?:DW|OFFSHORE|SEIS|RIG|[A-Z0-9_-]+)/\d{4,10}(?:/\d{2,4})?)\b", full_row_text, re.IGNORECASE)
                    if m_tid:
                        tender_id = m_tid.group(1)
                if not tender_id and link:
                    m_url_id = re.search(r"[?&]id=([A-Za-z0-9_-]+)", link)
                    if m_url_id:
                        tender_id = m_url_id.group(1)

                # Extract estimated value if present
                val_cr = None
                m_val = re.search(r"(?:₹|Rs\.?|INR)\s*([\d,.]+)\s*(?:Cr|Crore|Lakh|L)?", full_row_text, re.IGNORECASE)
                if m_val:
                    try:
                        raw_num = float(m_val.group(1).replace(",", ""))
                        if "lakh" in full_row_text.lower():
                            val_cr = raw_num / 100.0
                        else:
                            val_cr = raw_num
                    except Exception:
                        val_cr = None

                # Issuer detection (e.g. ONGC, OIL, GAIL, IOCL)
                issuer = "Government eProcurement"
                for org in ["ONGC", "Oil India Limited", "OIL", "GAIL", "IOCL", "BPCL", "DGH"]:
                    if org.lower() in full_row_text.lower():
                        issuer = org
                        break

                records.append(RawExtractedRecord(
                    title=title,
                    url=link,
                    content=full_row_text,
                    summary=f"Tender from {issuer}. Closing: {close_date or 'N/A'}",
                    published_at=pub_date or None,
                    external_id=tender_id,
                    raw_metadata={
                        "tender_id": tender_id,
                        "issuer": issuer,
                        "closing_date": close_date,
                        "estimated_value_cr": val_cr,
                    },
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

            issuer = rec.raw_metadata.get("issuer", "Government eProcurement")
            tender_id = rec.raw_metadata.get("tender_id") or rec.external_id

            events.append(NormalizedSchemeEvent(
                event_id=evt_id,
                scheme_id=self.scheme_id,
                source_id=self.source_id,
                event_type="TENDER_NOTICE",
                title=f"[{issuer}] {rec.title}",
                content=rec.content or rec.title,
                summary=rec.summary or rec.title[:200],
                published_at=rec.published_at or now_utc,
                retrieved_at=now_utc,
                entities=[issuer] if issuer != "Government eProcurement" else [],
                companies=[issuer] if issuer in ["ONGC", "OIL", "Oil India Limited", "GAIL", "IOCL", "BPCL"] else [],
                projects=[],
                contracts=[tender_id] if tender_id else [],
                importance=importance,
                confidence=conf,
                url=rec.url,
                external_id=tender_id,
                relevance_reason=reason,
                water_depth=water_depth.value,
                evidence=[{
                    "source": self.name,
                    "url": rec.url,
                    "published_at": rec.published_at or now_utc,
                    "claim": rec.title,
                    "issuer": issuer,
                    "closing_date": rec.raw_metadata.get("closing_date"),
                    "estimated_value_cr": rec.raw_metadata.get("estimated_value_cr"),
                    "confidence": conf,
                }],
            ))

        return events
