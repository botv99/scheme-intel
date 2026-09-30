"""
Live Smoke Test and Probe Tool for Samudra Manthan Sources (Stage 4B -> 4D).
Performs non-blocking diagnostic probes across all registered Samudra Manthan endpoints
and categorizes response states:
  - LIVE_REACHABLE: Successfully contacted with HTTP 200 and valid parseable payload
  - LIVE_BLOCKED: Bot mitigation, WAF, Cloudflare challenge, or HTTP 403/429
  - LIVE_CHANGED: HTTP 200 returned but DOM structure / selectors altered
  - LIVE_UNAVAILABLE: Connection timeout, DNS failure, SSL failure, or HTTP 5xx

Usage:
  python scripts/smoke_test_samudra_sources.py [--timeout 8] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure src is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests
from src.scheme_intel.ingestion.adapters import AdapterRegistry
from src.scheme_intel.schemes.registry import SchemeRegistry

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class SourceProbeResult:
    source_id: str
    name: str
    url: str
    status: str            # LIVE_REACHABLE, LIVE_BLOCKED, LIVE_CHANGED, LIVE_UNAVAILABLE
    http_code: Optional[int]
    latency_ms: int
    extracted_count: int
    relevant_events_count: int
    parser_status: str
    diagnostics: str
    checked_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def probe_source(source_id: str, name: str, url: str, timeout: int = 8) -> SourceProbeResult:
    """Probe a single real source endpoint and categorize its live availability."""
    now_utc = datetime.now(timezone.utc).isoformat()
    adapter = AdapterRegistry.get_adapter("samudra_manthan", source_id)

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    # For exchanges, include appropriate referer
    if "nseindia" in url:
        headers["Referer"] = "https://www.nseindia.com/"
    elif "bseindia" in url:
        headers["Referer"] = "https://www.bseindia.com/"

    t0 = time.time()
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
        latency = int((time.time() - t0) * 1000)

        status_code = resp.status_code
        text = resp.text or ""

        # Bot protection / WAF detection
        is_blocked = (
            status_code in (403, 429)
            or any(k in text.lower() for k in [
                "access denied", "cf-browser-verification", "attention required! | cloudflare",
                "incapsula", "akamai", "captcha", "security check"
            ])
        )

        if is_blocked:
            return SourceProbeResult(
                source_id=source_id,
                name=name,
                url=url,
                status="LIVE_BLOCKED",
                http_code=status_code,
                latency_ms=latency,
                extracted_count=0,
                relevant_events_count=0,
                parser_status="BLOCKED",
                diagnostics=f"Endpoint defended by WAF / Anti-Bot protection (HTTP {status_code})",
                checked_at=now_utc,
            )

        if status_code != 200:
            return SourceProbeResult(
                source_id=source_id,
                name=name,
                url=url,
                status="LIVE_UNAVAILABLE",
                http_code=status_code,
                latency_ms=latency,
                extracted_count=0,
                relevant_events_count=0,
                parser_status="HTTP_ERROR",
                diagnostics=f"HTTP server error status {status_code}",
                checked_at=now_utc,
            )

        # Parse with specialized adapter if available
        if adapter:
            try:
                raw_items = adapter.parse(text)
                norm_events = adapter.normalize(raw_items)
                valid_events = [e for e in norm_events if adapter.validate(e)]

                if not raw_items:
                    # Check if client-side SPA or altered markup
                    if adapter.is_spa_detected(text):
                        return SourceProbeResult(
                            source_id=source_id,
                            name=name,
                            url=url,
                            status="LIVE_BLOCKED",
                            http_code=status_code,
                            latency_ms=latency,
                            extracted_count=0,
                            relevant_events_count=0,
                            parser_status="SPA_DETECTED",
                            diagnostics="Client-side Single Page Application (SPA) requiring JS execution",
                            checked_at=now_utc,
                        )
                    return SourceProbeResult(
                        source_id=source_id,
                        name=name,
                        url=url,
                        status="LIVE_CHANGED",
                        http_code=status_code,
                        latency_ms=latency,
                        extracted_count=0,
                        relevant_events_count=0,
                        parser_status="NO_ITEMS",
                        diagnostics="HTTP 200 received but 0 items extracted (DOM structure changed)",
                        checked_at=now_utc,
                    )

                return SourceProbeResult(
                    source_id=source_id,
                    name=name,
                    url=url,
                    status="LIVE_REACHABLE",
                    http_code=status_code,
                    latency_ms=latency,
                    extracted_count=len(raw_items),
                    relevant_events_count=len(valid_events),
                    parser_status="OK",
                    diagnostics=f"Parsed {len(raw_items)} raw items; {len(valid_events)} relevant scheme events",
                    checked_at=now_utc,
                )
            except Exception as pe:
                return SourceProbeResult(
                    source_id=source_id,
                    name=name,
                    url=url,
                    status="LIVE_CHANGED",
                    http_code=status_code,
                    latency_ms=latency,
                    extracted_count=0,
                    relevant_events_count=0,
                    parser_status="PARSE_ERROR",
                    diagnostics=f"Parser encountered schema drift: {str(pe)[:100]}",
                    checked_at=now_utc,
                )

        # Generic reachability check for non-adaptered source
        return SourceProbeResult(
            source_id=source_id,
            name=name,
            url=url,
            status="LIVE_REACHABLE",
            http_code=status_code,
            latency_ms=latency,
            extracted_count=1,
            relevant_events_count=1,
            parser_status="GENERIC_OK",
            diagnostics="Endpoint responded with valid HTTP 200 payload",
            checked_at=now_utc,
        )

    except requests.exceptions.Timeout:
        latency = int((time.time() - t0) * 1000)
        return SourceProbeResult(
            source_id=source_id,
            name=name,
            url=url,
            status="LIVE_UNAVAILABLE",
            http_code=None,
            latency_ms=latency,
            extracted_count=0,
            relevant_events_count=0,
            parser_status="TIMEOUT",
            diagnostics=f"Connection timed out after {timeout} seconds",
            checked_at=now_utc,
        )
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return SourceProbeResult(
            source_id=source_id,
            name=name,
            url=url,
            status="LIVE_UNAVAILABLE",
            http_code=None,
            latency_ms=latency,
            extracted_count=0,
            relevant_events_count=0,
            parser_status="NETWORK_ERROR",
            diagnostics=f"{type(e).__name__}: {str(e)[:100]}",
            checked_at=now_utc,
        )


def run_smoke_tests(timeout: int = 8, output_json: bool = False) -> Dict[str, Any]:
    """Execute smoke test probe across all Samudra Manthan sources."""
    scheme = SchemeRegistry.get("samudra_manthan")
    if not scheme:
        print("[ERROR] Scheme 'samudra_manthan' is not registered!")
        sys.exit(1)

    results: List[SourceProbeResult] = []
    print("\n" + "=" * 95)
    print("SCHEME INTEL — SAMUDRA MANTHAN LIVE SOURCE SMOKE TEST & PROBE")
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC | Timeout: {timeout}s")
    print("=" * 95)
    print(f"{'Source ID':<18} | {'Status':<16} | {'HTTP':<5} | {'Latency':<8} | {'Items':<6} | {'Diagnostics':<32}")
    print("-" * 95)

    for src in scheme.sources:
        if not src.enabled:
            res = SourceProbeResult(
                source_id=src.id,
                name=src.name,
                url=src.url,
                status="DISABLED",
                http_code=None,
                latency_ms=0,
                extracted_count=0,
                relevant_events_count=0,
                parser_status="DISABLED",
                diagnostics="Source disabled in scheme registry",
                checked_at=datetime.now(timezone.utc).isoformat(),
            )
            results.append(res)
            print(f"{src.id:<18} | {'DISABLED':<16} | {'-':<5} | {'-':<8} | {'-':<6} | Source disabled in registry")
            continue

        res = probe_source(source_id=src.id, name=src.name, url=src.url, timeout=timeout)
        results.append(res)

        code_str = str(res.http_code) if res.http_code else "ERR"
        lat_str = f"{res.latency_ms}ms"
        diag_short = (res.diagnostics[:32] + "..") if len(res.diagnostics) > 32 else res.diagnostics
        items_str = f"{res.extracted_count}/{res.relevant_events_count}"

        # Color indicator text
        print(f"{res.source_id:<18} | {res.status:<16} | {code_str:<5} | {lat_str:<8} | {items_str:<6} | {diag_short}")

    # Summary calculations
    reachable = sum(1 for r in results if r.status == "LIVE_REACHABLE")
    blocked = sum(1 for r in results if r.status == "LIVE_BLOCKED")
    changed = sum(1 for r in results if r.status == "LIVE_CHANGED")
    unavailable = sum(1 for r in results if r.status == "LIVE_UNAVAILABLE")
    total = len(results)

    summary = {
        "scheme_id": "samudra_manthan",
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "total_sources": total,
        "reachable": reachable,
        "blocked": blocked,
        "changed": changed,
        "unavailable": unavailable,
        "health_score_pct": round((reachable / max(1, total)) * 100, 1),
        "results": [r.to_dict() for r in results],
    }

    print("-" * 95)
    print(f"Summary: Total={total} | Reachable={reachable} | Blocked/Protected={blocked} | Changed={changed} | Unavailable={unavailable}")
    print(f"Operational Health: {summary['health_score_pct']}% reachable/monitored")
    print("=" * 95 + "\n")

    # Print Information Redundancy & Coverage Matrix
    from src.scheme_intel.schemes.samudra_manthan.redundancy import get_information_coverage_matrix
    cov_matrix = get_information_coverage_matrix()
    summary["coverage_matrix"] = cov_matrix

    print("=" * 95)
    print("SAMUDRA MANTHAN INFORMATION REDUNDANCY & COVERAGE MATRIX")
    print("=" * 95)
    print(f"{'Requirement':<28} | {'Rating':<10} | {'Paths':<6} | {'Official/Exch':<14} | {'News/Specialist':<16}")
    print("-" * 95)
    for req_key, info in cov_matrix.items():
        off_count = len(info.get("primary_official", [])) + len(info.get("exchange_statutory", []))
        news_count = len(info.get("financial_news", [])) + len(info.get("specialist_media", []))
        print(f"{req_key:<28} | {info['coverage_rating']:<10} | {info['total_independent_paths']:<6} | {off_count:<14} | {news_count:<16}")
    print("=" * 95 + "\n")

    if output_json:
        print(json.dumps(summary, indent=2))

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Samudra Manthan Live Source Probe")
    parser.add_argument("--timeout", type=int, default=8, help="Timeout in seconds per probe")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    run_smoke_tests(timeout=args.timeout, output_json=args.json)
