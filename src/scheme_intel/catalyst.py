from __future__ import annotations

from .models import Article, Catalyst

MATERIAL_EVENTS = {
    "cabinet approval": (95, "policy approval"),
    "funds released": (90, "fund release"),
    "fund release": (90, "fund release"),
    "letter of award": (90, "contract award"),
    "contract awarded": (90, "contract award"),
    "tender awarded": (85, "tender award"),
    "commercial operation": (85, "commissioning"),
    "commissioned": (80, "commissioning"),
    "procurement price": (75, "pricing"),
    "blending obligation": (75, "demand policy"),
    "tender": (60, "tender"),
    "memorandum of understanding": (45, "memorandum"),
}


def classify(article: Article, companies: list[dict]) -> Catalyst | None:
    text = f"{article.title} {article.summary}".lower()
    match = max(
        ((score, category, term) for term, (score, category) in MATERIAL_EVENTS.items() if term in text),
        default=None,
    )
    if not match:
        return None
    score, category, term = match
    names = []
    for company in companies:
        aliases = [company["name"], *company.get("aliases", [])]
        if any(alias.lower() in text for alias in aliases):
            names.append(company["name"])
    rationale = f"Detected {category} language ('{term}') in {article.source}."
    return Catalyst(article, score, category, rationale, tuple(names))


