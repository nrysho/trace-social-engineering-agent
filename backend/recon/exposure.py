"""exposure score: how much attackable surface the target presents.

- a deterministic 0-100 heuristic (no llm), returned with a per-metric breakdown
- measures surface, not a calibrated chance of success; constants are a first cut
"""
from urllib.parse import urlsplit

from schemas import FACT_CATEGORIES

CHANNEL_HINTS = ("linkedin", "twitter", "x.com", "@")  # a contactable handle showed up


def _domain(url):
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _recency_points(facts):
    # we rarely have parsed dates yet, so credit a recent_activity fact as a fresh signal
    return 15.0 if any(f.category == "recent_activity" for f in facts) else 5.0


def score(facts, hooks):
    verified = [f for f in facts if f.verified]
    domains = {_domain(f.source_url) for f in facts if f.source_url}
    categories = {f.category for f in facts}
    contactable = any(any(h in f"{f.source_url} {f.value}".lower() for h in CHANNEL_HINTS) for f in facts)
    top_hook = hooks[0].probability if hooks else 0.0

    breakdown = {
        "verified_facts": min(len(verified) / 8, 1) * 25,
        "category_breadth": len(categories) / len(FACT_CATEGORIES) * 20,
        "source_diversity": min(len(domains) / 10, 1) * 15,
        "recency": _recency_points(facts),
        "contactability": 15.0 if contactable else 0.0,
        "top_hook": top_hook * 10,
    }
    return round(sum(breakdown.values()), 1), {k: round(v, 1) for k, v in breakdown.items()}
