from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .catalyst import classify
from .notifier import send_telegram
from .signals import make_setup
from .sources import fetch_rss, scan_page


ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config" / "watchlist.yaml").read_text(encoding="utf-8"))


def run(send: bool = False) -> dict:
    config = load_config()
    aliases = config["scheme"]["aliases"]
    articles = []
    for source in config["scheme"]["official_sources"]:
        # Add source-specific RSS URLs in config when available; page scan is intentionally conservative.
        articles.extend(scan_page(source["name"], source["url"], aliases))
    deduped = {article.url: article for article in articles if article.url}.values()
    catalysts = [item for article in deduped if (item := classify(article, config["stocks"]))]
    material = [item for item in catalysts if item.score >= config["settings"]["minimum_catalyst_score"]]
    setups = []
    for catalyst in material:
        for company in config["stocks"]:
            if company["name"] in catalyst.companies and company.get("symbol"):
                setup = make_setup(company["name"], company["symbol"], catalyst.score)
                if setup:
                    setups.append(setup.to_dict())
    report = {"catalysts": [{"title": c.article.title, "url": c.article.url, "score": c.score,
                               "category": c.category, "companies": c.companies} for c in material], "setups": setups}
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if send and material:
        lines = ["GOBARdhan / CBG catalyst alert"]
        lines.extend(f"• [{c.score}] {c.article.title}\n{c.article.url}" for c in material)
        if setups:
            lines.append("\nSetups require an entry trigger; this is research, not investment advice.")
            lines.extend(f"• {s['company']}: entry {s['entry']}, stop {s['stop']}, target {s['target']} ({s['status']})" for s in setups)
        send_telegram("\n".join(lines))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="send material alerts when Telegram secrets are configured")
    args = parser.parse_args()
    print(json.dumps(run(send=args.send), indent=2))


