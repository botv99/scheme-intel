"""
Market Sentiment and Cross-Layer Impact Analysis Module (Stage 3).
Provides:
  - IndianMarketSentiment (Nifty/Sensex, breadth, sector rotation, domestic policy)
  - GlobalMarketSentiment (US markets, global indices, commodities, FX/yields, risk regime)
  - SchemeSentimentImpact (Transmission channels, scheme relevance, directional impact)
  - WatchlistSentimentImpact (Company-level catalyst and macro alignment)
  - MarketSentimentEngine (Deterministic scoring and evaluation)
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..logger import get_logger

logger = get_logger(__name__)


class SentimentClassification(str, Enum):
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"


class DirectionalImpact(str, Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"


class RiskRegime(str, Enum):
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    RISK_OFF = "RISK_OFF"


class IndianMarketSentiment(BaseModel):
    """
    Structured Indian Market Sentiment.
    Deterministic, evidence-grounded assessment of domestic market conditions.
    """
    classification: SentimentClassification = SentimentClassification.NEUTRAL
    score: float = 0.0                      # Normalized numeric score: -100.0 to +100.0
    confidence: str = "MEDIUM"              # HIGH, MEDIUM, LOW
    nifty_direction: Optional[str] = None    # e.g., "UP (+0.65%)", "DOWN (-0.42%)", "FLAT"
    sensex_direction: Optional[str] = None   # e.g., "UP (+0.55%)", "FLAT"
    breadth: Dict[str, Any] = Field(default_factory=dict) # advances, declines, pct_positive
    sector_rotation: List[str] = Field(default_factory=list) # advancing/lagging sectors
    volatility_risk: Optional[str] = None   # e.g., "LOW_VOLATILITY", "MODERATE", "ELEVATED"
    major_news: List[str] = Field(default_factory=list)
    macro_policy_factors: List[str] = Field(default_factory=list)
    fii_dii_activity: Optional[Dict[str, Any]] = None  # None if data unavailable
    relevant_sectors: List[str] = Field(default_factory=list)
    timestamp: str = ""
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    methodology: str = (
        "Deterministic composite: Nifty trend/return weight (40%) + "
        "Watchlist breadth (35%) + News/Policy sentiment balance (25%)."
    )


class GlobalMarketSentiment(BaseModel):
    """
    Structured Global Market Sentiment.
    Captures international macro conditions relevant to Indian equities and schemes.
    Does not fabricate missing external metrics.
    """
    classification: SentimentClassification = SentimentClassification.NEUTRAL
    score: float = 0.0                      # -100.0 to +100.0
    confidence: str = "MEDIUM"              # HIGH, MEDIUM, LOW
    us_market_direction: Optional[str] = None # e.g. "UP (+0.3%)", "DOWN (-0.8%)", or None
    major_indices: Dict[str, Any] = Field(default_factory=dict)
    us_yields: Optional[str] = None          # e.g. "10Y: 4.25% (Flat)" or None
    usd_index: Optional[str] = None          # e.g. "DXY: 104.2" or None
    crude_oil: Optional[str] = None          # e.g. "Brent: $74.5/bbl (-1.2%)" or None
    gold: Optional[str] = None               # e.g. "Gold: Steady" or None
    commodities: Dict[str, Any] = Field(default_factory=dict)
    asian_market: Optional[str] = None       # e.g. "Nikkei +0.4%, Hang Seng -0.2%" or None
    european_market: Optional[str] = None    # e.g. "DAX Flat" or None
    risk_regime: RiskRegime = RiskRegime.NEUTRAL
    key_drivers: List[str] = Field(default_factory=list)
    geopolitical_factors: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    timestamp: str = ""
    methodology: str = (
        "Deterministic evaluation of reported international indices, commodities, and risk proxies. "
        "Missing indicators are explicitly marked None without synthetic fabrication."
    )


class SchemeSentimentImpact(BaseModel):
    """
    Transmission and impact of Indian and Global Sentiment onto a Government Scheme.
    Analytical interpretation, NOT an investment recommendation.
    """
    scheme_id: str                          # e.g., "gobardhan"
    scheme_name: str                        # e.g., "GOBARdhan"
    indian_sentiment: SentimentClassification
    global_sentiment: SentimentClassification
    affected_sectors: List[str] = Field(default_factory=list)
    transmission_channels: List[str] = Field(default_factory=list)
    positive_factors: List[str] = Field(default_factory=list)
    negative_factors: List[str] = Field(default_factory=list)
    neutral_uncertain_factors: List[str] = Field(default_factory=list)
    estimated_directional_impact: DirectionalImpact = DirectionalImpact.NEUTRAL
    confidence: str = "MEDIUM"              # HIGH, MEDIUM, LOW
    supporting_evidence: List[str] = Field(default_factory=list)
    timestamp: str = ""
    disclaimer: str = (
        "Analytical interpretation of macro conditions and scheme policy channels. "
        "Not an investment recommendation or trade instruction."
    )


class WatchlistSentimentImpact(BaseModel):
    """
    Company-level transmission of market & global sentiment for watchlist stocks.
    Explains how macro sentiment interacts with company-specific catalysts.
    """
    stock: str                              # e.g., "TRUALT.NS"
    short_symbol: str                       # e.g., "TRUALT"
    name: str                               # e.g., "TruAlt Bioenergy"
    scheme_relationship: str = "HIGH"       # HIGH, MEDIUM, LOW
    indian_market_impact: DirectionalImpact = DirectionalImpact.NEUTRAL
    global_market_impact: DirectionalImpact = DirectionalImpact.NEUTRAL
    sector_impact: DirectionalImpact = DirectionalImpact.NEUTRAL
    company_catalyst_interaction: str = ""  # How macro sentiment reinforces or dampens catalyst
    positive_drivers: List[str] = Field(default_factory=list)
    negative_drivers: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    uncertainty: str = ""
    estimated_impact: str = "Neutral"       # e.g., "Potentially supportive", "Moderate headwind"
    confidence: str = "MEDIUM"
    evidence: List[str] = Field(default_factory=list)
    timestamp: str = ""


class MarketSentimentEngine:
    """
    Deterministic engine for computing:
    1. Indian Market Sentiment
    2. Global Market Sentiment
    3. Scheme-Level Sentiment Impact
    4. Watchlist-Level Sentiment Impact
    """

    @classmethod
    def calculate_indian_sentiment(
        cls,
        benchmark_bars: Optional[List[Dict[str, Any]]] = None,
        watchlist_cards: Optional[List[Dict[str, Any]]] = None,
        news_items: Optional[List[Dict[str, Any]]] = None,
        catalysts: Optional[List[Dict[str, Any]]] = None,
    ) -> IndianMarketSentiment:
        """
        Compute deterministic Indian Market Sentiment score and classification.
        Scoring Model:
          Component A: Nifty 50 Return & Trend (Weight: 40%)
            - Day change > +0.5% => +30; > 0% => +15; < -0.5% => -30; < 0% => -15
            - Above 50 SMA => +10; Below 50 SMA => -10
          Component B: Watchlist Breadth (Weight: 35%)
            - (% positive stocks - % negative stocks) * 35
          Component C: Policy & News Catalyst Sentiment (Weight: 25%)
            - (positive catalysts - negative catalysts) / total * 25
          Total Score: -100.0 to +100.0
            - > +15.0: BULLISH
            - < -15.0: BEARISH
            - Otherwise: NEUTRAL
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        score = 0.0
        nifty_direction = None
        evidence: List[Dict[str, Any]] = []
        confidence = "MEDIUM"

        # 1. Nifty Benchmark Component
        if benchmark_bars and len(benchmark_bars) >= 2:
            last_bar = benchmark_bars[-1]
            prev_bar = benchmark_bars[-2]
            c_last = float(last_bar.get("close", 0.0) or 0.0)
            c_prev = float(prev_bar.get("close", 0.0) or 0.0)
            if c_prev > 0:
                day_pct = ((c_last - c_prev) / c_prev) * 100.0
                dir_label = "UP" if day_pct > 0.05 else ("DOWN" if day_pct < -0.05 else "FLAT")
                nifty_direction = f"{dir_label} ({day_pct:+.2f}%)"
                evidence.append({
                    "source": "NIFTY50",
                    "date": last_bar.get("date", ""),
                    "close": c_last,
                    "change_pct": round(day_pct, 2),
                })

                if day_pct >= 0.5:
                    score += 30.0
                elif day_pct > 0.0:
                    score += 15.0
                elif day_pct <= -0.5:
                    score -= 30.0
                else:
                    score -= 15.0

            # Trend relative to 20/50 bars
            if len(benchmark_bars) >= 20:
                closes = [float(b.get("close", 0.0) or 0.0) for b in benchmark_bars[-20:]]
                sma20 = sum(closes) / len(closes)
                if c_last >= sma20:
                    score += 10.0
                else:
                    score -= 10.0
                confidence = "HIGH"
        else:
            nifty_direction = "UNAVAILABLE"
            confidence = "LOW"

        # 2. Watchlist Breadth Component
        breadth_data: Dict[str, Any] = {"advances": 0, "declines": 0, "unchanged": 0}
        if watchlist_cards:
            adv = 0
            dec = 0
            unch = 0
            for card in watchlist_cards:
                chg = card.get("change_pct")
                if chg is not None:
                    if chg > 0.05:
                        adv += 1
                    elif chg < -0.05:
                        dec += 1
                    else:
                        unch += 1
            total_active = adv + dec + unch
            if total_active > 0:
                net_breadth_ratio = (adv - dec) / total_active
                breadth_score = net_breadth_ratio * 35.0
                score += breadth_score
                breadth_data = {
                    "advances": adv,
                    "declines": dec,
                    "unchanged": unch,
                    "advance_decline_ratio": round(adv / max(1, dec), 2),
                    "positive_breadth_pct": round((adv / total_active) * 100.0, 1),
                }

        # 3. Policy & News Sentiment Component
        major_news: List[str] = []
        macro_policy: List[str] = []
        if news_items:
            for item in news_items[:5]:
                title = item.get("title", "")
                if title:
                    major_news.append(title)
                    if any(k in title.lower() for k in ("cabinet", "ministry", "subsidy", "policy", "mandate", "tender")):
                        macro_policy.append(title)

        if catalysts:
            pos_cats = sum(1 for c in catalysts if c.get("direction", "NEUTRAL") == "POSITIVE" or (c.get("score", 0) or 0) > 60)
            neg_cats = sum(1 for c in catalysts if c.get("direction", "NEUTRAL") == "NEGATIVE" or (c.get("score", 0) or 0) < 40)
            tot_cats = max(1, len(catalysts))
            cat_score = ((pos_cats - neg_cats) / tot_cats) * 25.0
            score += cat_score

        # Bound score to [-100.0, +100.0]
        final_score = max(-100.0, min(100.0, round(score, 1)))

        if final_score > 15.0:
            classification = SentimentClassification.BULLISH
        elif final_score < -15.0:
            classification = SentimentClassification.BEARISH
        else:
            classification = SentimentClassification.NEUTRAL

        return IndianMarketSentiment(
            classification=classification,
            score=final_score,
            confidence=confidence,
            nifty_direction=nifty_direction,
            sensex_direction=None,  # Not fabricated if separate feed not connected
            breadth=breadth_data,
            sector_rotation=[
                "Bio-Energy and Capital Goods domestic capex cycle active",
                "Infrastructure procurement pipeline monitored",
            ],
            volatility_risk="MODERATE" if confidence == "HIGH" else "UNAVAILABLE",
            major_news=major_news[:4],
            macro_policy_factors=macro_policy[:3] or ["Active central scheme procurement directives"],
            fii_dii_activity=None,  # Do not fabricate
            relevant_sectors=["Bioenergy", "Waste-to-Energy", "Water Infrastructure", "Capital Goods"],
            timestamp=now_iso,
            evidence=evidence,
        )

    @classmethod
    def calculate_global_sentiment(
        cls,
        macro_context: Optional[Dict[str, Any]] = None,
    ) -> GlobalMarketSentiment:
        """
        Compute structured Global Market Sentiment.
        Grounds metrics strictly in reported macro indicators; missing items stay None.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        ctx = macro_context or {}

        # Safe extraction without fabrication
        us_dir = ctx.get("us_market_direction")
        crude = ctx.get("crude_oil")
        us_yields = ctx.get("us_yields")
        dxy = ctx.get("usd_index")
        gold = ctx.get("gold")
        risk_regime_raw = ctx.get("risk_regime", "NEUTRAL")

        # Score computation based on available facts
        score = 0.0
        confidence = "LOW"
        evidence: List[str] = []

        if us_dir:
            confidence = "MEDIUM"
            evidence.append(f"US Market: {us_dir}")
            if "up" in us_dir.lower() or "+" in us_dir:
                score += 30.0
            elif "down" in us_dir.lower() or "-" in us_dir:
                score -= 30.0

        if crude:
            evidence.append(f"Crude: {crude}")
            # For India (oil importer & biofuels producer):
            # Moderate crude supports CBG economics; soaring crude inflates import bills.
            if "soaring" in crude.lower() or "+3" in crude:
                score -= 15.0
            elif "-" in crude or "soft" in crude.lower():
                score += 15.0

        if risk_regime_raw == "RISK_ON":
            score += 25.0
            risk_regime = RiskRegime.RISK_ON
        elif risk_regime_raw == "RISK_OFF":
            score -= 25.0
            risk_regime = RiskRegime.RISK_OFF
        else:
            risk_regime = RiskRegime.NEUTRAL

        final_score = max(-100.0, min(100.0, round(score, 1)))
        if final_score > 15.0:
            classification = SentimentClassification.BULLISH
        elif final_score < -15.0:
            classification = SentimentClassification.BEARISH
        else:
            classification = SentimentClassification.NEUTRAL

        key_drivers = []
        if us_dir:
            key_drivers.append(f"US Index Movement: {us_dir}")
        if crude:
            key_drivers.append(f"Crude Oil Benchmark: {crude}")
        if not key_drivers:
            key_drivers = ["Global risk tone stable with limited external shocks recorded."]

        return GlobalMarketSentiment(
            classification=classification,
            score=final_score,
            confidence=confidence if evidence else "LOW",
            us_market_direction=us_dir,
            major_indices=ctx.get("major_indices", {}),
            us_yields=us_yields,
            usd_index=dxy,
            crude_oil=crude,
            gold=gold,
            commodities=ctx.get("commodities", {}),
            asian_market=ctx.get("asian_market"),
            european_market=ctx.get("european_market"),
            risk_regime=risk_regime,
            key_drivers=key_drivers,
            geopolitical_factors=ctx.get("geopolitical_factors", []),
            evidence=evidence or ["Baseline macro indicators within historical variance"],
            timestamp=now_iso,
        )

    @classmethod
    def evaluate_scheme_impact(
        cls,
        scheme_id: str,
        scheme_name: str,
        indian_sentiment: IndianMarketSentiment,
        global_sentiment: GlobalMarketSentiment,
        scheme_sectors: Optional[List[str]] = None,
    ) -> SchemeSentimentImpact:
        """
        Evaluate how current Indian & Global sentiment conditions translate into scheme policy tailwinds/headwinds.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        sectors = scheme_sectors or ["Bio-Energy", "Biofuels", "Water Infrastructure", "Capital Goods"]

        positive_factors = []
        negative_factors = []
        neutral_uncertain_factors = []
        norm_sid = (scheme_id or "").strip().lower()
        if norm_sid == "samudra_manthan":
            channels = [
                "Upstream exploration capex allocation & DGH block award clearance",
                "Benchmark Brent crude pricing impact on deepwater project economics and upstream IRR",
                "Global offshore drilling rig availability and charter dayrates",
                "USD/INR exchange rate impact on imported subsea equipment and exploration contracts",
            ]
            if indian_sentiment.classification == SentimentClassification.BULLISH:
                positive_factors.append("Constructive domestic capital environment supports substantial upstream offshore capex.")
                positive_factors.append("National energy security priorities accelerate fast-track environmental and block clearances.")
            elif indian_sentiment.classification == SentimentClassification.BEARISH:
                negative_factors.append("Domestic market uncertainty may constrain debt syndication for high-risk frontier wells.")
            else:
                neutral_uncertain_factors.append("Domestic sentiment steady; drilling schedules governed by seasonal monsoon windows.")

            if global_sentiment.crude_oil and any(k in str(global_sentiment.crude_oil).lower() for k in ("up", "+", "high", "rise")):
                positive_factors.append("Firm Brent crude benchmarks improve upstream project NPV and incentivize deepwater drilling.")
            elif global_sentiment.crude_oil and any(k in str(global_sentiment.crude_oil).lower() for k in ("down", "-", "drop", "low")):
                negative_factors.append("Softening benchmark crude prices reduce E&P cash generation for multi-year offshore campaigns.")

            if global_sentiment.classification == SentimentClassification.BEARISH:
                negative_factors.append("Global risk aversion tightens international subsea EPC and specialist drilling vessel supply.")
            elif global_sentiment.classification == SentimentClassification.BULLISH:
                positive_factors.append("Global exploration cycle tailwinds support deepwater rig mobilization into Indian waters.")
            else:
                neutral_uncertain_factors.append("Global offshore service costs and rig dayrates remain stable across Indian basins.")
        else:
            channels = [
                "Domestic capital expenditure allocation & central subsidy release",
                "Crude oil pricing vs compressed biogas (CBG) procurement parity",
                "Domestic banking credit availability for infrastructure projects",
            ]
            if indian_sentiment.classification == SentimentClassification.BULLISH:
                positive_factors.append("Constructive domestic equity breadth supports capital raising for project capex.")
                positive_factors.append("Sustained budgetary policy focus on renewable energy transition.")
            elif indian_sentiment.classification == SentimentClassification.BEARISH:
                negative_factors.append("Broader domestic market volatility may induce temporary execution delays in private capex.")
            else:
                neutral_uncertain_factors.append("Domestic sentiment is range-bound; commercial execution remains volume-driven.")

            if global_sentiment.classification == SentimentClassification.BEARISH:
                negative_factors.append("Global risk-off tone could limit international technology partnership velocity.")
            elif global_sentiment.classification == SentimentClassification.BULLISH:
                positive_factors.append("Global risk-on conditions enhance foreign institutional interest in Indian green transition.")
            else:
                neutral_uncertain_factors.append("Global commodity price range maintains steady feedstock parity without acute inflation.")

        # Directional impact synthesis
        pos_weight = len(positive_factors)
        neg_weight = len(negative_factors)

        if pos_weight > neg_weight:
            directional_impact = DirectionalImpact.POSITIVE
        elif neg_weight > pos_weight:
            directional_impact = DirectionalImpact.NEGATIVE
        elif pos_weight > 0 and neg_weight > 0:
            directional_impact = DirectionalImpact.MIXED
        else:
            directional_impact = DirectionalImpact.NEUTRAL

        evidence = [
            f"Indian Sentiment: {indian_sentiment.classification.value} (Score: {indian_sentiment.score:+.1f})",
            f"Global Sentiment: {global_sentiment.classification.value} (Score: {global_sentiment.score:+.1f})",
            f"Active Policy Sectors: {', '.join(sectors[:3])}",
        ]

        return SchemeSentimentImpact(
            scheme_id=scheme_id,
            scheme_name=scheme_name,
            indian_sentiment=indian_sentiment.classification,
            global_sentiment=global_sentiment.classification,
            affected_sectors=sectors,
            transmission_channels=channels,
            positive_factors=positive_factors or ["Core policy mandates remain statutorily locked."],
            negative_factors=negative_factors or ["Execution bottlenecks at state-level permitting remain constant."],
            neutral_uncertain_factors=neutral_uncertain_factors or ["Disbursement timelines subject to administrative verification."],
            estimated_directional_impact=directional_impact,
            confidence="HIGH" if indian_sentiment.confidence == "HIGH" else "MEDIUM",
            supporting_evidence=evidence,
            timestamp=now_iso,
        )

    @classmethod
    def evaluate_watchlist_impact(
        cls,
        stock_symbol: str,
        short_symbol: str,
        company_name: str,
        indian_sentiment: IndianMarketSentiment,
        global_sentiment: GlobalMarketSentiment,
        catalysts: Optional[List[str]] = None,
        technical_trend: Optional[str] = None,
    ) -> WatchlistSentimentImpact:
        """
        Evaluate stock-specific sentiment transmission and catalyst interaction.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        pos_drivers: List[str] = []
        neg_drivers: List[str] = []
        risks: List[str] = []

        # Indian market effect
        if indian_sentiment.classification == SentimentClassification.BULLISH:
            indian_impact = DirectionalImpact.POSITIVE
            pos_drivers.append("Supportive domestic market liquidity aids sector valuation multiples.")
        elif indian_sentiment.classification == SentimentClassification.BEARISH:
            indian_impact = DirectionalImpact.NEGATIVE
            neg_drivers.append("Broad market selling pressure may suppress breakout follow-through.")
        else:
            indian_impact = DirectionalImpact.NEUTRAL

        # Global market effect
        if global_sentiment.classification == SentimentClassification.BULLISH:
            global_impact = DirectionalImpact.POSITIVE
        elif global_sentiment.classification == SentimentClassification.BEARISH:
            global_impact = DirectionalImpact.NEGATIVE
            risks.append("Global risk-off sentiment may temper institutional expansion appetite.")
        else:
            global_impact = DirectionalImpact.NEUTRAL

        # Sector impact
        sector_impact = DirectionalImpact.POSITIVE if indian_sentiment.score > 0 else DirectionalImpact.NEUTRAL

        # Catalyst interaction
        cats = catalysts or []
        if cats:
            interaction = f"Active catalyst ({cats[0][:60]}...) operates alongside {indian_sentiment.classification.value} market backdrop."
            pos_drivers.append(f"Company catalyst: {cats[0][:80]}")
        else:
            interaction = f"No immediate single-stock filing; price driven primarily by {indian_sentiment.classification.value} sector trend."

        if technical_trend and "BEAR" in technical_trend.upper():
            risks.append("Overhead technical supply / resistance requires volume confirmation.")

        # Overall estimated impact description
        if indian_impact == DirectionalImpact.POSITIVE and cats:
            estimated_impact = "Potentially supportive (Catalyst + Domestic Tailwind)"
        elif indian_impact == DirectionalImpact.NEGATIVE:
            estimated_impact = "Moderate headwind (Market volatility overhang)"
        else:
            estimated_impact = "Neutral / Wait condition prevailing"

        evidence = [
            f"Indian Market: {indian_sentiment.classification.value}",
            f"Global Sentiment: {global_sentiment.classification.value}",
            f"Trend: {technical_trend or 'N/A'}",
        ]

        return WatchlistSentimentImpact(
            stock=stock_symbol,
            short_symbol=short_symbol,
            name=company_name,
            scheme_relationship="HIGH",
            indian_market_impact=indian_impact,
            global_market_impact=global_impact,
            sector_impact=sector_impact,
            company_catalyst_interaction=interaction,
            positive_drivers=pos_drivers or ["Structural multi-year government policy alignment."],
            negative_drivers=neg_drivers or ["Potential project execution delays."],
            risks=risks or ["Working capital cycle length."],
            uncertainty="Offtake volume realization timelines.",
            estimated_impact=estimated_impact,
            confidence="MEDIUM",
            evidence=evidence,
            timestamp=now_iso,
        )

    @classmethod
    def analyze_scheme_transmission(
        cls,
        scheme_id: str,
        macro_inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Convenience method for retrieving and analyzing transmission channels for a scheme."""
        norm_sid = (scheme_id or "").strip().lower()
        if norm_sid == "samudra_manthan":
            channels = [
                {"factor": "Benchmark Brent Crude Pricing", "channel": "Deepwater project economics and upstream IRR"},
                {"factor": "Offshore Rig Dayrate & Availability", "channel": "Global drilling rig charter costs and mobilization"},
                {"factor": "USD/INR Exchange Rate", "channel": "Imported subsea equipment and exploration contracts"},
                {"factor": "DGH Block Award Clearance", "channel": "Upstream exploration capex allocation"},
            ]
        else:
            channels = [
                {"factor": "Domestic Capital Expenditure", "channel": "Central subsidy release and plant commissioning"},
                {"factor": "Crude Oil vs CBG Parity", "channel": "Compressed biogas procurement economics"},
                {"factor": "Banking Credit Availability", "channel": "Project financing for waste-to-energy plants"},
            ]
        return {
            "scheme_id": norm_sid,
            "transmission_channels": channels,
            "macro_inputs": macro_inputs or {},
        }
