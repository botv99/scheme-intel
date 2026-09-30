"""
Stock Exchange Corporate Announcements Adapters for NSE & BSE (Stage 4B).
Parses material corporate disclosures, tender wins, joint ventures, and contract awards.
Applies strict Samudra relevance filtering to prevent generic earnings results or routine compliance from entering the intelligence event stream.
"""
from __future__ import annotations

import json
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


class NSEFilingAdapter(BaseSourceAdapter):
    """Source adapter for NSE Corporate Filings & Announcements."""

    def __init__(
        self,
        source_id: str = "nse_energy_filings",
        scheme_id: str = "samudra_manthan",
        url: str = "https://www.nseindia.com/api/corporate-announcements?index=equities",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="filing",
            name="NSE Corporate Filings (Energy & Upstream)",
            url=url,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content or not raw_content.strip():
            return records

        # 1. Try parsing JSON (NSE Corporate Announcements API)
        try:
            data = json.loads(raw_content)
            announcements = data if isinstance(data, list) else data.get("data", [])
            for item in announcements:
                symbol = item.get("symbol", "")
                company = item.get("companyName") or item.get("sm_name") or symbol
                subject = item.get("subject", "")
                desc = item.get("desc", "")
                att_text = item.get("attchmntText", "")
                headline = subject or desc or f"{symbol} Announcement"
                title = f"[{company}] {headline}" if company else headline
                link = item.get("attchmntFile") or item.get("attmntFile", "")
                date_str = item.get("sort_date") or item.get("an_dt") or item.get("dt")
                seq_id = str(item.get("seq_id", ""))

                records.append(RawExtractedRecord(
                    title=title,
                    url=link or self.url,
                    content=f"{subject} {desc} {att_text}".strip(),
                    summary=att_text[:300] if att_text else (desc[:300] if desc else subject[:300]),
                    published_at=date_str,
                    external_id=seq_id or None,
                    raw_metadata={
                        "exchange": "NSE",
                        "symbol": symbol,
                        "company": company,
                        "filing_type": desc or subject,
                    },
                ))
            if records:
                return records
        except Exception:
            pass

        # 2. Fallback: Parse HTML table structure if HTML was returned
        soup = BeautifulSoup(raw_content, "html.parser")
        for tr in soup.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 3:
                continue

            row_text = tr.get_text(" ", strip=True)
            a_tag = tr.find("a", href=True)
            link = urljoin(self.url, a_tag["href"]) if a_tag else self.url
            title = a_tag.get_text(" ", strip=True) if a_tag else row_text[:100]

            records.append(RawExtractedRecord(
                title=title,
                url=link,
                content=row_text,
                raw_metadata={"exchange": "NSE"},
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

            symbol = rec.raw_metadata.get("symbol", "")
            company = rec.raw_metadata.get("company", symbol or "NSE Listed Company")

            events.append(NormalizedSchemeEvent(
                event_id=evt_id,
                scheme_id=self.scheme_id,
                source_id=self.source_id,
                event_type="EXCHANGE_FILING",
                title=rec.title,
                content=rec.content or rec.title,
                summary=rec.summary or rec.title[:200],
                published_at=rec.published_at or now_utc,
                retrieved_at=now_utc,
                entities=[c for c in [company, symbol] if c],
                companies=[c for c in [company, symbol] if c],
                projects=[],
                contracts=[],
                importance=importance,
                confidence=conf,
                url=rec.url,
                external_id=rec.external_id,
                relevance_reason=reason,
                water_depth=water_depth.value,
                evidence=[{
                    "source": "National Stock Exchange (NSE)",
                    "url": rec.url,
                    "published_at": rec.published_at or now_utc,
                    "claim": rec.title,
                    "symbol": symbol,
                    "exchange": "NSE",
                    "confidence": conf,
                }],
            ))

        return events


class BSEAnnouncementAdapter(BaseSourceAdapter):
    """Source adapter for BSE Corporate Announcements & Filings."""

    def __init__(
        self,
        source_id: str = "bse_energy_announcements",
        scheme_id: str = "samudra_manthan",
        url: str = "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w?strCat=-1&strPrevDate=&strScrip=&strSearch=P&strToDate=&strType=C",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="filing",
            name="BSE Corporate Announcements (Energy & Upstream)",
            url=url,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.bseindia.com/",
                "Origin": "https://www.bseindia.com",
            },
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content or not raw_content.strip():
            return records

        # 1. Try JSON structure (BSE API Table)
        try:
            data = json.loads(raw_content)
            items = data.get("Table", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for item in items:
                scrip = str(item.get("SCRIP_CD", item.get("scrip_code", "")))
                company = item.get("SLONGNAME", item.get("CompanyName", scrip))
                subject = item.get("NEWSSUB", item.get("Subject", ""))
                headline = item.get("HEADLINE", subject)
                news_dt = item.get("NEWS_DT", item.get("DT_TM", item.get("DissemDT", "")))
                news_id = str(item.get("NEWSID", item.get("NewsId", "")))
                att_file = item.get("ATTACHMENTNAME", "")

                pdf_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{att_file}" if att_file else self.url

                title = f"[{company}] {headline or subject}"
                records.append(RawExtractedRecord(
                    title=title,
                    url=pdf_url,
                    content=f"{subject} {headline} {item.get('MORE', '')}".strip(),
                    summary=subject[:300] if subject else headline,
                    published_at=news_dt,
                    external_id=news_id or None,
                    raw_metadata={
                        "exchange": "BSE",
                        "scrip_code": scrip,
                        "company": company,
                    },
                ))
            if records:
                return records
        except Exception:
            pass

        # 2. Fallback: Parse HTML table structure if HTML was returned
        soup = BeautifulSoup(raw_content, "html.parser")
        for tr in soup.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            txt = tr.get_text(" ", strip=True)
            a_tag = tr.find("a", href=True)
            link = urljoin(self.url, a_tag["href"]) if a_tag else self.url
            title = a_tag.get_text(" ", strip=True) if a_tag else txt[:100]

            records.append(RawExtractedRecord(
                title=title,
                url=link,
                content=txt,
                raw_metadata={"exchange": "BSE"},
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

            scrip = rec.raw_metadata.get("scrip_code", "")
            company = rec.raw_metadata.get("company", scrip or "BSE Listed Company")

            events.append(NormalizedSchemeEvent(
                event_id=evt_id,
                scheme_id=self.scheme_id,
                source_id=self.source_id,
                event_type="EXCHANGE_FILING",
                title=rec.title,
                content=rec.content or rec.title,
                summary=rec.summary or rec.title[:200],
                published_at=rec.published_at or now_utc,
                retrieved_at=now_utc,
                entities=[company] if company else [],
                companies=[company] if company else [],
                projects=[],
                contracts=[],
                importance=importance,
                confidence=conf,
                url=rec.url,
                external_id=rec.external_id,
                relevance_reason=reason,
                water_depth=water_depth.value,
                evidence=[{
                    "source": "Bombay Stock Exchange (BSE)",
                    "url": rec.url,
                    "published_at": rec.published_at or now_utc,
                    "claim": rec.title,
                    "scrip_code": scrip,
                    "exchange": "BSE",
                    "confidence": conf,
                }],
            ))

        return events
