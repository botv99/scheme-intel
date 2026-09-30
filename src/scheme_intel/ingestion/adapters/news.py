"""
Specialized News and Specialist Energy Source Adapters (Stage 4E).
Implements resilient adapters for:
  - Economic Times EnergyWorld (ETEnergyWorldAdapter)
  - Reuters India Energy (ReutersEnergyAdapter)
  - Business Standard Hydrocarbon (BusinessStandardEnergyAdapter)
  - Mint Energy & Infrastructure (MintEnergyAdapter)
  - Offshore Technology Specialist Publication (OffshoreTechnologyAdapter)
  - Legacy DGH Archive Adapter (LegacyDGHArchiveAdapter)
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from .base import BaseSourceAdapter, RawExtractedRecord
from ..models import NormalizedSchemeEvent
from ...schemes.samudra_manthan.relevance import SamudraRelevanceFilter
from ...schemes.samudra_manthan.entities import classify_water_depth_strict
from ...logger import get_logger

logger = get_logger(__name__)


class BaseNewsAdapter(BaseSourceAdapter):
    """Shared baseline functionality for financial news and specialist media adapters."""

    def __init__(
        self,
        source_id: str,
        name: str,
        url: str,
        authority_level: int = 3,
        is_legacy: bool = False,
        scheme_id: str = "samudra_manthan",
        timeout: int = 15,
    ):
        super().__init__(
            source_id=source_id,
            scheme_id=scheme_id,
            source_type="legacy" if is_legacy else ("specialist" if authority_level == 4 else "news"),
            name=name,
            url=url,
            timeout=timeout,
        )
        self.authority_level = authority_level
        self.is_legacy = is_legacy
        self.base_confidence = 0.65 if is_legacy else (0.78 if authority_level == 4 else 0.82)

    def extract_entities_from_text(self, text: str) -> Dict[str, Any]:
        """Extract offshore companies, projects, contracts, and water depth from news text."""
        lowered = text.lower()
        companies: List[str] = []
        projects: List[str] = []
        contracts: List[str] = []

        # Company recognition
        company_kw = {
            "ONGC": ["ongc", "oil and natural gas corporation"],
            "Oil India": ["oil india", "oil india limited"],
            "Reliance Industries": ["reliance", "ril", "reliance industries"],
            "Vedanta (Cairn)": ["vedanta", "cairn oil", "cairn india"],
            "Deep Industries": ["deep industries", "deep ind"],
            "Alphageo": ["alphageo"],
            "SEAMEC": ["seamec"],
            "Dolphin Offshore": ["dolphin offshore"],
            "Great Eastern Shipping": ["great eastern shipping", "ge shipping", "geship"],
            "Larsen & Toubro": ["larsen & toubro", "l&t hydrocarbon", "l&t energy"],
            "Cochin Shipyard": ["cochin shipyard"],
            "Mazagon Dock": ["mazagon dock"],
        }
        for comp_name, aliases in company_kw.items():
            if any(re.search(rf"\b{re.escape(a)}\b", lowered) for a in aliases):
                companies.append(comp_name)

        # Projects / Basins
        project_kw = [
            "KG-DWN-98/2", "KG-D6", "R-Cluster", "MJ Field", "Mumbai High",
            "Cambay Offshore", "Ravva", "Mahanadi Deepwater", "Andaman Basin",
            "Cauvery Offshore", "Bengal Offshore", "Kutch Offshore", "Saurashtra Offshore",
        ]
        for p in project_kw:
            if p.lower() in lowered:
                projects.append(p)

        # Contracts / Tenders
        contract_matches = re.findall(
            r"\b(?:LOA|contract|tender|charter hire|work order|order win|bidding round|award)\b[^\.\;\n]{0,60}",
            text,
            flags=re.IGNORECASE,
        )
        for c in contract_matches[:2]:
            clean_c = c.strip()
            if len(clean_c) > 8:
                contracts.append(clean_c)

        water_depth = classify_water_depth_strict(text)

        return {
            "companies": companies,
            "projects": projects,
            "contracts": contracts,
            "water_depth": water_depth,
        }

    def normalize(self, records: List[RawExtractedRecord]) -> List[NormalizedSchemeEvent]:
        events: List[NormalizedSchemeEvent] = []
        now_utc = datetime.now(timezone.utc).isoformat()

        for rec in records:
            combined_text = f"{rec.title} {rec.summary or ''} {rec.content}"
            rel_res = SamudraRelevanceFilter.evaluate(rec.title, rec.content or rec.summary or "")

            if not rel_res.is_relevant:
                continue

            extracted = self.extract_entities_from_text(combined_text)
            evt_id = self.generate_event_id(rec.external_id, rec.title, rec.published_at)

            evidence_entry = {
                "source": self.name,
                "url": rec.url,
                "title": rec.title,
                "date": rec.published_at or now_utc[:10],
                "authority_level": self.authority_level,
                "is_legacy": self.is_legacy,
                "source_status": "LEGACY" if self.is_legacy else "CURRENT",
            }

            events.append(NormalizedSchemeEvent(
                event_id=evt_id,
                scheme_id=self.scheme_id,
                source_id=self.source_id,
                event_type="NEWS_REPORT" if not self.is_legacy else "HISTORICAL_ARCHIVE",
                title=rec.title,
                content=rec.content or rec.summary or rec.title,
                summary=rec.summary or "",
                published_at=rec.published_at or now_utc,
                retrieved_at=now_utc,
                entities=extracted["companies"] + extracted["projects"],
                evidence=[evidence_entry],
                importance=rel_res.importance,
                confidence=round(self.base_confidence, 2),
                url=rec.url,
                external_id=rec.external_id,
                companies=extracted["companies"],
                projects=extracted["projects"],
                contracts=extracted["contracts"],
                relevance_reason=rel_res.reason,
                water_depth=extracted["water_depth"],
            ))

        return events


class ETEnergyWorldAdapter(BaseNewsAdapter):
    """Economic Times EnergyWorld (Oil & Gas Beat) News Adapter."""

    def __init__(self, source_id: str = "et_energyworld", scheme_id: str = "samudra_manthan"):
        super().__init__(
            source_id=source_id,
            name="The Economic Times EnergyWorld",
            url="https://energy.economictimes.indiatimes.com/rss/oil-and-gas",
            authority_level=3,
            scheme_id=scheme_id,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content or not raw_content.strip():
            return records

        # RSS XML Parse
        if "<rss" in raw_content or "<?xml" in raw_content or "<channel>" in raw_content:
            try:
                root = ET.fromstring(raw_content)
                for item in root.findall(".//item"):
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    desc_elem = item.find("description")
                    pub_elem = item.find("pubDate")

                    title = (title_elem.text or "").strip() if title_elem is not None else ""
                    link = (link_elem.text or "").strip() if link_elem is not None else self.url
                    desc = (desc_elem.text or "").strip() if desc_elem is not None else ""
                    pub_date = (pub_elem.text or "").strip() if pub_elem is not None else None

                    if title:
                        records.append(RawExtractedRecord(
                            title=title,
                            url=link,
                            summary=desc,
                            content=desc,
                            published_at=pub_date,
                        ))
                return records
            except Exception as e:
                logger.debug("ETEnergyWorld XML parse failed, falling back to HTML: %s", e)

        # HTML fallback
        soup = BeautifulSoup(raw_content, "html.parser")
        articles = soup.find_all(["article", "div", "li"], class_=re.compile(r"news|story|article|listing", re.IGNORECASE))
        seen_titles = set()
        for art in articles:
            a_tag = art.find("a")
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            if not title or len(title) < 15 or title in seen_titles:
                continue
            seen_titles.add(title)

            link = a_tag.get("href", "")
            if link and not link.startswith("http"):
                link = f"https://energy.economictimes.indiatimes.com{link}"

            desc_tag = art.find(["p", "span", "div"], class_=re.compile(r"desc|summary|snippet", re.IGNORECASE))
            desc = desc_tag.get_text(strip=True) if desc_tag else ""

            records.append(RawExtractedRecord(
                title=title,
                url=link or self.url,
                summary=desc,
                content=desc,
            ))

        return records


class ReutersEnergyAdapter(BaseNewsAdapter):
    """Reuters India Energy & Global Commodities Adapter."""

    def __init__(self, source_id: str = "reuters_energy", scheme_id: str = "samudra_manthan"):
        super().__init__(
            source_id=source_id,
            name="Reuters India Energy & Commodities",
            url="https://www.reuters.com/business/energy/",
            authority_level=3,
            scheme_id=scheme_id,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content:
            return records

        if "<rss" in raw_content or "<?xml" in raw_content or "<channel>" in raw_content:
            try:
                root = ET.fromstring(raw_content)
                for item in root.findall(".//item"):
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    desc = (item.findtext("description") or "").strip()
                    pub_date = item.findtext("pubDate")
                    if title:
                        records.append(RawExtractedRecord(
                            title=title,
                            url=link or self.url,
                            summary=desc,
                            content=desc,
                            published_at=pub_date,
                        ))
                return records
            except Exception as e:
                logger.debug("Reuters XML parse failed: %s", e)

        # HTML parsing
        soup = BeautifulSoup(raw_content, "html.parser")
        headings = soup.find_all(["h2", "h3", "a"], attrs={"data-testid": re.compile(r"Heading|Link", re.IGNORECASE)})
        if not headings:
            headings = soup.find_all(["h2", "h3"])

        seen = set()
        for h in headings:
            a_tag = h if h.name == "a" else h.find("a")
            title = (a_tag or h).get_text(strip=True)
            if not title or len(title) < 15 or title in seen:
                continue
            seen.add(title)

            link = a_tag.get("href", "") if a_tag else ""
            if link and not link.startswith("http"):
                link = f"https://www.reuters.com{link}"

            records.append(RawExtractedRecord(
                title=title,
                url=link or self.url,
                summary=title,
                content=title,
            ))

        return records


class BusinessStandardEnergyAdapter(BaseNewsAdapter):
    """Business Standard Hydrocarbon & Corporate News Adapter."""

    def __init__(self, source_id: str = "business_standard_energy", scheme_id: str = "samudra_manthan"):
        super().__init__(
            source_id=source_id,
            name="Business Standard Hydrocarbon & Economy",
            url="https://www.business-standard.com/rss/companies-news.rss",
            authority_level=3,
            scheme_id=scheme_id,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content:
            return records

        if "<rss" in raw_content or "<?xml" in raw_content or "<channel>" in raw_content:
            try:
                root = ET.fromstring(raw_content)
                for item in root.findall(".//item"):
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    desc = (item.findtext("description") or "").strip()
                    pub_date = item.findtext("pubDate")
                    if title:
                        records.append(RawExtractedRecord(
                            title=title,
                            url=link or self.url,
                            summary=desc,
                            content=desc,
                            published_at=pub_date,
                        ))
                return records
            except Exception as e:
                logger.debug("Business Standard XML error: %s", e)

        soup = BeautifulSoup(raw_content, "html.parser")
        stories = soup.find_all(["div", "article"], class_=re.compile(r"card|story|listing", re.IGNORECASE))
        seen = set()
        for s in stories:
            a_tag = s.find("a")
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            if not title or len(title) < 15 or title in seen:
                continue
            seen.add(title)
            link = a_tag.get("href", "")
            if link and not link.startswith("http"):
                link = f"https://www.business-standard.com{link}"

            records.append(RawExtractedRecord(
                title=title,
                url=link or self.url,
                summary=title,
                content=title,
            ))
        return records


class MintEnergyAdapter(BaseNewsAdapter):
    """Mint Energy & Natural Resources News Adapter."""

    def __init__(self, source_id: str = "mint_energy", scheme_id: str = "samudra_manthan"):
        super().__init__(
            source_id=source_id,
            name="Mint Energy & Natural Resources",
            url="https://www.livemint.com/rss/industry",
            authority_level=3,
            scheme_id=scheme_id,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content:
            return records

        if "<rss" in raw_content or "<?xml" in raw_content or "<channel>" in raw_content:
            try:
                root = ET.fromstring(raw_content)
                for item in root.findall(".//item"):
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    desc = (item.findtext("description") or "").strip()
                    pub_date = item.findtext("pubDate")
                    if title:
                        records.append(RawExtractedRecord(
                            title=title,
                            url=link or self.url,
                            summary=desc,
                            content=desc,
                            published_at=pub_date,
                        ))
                return records
            except Exception as e:
                logger.debug("Mint XML error: %s", e)

        soup = BeautifulSoup(raw_content, "html.parser")
        articles = soup.find_all(["div", "article"], class_=re.compile(r"headline|story|listing", re.IGNORECASE))
        seen = set()
        for art in articles:
            a_tag = art.find("a")
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            if not title or len(title) < 15 or title in seen:
                continue
            seen.add(title)
            link = a_tag.get("href", "")
            if link and not link.startswith("http"):
                link = f"https://www.livemint.com{link}"

            records.append(RawExtractedRecord(
                title=title,
                url=link or self.url,
                summary=title,
                content=title,
            ))
        return records


class OffshoreTechnologyAdapter(BaseNewsAdapter):
    """Offshore Technology Specialist Media Adapter (Authority Level 4)."""

    def __init__(self, source_id: str = "offshore_technology", scheme_id: str = "samudra_manthan"):
        super().__init__(
            source_id=source_id,
            name="Offshore Technology (Global & Indian Upstream)",
            url="https://www.offshore-technology.com/feed/",
            authority_level=4,
            scheme_id=scheme_id,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content:
            return records

        if "<rss" in raw_content or "<?xml" in raw_content or "<channel>" in raw_content:
            try:
                root = ET.fromstring(raw_content)
                for item in root.findall(".//item"):
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    desc = (item.findtext("description") or "").strip()
                    pub_date = item.findtext("pubDate")
                    if title:
                        records.append(RawExtractedRecord(
                            title=title,
                            url=link or self.url,
                            summary=desc,
                            content=desc,
                            published_at=pub_date,
                        ))
                return records
            except Exception as e:
                logger.debug("Offshore Technology XML error: %s", e)

        soup = BeautifulSoup(raw_content, "html.parser")
        items = soup.find_all(["div", "article", "li"], class_=re.compile(r"article|feed-item|story", re.IGNORECASE))
        seen = set()
        for item in items:
            a_tag = item.find("a")
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            if not title or len(title) < 15 or title in seen:
                continue
            seen.add(title)
            link = a_tag.get("href", "")
            records.append(RawExtractedRecord(
                title=title,
                url=link or self.url,
                summary=title,
                content=title,
            ))
        return records


class LegacyDGHArchiveAdapter(BaseNewsAdapter):
    """
    Legacy DGH Archive Adapter (Authority Level 5).
    Provides access to archived regulatory bidding guidelines, OALP round historical gazettes,
    and baseline acreage circulars when live DGH SPA is blocked.
    Explicitly tags events as LEGACY with source_status='LEGACY'.
    """

    def __init__(self, source_id: str = "legacy_dgh_archive", scheme_id: str = "samudra_manthan"):
        super().__init__(
            source_id=source_id,
            name="DGH Exploration & OALP Archive (Historical Baseline)",
            url="https://dghindia.gov.in/index.php/archive/oalp",
            authority_level=5,
            is_legacy=True,
            scheme_id=scheme_id,
        )

    def parse(self, raw_content: str) -> List[RawExtractedRecord]:
        records: List[RawExtractedRecord] = []
        if not raw_content:
            return records

        soup = BeautifulSoup(raw_content, "html.parser")
        # Archive tables or list items
        rows = soup.find_all(["tr", "li", "div"], class_=re.compile(r"archive|row|document|notice", re.IGNORECASE))
        if not rows:
            rows = soup.find_all("tr")

        seen = set()
        for r in rows:
            a_tag = r.find("a")
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            if not title or len(title) < 15 or title in seen:
                continue
            seen.add(title)

            link = a_tag.get("href", "")
            if link and not link.startswith("http"):
                link = f"https://dghindia.gov.in{link}"

            # Look for archived dates in sibling cells/spans
            date_text = None
            date_match = re.search(r"\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}-\d{2}-\d{2})\b", r.get_text())
            if date_match:
                date_text = date_match.group(1)

            records.append(RawExtractedRecord(
                title=f"[ARCHIVE] {title}",
                url=link or self.url,
                summary=f"Historical DGH exploration document: {title}",
                content=r.get_text(strip=True),
                published_at=date_text or "2024-01-01",
                raw_metadata={"is_legacy": True, "source_status": "LEGACY"},
            ))

        return records
