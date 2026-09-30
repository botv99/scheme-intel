"""
PIB (Press Information Bureau) Source Adapters for Samudra Manthan (Stage 4B).
Covers:
- MoPNG (Ministry of Petroleum & Natural Gas)
- National Energy & Infrastructure Releases
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .base import BaseSourceAdapter, RawExtractedRecord
from ..models import NormalizedSchemeEvent
from ...schemes.samudra_manthan.relevance import SamudraRelevanceFilter
from ...schemes.samudra_manthan.entities import classify_water_depth_strict
from ...logger import get_logger

logger = get_logger(__name__)


class BasePIBAdapter(BaseSourceAdapter):
    """Base class for parsing PIB XML feeds and release pages."""

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content or not raw_content.strip():
            return records

        # 1. Try standard XML parsing for RSS feed
        try:
            root = ET.fromstring(raw_content.encode("utf-8", errors="replace"))
            channel = root.find("channel")
            if channel is not None:
                for item in channel.findall("item"):
                    title = item.findtext("title") or ""
                    link = item.findtext("link") or ""
                    pub_date = item.findtext("pubDate") or ""
                    desc = item.findtext("description") or ""

                    # Extract PRID from link e.g. PRID=2056789
                    prid = None
                    m_prid = re.search(r"PRID=(\d+)", link)
                    if m_prid:
                        prid = m_prid.group(1)

                    if title:
                        records.append(RawExtractedRecord(
                            title=title.strip(),
                            url=link.strip(),
                            content=desc.strip(),
                            summary=desc.strip()[:300] if desc else None,
                            published_at=pub_date.strip() or None,
                            external_id=prid,
                            raw_metadata={"prid": prid},
                        ))
                if records:
                    return records
        except Exception as e:
            logger.debug("[PIBAdapter] XML parsing fallback to BeautifulSoup: %s", e)

        # 2. BeautifulSoup fallback for malformed XML or HTML wrap
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(raw_content, "html.parser")
        items = soup.find_all("item")
        if items:
            for it in items:
                title = it.find("title")
                link = it.find("link")
                pub = it.find("pubdate")
                desc = it.find("description")

                t_str = title.get_text(strip=True) if title else ""
                l_str = link.get_text(strip=True) if link else (link.get("href") if link else "")
                p_str = pub.get_text(strip=True) if pub else ""
                d_str = desc.get_text(strip=True) if desc else ""

                prid = None
                m_prid = re.search(r"PRID=(\d+)", l_str)
                if m_prid:
                    prid = m_prid.group(1)

                if t_str:
                    records.append(RawExtractedRecord(
                        title=t_str,
                        url=l_str,
                        content=d_str,
                        summary=d_str[:300] if d_str else None,
                        published_at=p_str or None,
                        external_id=prid,
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

            comp_list = []
            for c_name in ["ONGC", "Oil India", "Reliance Industries", "Reliance", "Vedanta", "Cairn", "GAIL", "BPCL", "IOCL"]:
                if re.search(rf"\b{re.escape(c_name)}\b", f"{rec.title} {rec.content}", re.IGNORECASE):
                    comp_list.append(c_name)

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
                event_type="POLICY_ANNOUNCEMENT" if "cabinet" in rec.title.lower() or "policy" in rec.title.lower() else "EXPLORATION_UPDATE",
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


class PIBMoPNGAdapter(BasePIBAdapter):
    """PIB Ministry of Petroleum & Natural Gas Feed."""

    def __init__(
        self,
        source_id: str = "pib_mopng_samudra",
        scheme_id: str = "samudra_manthan",
        url: str = "https://pib.gov.in/RssMain.aspx?ModId=2&MinId=30",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="rss",
            name="PIB Ministry of Petroleum & Natural Gas",
            url=url,
            timeout=timeout,
        )


class PIBNationalEnergyAdapter(BasePIBAdapter):
    """PIB National Energy & Infrastructure Feed."""

    def __init__(
        self,
        source_id: str = "pib_national_energy",
        scheme_id: str = "samudra_manthan",
        url: str = "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="rss",
            name="PIB National Energy & Infrastructure",
            url=url,
            timeout=timeout,
        )
