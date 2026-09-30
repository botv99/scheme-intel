"""
Samudra Manthan Source Redundancy Graph and Information Requirement Architecture (Stage 4E).
Implements:
1. SamudraInformationRequirement enumeration (18 granular offshore information categories).
2. Multi-tier Source Hierarchy (Tier 1 Official, Tier 2 Exchange, Tier 3 News, Tier 4 Specialist, Tier 5 Legacy).
3. RedundantSourceDefinition registry mapping information requirements to alternative independent acquisition paths.
4. Fallback groups ensuring that when a primary source fails/blocks, the coordinator activates alternate channels.
5. Information Coverage Matrix evaluating operational robustness across requirements.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class SamudraInformationRequirement(str, Enum):
    """Granular information requirements for Samudra Manthan intelligence."""
    OALP_ROUND = "OALP_ROUND"                             # OALP bidding rounds, block notices, timeline
    OFFSHORE_BLOCK_AWARD = "OFFSHORE_BLOCK_AWARD"         # Formal block awards, RSC/PSC clearances
    EXPLORATION_ACTIVITY = "EXPLORATION_ACTIVITY"         # Basin exploration campaigns, exploratory drilling
    DEEPWATER_DRILLING = "DEEPWATER_DRILLING"             # Drilling operations at 400m-1500m depth
    ULTRA_DEEPWATER_DRILLING = "ULTRA_DEEPWATER_DRILLING" # Drilling operations at >1500m depth (KG Basin, etc.)
    OFFSHORE_DISCOVERY = "OFFSHORE_DISCOVERY"             # Hydrocarbon strikes, commercial gas/oil finds
    OFFSHORE_CONTRACT = "OFFSHORE_CONTRACT"               # LOA / work orders / charter hire for offshore works
    SEISMIC_SURVEY = "SEISMIC_SURVEY"                     # 2D/3D seismic, OBN, ocean bottom cable surveys
    SUBSEA_PROJECT = "SUBSEA_PROJECT"                     # Subsea umbilicals, flowlines, manifolds, pipelines
    OFFSHORE_CAPEX = "OFFSHORE_CAPEX"                     # Upstream capex allocations, project budgets
    GOVERNMENT_POLICY = "GOVERNMENT_POLICY"               # MoPNG/DGH policies, royalty relief, fiscal terms
    EXPLORATION_INCENTIVE = "EXPLORATION_INCENTIVE"       # Accelerated depreciation, price freedom, tax holidays
    OIL_GAS_TENDER = "OIL_GAS_TENDER"                     # RFP / tenders for drilling rigs, vessels, oilfield services
    RIG_CONTRACT = "RIG_CONTRACT"                         # Jackup / drillship / semi-submersible charter hire
    OFFSHORE_PRODUCTION = "OFFSHORE_PRODUCTION"           # Oil/gas output from offshore fields
    COMPANY_JV = "COMPANY_JV"                             # Farm-ins, consortiums, foreign partnerships
    COMPANY_CAPEX = "COMPANY_CAPEX"                       # Operator corporate investment disclosures
    ENERGY_POLICY = "ENERGY_POLICY"                       # Cabinet / PMO / national energy security directives
    GLOBAL_OIL_IMPACT = "GLOBAL_OIL_IMPACT"               # Brent crude movements, offshore rig dayrates, global E&P capex


class SourceAuthorityLevel(int, Enum):
    """Authority and confidence hierarchy for data sources."""
    TIER1_OFFICIAL = 1          # Regulatory / Ministry / Direct Operator Portal (0.95)
    TIER2_EXCHANGE = 2          # NSE / BSE / SEBI statutory disclosures (0.92)
    TIER3_FINANCIAL_NEWS = 3    # High-quality financial / business news (0.82)
    TIER4_SPECIALIST_MEDIA = 4  # Specialist energy / offshore publications (0.78)
    TIER5_LEGACY_ARCHIVE = 5    # Archived government gazettes / historical baselines (0.65)


BASE_CONFIDENCE_BY_TIER: Dict[SourceAuthorityLevel, float] = {
    SourceAuthorityLevel.TIER1_OFFICIAL: 0.95,
    SourceAuthorityLevel.TIER2_EXCHANGE: 0.92,
    SourceAuthorityLevel.TIER3_FINANCIAL_NEWS: 0.82,
    SourceAuthorityLevel.TIER4_SPECIALIST_MEDIA: 0.78,
    SourceAuthorityLevel.TIER5_LEGACY_ARCHIVE: 0.65,
}


@dataclass
class RedundantSourceDefinition:
    """Rich source definition representing capabilities, fallback groups, and authority tiers."""
    source_id: str
    name: str
    url: str
    scheme_id: str = "samudra_manthan"
    source_type: str = "official"             # official, exchange, news, specialist, legacy
    authority_level: SourceAuthorityLevel = SourceAuthorityLevel.TIER1_OFFICIAL
    information_types: List[SamudraInformationRequirement] = field(default_factory=list)
    fallback_group: str = "offshore_exploration"
    priority: int = 1                         # Lower number = higher priority within group
    enabled: bool = True
    feed_type: str = "html"                   # rss, html, json_api, archive
    is_legacy: bool = False
    parser: Optional[str] = None
    query_templates: List[str] = field(default_factory=list)

    @property
    def base_confidence(self) -> float:
        return BASE_CONFIDENCE_BY_TIER.get(self.authority_level, 0.70)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["authority_level"] = self.authority_level.value
        d["information_types"] = [it.value for it in self.information_types]
        return d


# ─────────────────────────────────────────────────────────────────────────────
# REDUNDANT SOURCE REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

SAMUDRA_REDUNDANT_CATALOG: Dict[str, RedundantSourceDefinition] = {
    # ── Tier 1: Primary Official ─────────────────────────────────────────────
    "dgh_portal": RedundantSourceDefinition(
        source_id="dgh_portal",
        name="Directorate General of Hydrocarbons (DGH)",
        url="https://dghindia.gov.in",
        source_type="official",
        authority_level=SourceAuthorityLevel.TIER1_OFFICIAL,
        information_types=[
            SamudraInformationRequirement.OALP_ROUND,
            SamudraInformationRequirement.OFFSHORE_BLOCK_AWARD,
            SamudraInformationRequirement.EXPLORATION_ACTIVITY,
            SamudraInformationRequirement.DEEPWATER_DRILLING,
            SamudraInformationRequirement.ULTRA_DEEPWATER_DRILLING,
            SamudraInformationRequirement.GOVERNMENT_POLICY,
            SamudraInformationRequirement.EXPLORATION_INCENTIVE,
        ],
        fallback_group="oalp",
        priority=1,
        feed_type="html",
        parser="dgh_html",
    ),
    "pib_mopng_samudra": RedundantSourceDefinition(
        source_id="pib_mopng_samudra",
        name="PIB Ministry of Petroleum & Natural Gas",
        url="https://pib.gov.in/RssMain.aspx?ModId=2&MinId=30",
        source_type="official",
        authority_level=SourceAuthorityLevel.TIER1_OFFICIAL,
        information_types=[
            SamudraInformationRequirement.GOVERNMENT_POLICY,
            SamudraInformationRequirement.ENERGY_POLICY,
            SamudraInformationRequirement.OFFSHORE_BLOCK_AWARD,
            SamudraInformationRequirement.EXPLORATION_INCENTIVE,
        ],
        fallback_group="government_policy",
        priority=1,
        feed_type="rss",
        parser="pib_rss",
    ),
    "pib_national_energy": RedundantSourceDefinition(
        source_id="pib_national_energy",
        name="PIB National Energy & Infrastructure",
        url="https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
        source_type="official",
        authority_level=SourceAuthorityLevel.TIER1_OFFICIAL,
        information_types=[
            SamudraInformationRequirement.ENERGY_POLICY,
            SamudraInformationRequirement.GOVERNMENT_POLICY,
            SamudraInformationRequirement.OFFSHORE_DISCOVERY,
            SamudraInformationRequirement.GLOBAL_OIL_IMPACT,
        ],
        fallback_group="government_policy",
        priority=2,
        feed_type="rss",
        parser="pib_rss",
    ),
    "pmo_releases": RedundantSourceDefinition(
        source_id="pmo_releases",
        name="Prime Minister's Office Press Releases",
        url="https://www.pmindia.gov.in/en/news-updates/",
        source_type="official",
        authority_level=SourceAuthorityLevel.TIER1_OFFICIAL,
        information_types=[
            SamudraInformationRequirement.ENERGY_POLICY,
            SamudraInformationRequirement.GOVERNMENT_POLICY,
            SamudraInformationRequirement.OFFSHORE_CAPEX,
        ],
        fallback_group="government_policy",
        priority=3,
        feed_type="html",
        parser="pmo_html",
    ),
    "cppp_hydrocarbons": RedundantSourceDefinition(
        source_id="cppp_hydrocarbons",
        name="Government eProcurement - Hydrocarbon Tenders",
        url="https://eprocure.gov.in/cppp/latestactivetendersnew",
        source_type="official",
        authority_level=SourceAuthorityLevel.TIER1_OFFICIAL,
        information_types=[
            SamudraInformationRequirement.OIL_GAS_TENDER,
            SamudraInformationRequirement.RIG_CONTRACT,
            SamudraInformationRequirement.SEISMIC_SURVEY,
            SamudraInformationRequirement.SUBSEA_PROJECT,
            SamudraInformationRequirement.OFFSHORE_CONTRACT,
        ],
        fallback_group="offshore_contracts",
        priority=1,
        feed_type="html",
        parser="cppp_tender",
    ),
    "ongc_corporate": RedundantSourceDefinition(
        source_id="ongc_corporate",
        name="ONGC Corporate Disclosures",
        url="https://ongcindia.com/web/eng/media/press-release",
        source_type="official",
        authority_level=SourceAuthorityLevel.TIER1_OFFICIAL,
        information_types=[
            SamudraInformationRequirement.EXPLORATION_ACTIVITY,
            SamudraInformationRequirement.DEEPWATER_DRILLING,
            SamudraInformationRequirement.ULTRA_DEEPWATER_DRILLING,
            SamudraInformationRequirement.OFFSHORE_DISCOVERY,
            SamudraInformationRequirement.OFFSHORE_PRODUCTION,
            SamudraInformationRequirement.OFFSHORE_CONTRACT,
            SamudraInformationRequirement.COMPANY_CAPEX,
            SamudraInformationRequirement.OFFSHORE_CAPEX,
        ],
        fallback_group="offshore_exploration",
        priority=1,
        feed_type="html",
        parser="ongc_html",
    ),
    "oil_india_corporate": RedundantSourceDefinition(
        source_id="oil_india_corporate",
        name="Oil India Corporate Press Releases",
        url="https://www.oil-india.com/press-release",
        source_type="official",
        authority_level=SourceAuthorityLevel.TIER1_OFFICIAL,
        information_types=[
            SamudraInformationRequirement.EXPLORATION_ACTIVITY,
            SamudraInformationRequirement.DEEPWATER_DRILLING,
            SamudraInformationRequirement.SEISMIC_SURVEY,
            SamudraInformationRequirement.OFFSHORE_BLOCK_AWARD,
            SamudraInformationRequirement.COMPANY_CAPEX,
        ],
        fallback_group="offshore_exploration",
        priority=2,
        feed_type="html",
        parser="oil_india_html",
    ),
    "ril_investor_updates": RedundantSourceDefinition(
        source_id="ril_investor_updates",
        name="Reliance Industries Investor Releases",
        url="https://www.ril.com/news-media/press-releases",
        source_type="official",
        authority_level=SourceAuthorityLevel.TIER1_OFFICIAL,
        information_types=[
            SamudraInformationRequirement.ULTRA_DEEPWATER_DRILLING,
            SamudraInformationRequirement.OFFSHORE_PRODUCTION,
            SamudraInformationRequirement.SUBSEA_PROJECT,
            SamudraInformationRequirement.COMPANY_JV,
            SamudraInformationRequirement.COMPANY_CAPEX,
        ],
        fallback_group="deepwater",
        priority=1,
        feed_type="html",
        parser="ril_html",
    ),
    "vedanta_corporate": RedundantSourceDefinition(
        source_id="vedanta_corporate",
        name="Vedanta / Cairn Oil & Gas Corporate Disclosures",
        url="https://www.vedantalimited.com/eng/investor-relations-stock-exchange-announcements.php",
        source_type="official",
        authority_level=SourceAuthorityLevel.TIER1_OFFICIAL,
        information_types=[
            SamudraInformationRequirement.EXPLORATION_ACTIVITY,
            SamudraInformationRequirement.OFFSHORE_PRODUCTION,
            SamudraInformationRequirement.OFFSHORE_BLOCK_AWARD,
            SamudraInformationRequirement.COMPANY_CAPEX,
        ],
        fallback_group="offshore_exploration",
        priority=3,
        feed_type="html",
        parser="vedanta_html",
    ),

    # ── Tier 2: Exchange & Statutory Disclosures ──────────────────────────────
    "nse_energy_filings": RedundantSourceDefinition(
        source_id="nse_energy_filings",
        name="NSE Corporate Announcements (Energy & Services)",
        url="https://www.nseindia.com/api/corporate-announcements?index=equities",
        source_type="exchange",
        authority_level=SourceAuthorityLevel.TIER2_EXCHANGE,
        information_types=[
            SamudraInformationRequirement.OFFSHORE_CONTRACT,
            SamudraInformationRequirement.RIG_CONTRACT,
            SamudraInformationRequirement.SEISMIC_SURVEY,
            SamudraInformationRequirement.SUBSEA_PROJECT,
            SamudraInformationRequirement.COMPANY_JV,
            SamudraInformationRequirement.COMPANY_CAPEX,
            SamudraInformationRequirement.OFFSHORE_DISCOVERY,
        ],
        fallback_group="offshore_contracts",
        priority=2,
        feed_type="json_api",
        parser="exchange_filing",
    ),
    "bse_energy_announcements": RedundantSourceDefinition(
        source_id="bse_energy_announcements",
        name="BSE Corporate Filings (Energy & Offshore)",
        url="https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w",
        source_type="exchange",
        authority_level=SourceAuthorityLevel.TIER2_EXCHANGE,
        information_types=[
            SamudraInformationRequirement.OFFSHORE_CONTRACT,
            SamudraInformationRequirement.RIG_CONTRACT,
            SamudraInformationRequirement.SEISMIC_SURVEY,
            SamudraInformationRequirement.COMPANY_JV,
            SamudraInformationRequirement.OFFSHORE_DISCOVERY,
        ],
        fallback_group="offshore_contracts",
        priority=3,
        feed_type="json_api",
        parser="exchange_filing",
    ),

    # ── Tier 3: High-Quality Financial & Business News ────────────────────────
    "et_energyworld": RedundantSourceDefinition(
        source_id="et_energyworld",
        name="The Economic Times EnergyWorld (Oil & Gas)",
        url="https://energy.economictimes.indiatimes.com/rss/oil-and-gas",
        source_type="news",
        authority_level=SourceAuthorityLevel.TIER3_FINANCIAL_NEWS,
        information_types=[
            SamudraInformationRequirement.OALP_ROUND,
            SamudraInformationRequirement.OFFSHORE_BLOCK_AWARD,
            SamudraInformationRequirement.EXPLORATION_ACTIVITY,
            SamudraInformationRequirement.DEEPWATER_DRILLING,
            SamudraInformationRequirement.OFFSHORE_CONTRACT,
            SamudraInformationRequirement.GOVERNMENT_POLICY,
            SamudraInformationRequirement.EXPLORATION_INCENTIVE,
            SamudraInformationRequirement.OIL_GAS_TENDER,
            SamudraInformationRequirement.OFFSHORE_DISCOVERY,
            SamudraInformationRequirement.OFFSHORE_PRODUCTION,
            SamudraInformationRequirement.OFFSHORE_CAPEX,
        ],
        fallback_group="oalp",
        priority=2,
        feed_type="rss",
        parser="news_rss",
        query_templates=[
            "offshore exploration India",
            "DGH OALP round",
            "ONGC deepwater KG basin",
            "offshore drilling contract",
        ],
    ),
    "reuters_energy": RedundantSourceDefinition(
        source_id="reuters_energy",
        name="Reuters India Energy & Commodities",
        url="https://www.reuters.com/business/energy/",
        source_type="news",
        authority_level=SourceAuthorityLevel.TIER3_FINANCIAL_NEWS,
        information_types=[
            SamudraInformationRequirement.GLOBAL_OIL_IMPACT,
            SamudraInformationRequirement.DEEPWATER_DRILLING,
            SamudraInformationRequirement.ULTRA_DEEPWATER_DRILLING,
            SamudraInformationRequirement.OFFSHORE_DISCOVERY,
            SamudraInformationRequirement.ENERGY_POLICY,
            SamudraInformationRequirement.COMPANY_JV,
        ],
        fallback_group="deepwater",
        priority=2,
        feed_type="rss",
        parser="news_rss",
        query_templates=[
            "India offshore oil gas",
            "India deepwater exploration",
            "Reliance BP deepwater KG-D6",
            "Brent crude India upstream",
        ],
    ),
    "business_standard_energy": RedundantSourceDefinition(
        source_id="business_standard_energy",
        name="Business Standard Hydrocarbon & Economy",
        url="https://www.business-standard.com/rss/companies-news.rss",
        source_type="news",
        authority_level=SourceAuthorityLevel.TIER3_FINANCIAL_NEWS,
        information_types=[
            SamudraInformationRequirement.GOVERNMENT_POLICY,
            SamudraInformationRequirement.OFFSHORE_CONTRACT,
            SamudraInformationRequirement.OIL_GAS_TENDER,
            SamudraInformationRequirement.COMPANY_CAPEX,
            SamudraInformationRequirement.OFFSHORE_CAPEX,
        ],
        fallback_group="government_policy",
        priority=4,
        feed_type="rss",
        parser="news_rss",
        query_templates=[
            "MoPNG offshore policy",
            "ONGC tender awarded",
            "Oil India offshore Andaman",
        ],
    ),
    "mint_energy": RedundantSourceDefinition(
        source_id="mint_energy",
        name="Mint Energy & Natural Resources",
        url="https://www.livemint.com/rss/industry",
        source_type="news",
        authority_level=SourceAuthorityLevel.TIER3_FINANCIAL_NEWS,
        information_types=[
            SamudraInformationRequirement.OALP_ROUND,
            SamudraInformationRequirement.OFFSHORE_BLOCK_AWARD,
            SamudraInformationRequirement.EXPLORATION_ACTIVITY,
            SamudraInformationRequirement.COMPANY_JV,
            SamudraInformationRequirement.ENERGY_POLICY,
        ],
        fallback_group="oalp",
        priority=3,
        feed_type="rss",
        parser="news_rss",
        query_templates=[
            "OALP bidding blocks",
            "offshore gas discovery India",
        ],
    ),

    # ── Tier 4: Specialist Energy & Offshore Publications ─────────────────────
    "offshore_technology": RedundantSourceDefinition(
        source_id="offshore_technology",
        name="Offshore Technology (Global & Indian Upstream)",
        url="https://www.offshore-technology.com/feed/",
        source_type="specialist",
        authority_level=SourceAuthorityLevel.TIER4_SPECIALIST_MEDIA,
        information_types=[
            SamudraInformationRequirement.DEEPWATER_DRILLING,
            SamudraInformationRequirement.ULTRA_DEEPWATER_DRILLING,
            SamudraInformationRequirement.RIG_CONTRACT,
            SamudraInformationRequirement.SUBSEA_PROJECT,
            SamudraInformationRequirement.SEISMIC_SURVEY,
            SamudraInformationRequirement.GLOBAL_OIL_IMPACT,
            SamudraInformationRequirement.OFFSHORE_DISCOVERY,
        ],
        fallback_group="deepwater",
        priority=3,
        feed_type="rss",
        parser="specialist_rss",
        query_templates=[
            "India deepwater rig charter",
            "KG basin subsea umbilical",
            "Andaman basin seismic survey",
        ],
    ),

    # ── Tier 5: Legacy Official Archives ─────────────────────────────────────
    "legacy_dgh_archive": RedundantSourceDefinition(
        source_id="legacy_dgh_archive",
        name="DGH Exploration & OALP Archive (Historical Baseline)",
        url="https://dghindia.gov.in/index.php/archive/oalp",
        source_type="legacy",
        authority_level=SourceAuthorityLevel.TIER5_LEGACY_ARCHIVE,
        information_types=[
            SamudraInformationRequirement.OALP_ROUND,
            SamudraInformationRequirement.OFFSHORE_BLOCK_AWARD,
            SamudraInformationRequirement.GOVERNMENT_POLICY,
        ],
        fallback_group="oalp",
        priority=5,
        enabled=True,
        feed_type="archive",
        is_legacy=True,
        parser="legacy_archive",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# LOGICAL FALLBACK GROUPS
# ─────────────────────────────────────────────────────────────────────────────

SAMUDRA_FALLBACK_GROUPS: Dict[str, List[str]] = {
    "government_policy": [
        "pib_mopng_samudra",
        "pib_national_energy",
        "pmo_releases",
        "et_energyworld",
        "business_standard_energy",
    ],
    "oalp": [
        "dgh_portal",
        "et_energyworld",
        "mint_energy",
        "reuters_energy",
        "legacy_dgh_archive",
    ],
    "offshore_exploration": [
        "ongc_corporate",
        "oil_india_corporate",
        "ril_investor_updates",
        "vedanta_corporate",
        "nse_energy_filings",
        "et_energyworld",
        "reuters_energy",
        "offshore_technology",
    ],
    "offshore_contracts": [
        "cppp_hydrocarbons",
        "ongc_corporate",
        "oil_india_corporate",
        "nse_energy_filings",
        "bse_energy_announcements",
        "et_energyworld",
        "business_standard_energy",
    ],
    "deepwater": [
        "dgh_portal",
        "ongc_corporate",
        "ril_investor_updates",
        "offshore_technology",
        "reuters_energy",
        "et_energyworld",
    ],
    "ultra_deepwater": [
        "dgh_portal",
        "ongc_corporate",
        "ril_investor_updates",
        "offshore_technology",
        "reuters_energy",
    ],
    "tenders": [
        "cppp_hydrocarbons",
        "ongc_corporate",
        "oil_india_corporate",
        "nse_energy_filings",
        "et_energyworld",
        "business_standard_energy",
    ],
    "corporate_filings": [
        "nse_energy_filings",
        "bse_energy_announcements",
        "ongc_corporate",
        "oil_india_corporate",
        "ril_investor_updates",
        "vedanta_corporate",
        "et_energyworld",
    ],
    "market_impact": [
        "reuters_energy",
        "business_standard_energy",
        "offshore_technology",
    ],
    "global_energy": [
        "reuters_energy",
        "offshore_technology",
        "et_energyworld",
    ],
}


def get_fallback_sources_for_source(source_id: str) -> List[RedundantSourceDefinition]:
    """Given a failed source, return an ordered list of registered alternative sources in its fallback group."""
    source_def = SAMUDRA_REDUNDANT_CATALOG.get(source_id)
    if not source_def:
        return []

    group_sources = SAMUDRA_FALLBACK_GROUPS.get(source_def.fallback_group, [])
    alternatives: List[RedundantSourceDefinition] = []
    for sid in group_sources:
        if sid != source_id and sid in SAMUDRA_REDUNDANT_CATALOG:
            alternatives.append(SAMUDRA_REDUNDANT_CATALOG[sid])

    # Sort alternatives by priority
    return sorted(alternatives, key=lambda s: s.priority)


def get_sources_for_information_requirement(
    requirement: SamudraInformationRequirement,
) -> List[RedundantSourceDefinition]:
    """Retrieve all candidate sources that provide evidence for a given information requirement."""
    matches: List[RedundantSourceDefinition] = []
    for s_def in SAMUDRA_REDUNDANT_CATALOG.values():
        if s_def.enabled and requirement in s_def.information_types:
            matches.append(s_def)
    return sorted(matches, key=lambda s: (s.authority_level.value, s.priority))


def get_information_coverage_matrix() -> Dict[str, Dict[str, Any]]:
    """
    Computes the multi-path redundancy status for every information requirement.
    Ratings:
      - STRONG: >=3 independent sources with >=1 primary/secondary and >=1 news/specialist
      - ADEQUATE: >=2 independent sources
      - WEAK: exactly 1 source
      - NO_RELIABLE_SOURCE: 0 sources
    """
    matrix: Dict[str, Dict[str, Any]] = {}
    for req in SamudraInformationRequirement:
        sources = get_sources_for_information_requirement(req)
        primary_sources = [s.name for s in sources if s.authority_level == SourceAuthorityLevel.TIER1_OFFICIAL]
        exchange_sources = [s.name for s in sources if s.authority_level == SourceAuthorityLevel.TIER2_EXCHANGE]
        news_sources = [s.name for s in sources if s.authority_level == SourceAuthorityLevel.TIER3_FINANCIAL_NEWS]
        specialist_sources = [s.name for s in sources if s.authority_level == SourceAuthorityLevel.TIER4_SPECIALIST_MEDIA]
        legacy_sources = [s.name for s in sources if s.authority_level == SourceAuthorityLevel.TIER5_LEGACY_ARCHIVE]

        total_paths = len(sources)
        has_official_or_exchange = bool(primary_sources or exchange_sources)
        has_news_or_specialist = bool(news_sources or specialist_sources)

        if total_paths >= 3 and has_official_or_exchange and has_news_or_specialist:
            rating = "STRONG"
        elif total_paths >= 2 and has_official_or_exchange:
            rating = "ADEQUATE"
        elif total_paths >= 1:
            rating = "WEAK"
        else:
            rating = "NO_RELIABLE_SOURCE"

        matrix[req.value] = {
            "requirement": req.value,
            "total_independent_paths": total_paths,
            "primary_official": primary_sources,
            "exchange_statutory": exchange_sources,
            "financial_news": news_sources,
            "specialist_media": specialist_sources,
            "legacy_archive": legacy_sources,
            "coverage_rating": rating,
        }

    return matrix
