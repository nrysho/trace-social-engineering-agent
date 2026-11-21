"""mark facts verified when two independent domains agree.

- group by (category, normalised value); a group spanning >=2 domains is verified
- the surviving fact keeps its best wording and lists the other urls as supporting
"""
from urllib.parse import urlsplit


def _domain(url):
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _key(fact):
    return (fact.category, " ".join(fact.value.lower().split())[:80])


def verify(facts):
    groups = {}
    for f in facts:
        groups.setdefault(_key(f), []).append(f)
    out = []
    for group in groups.values():
        domains = {_domain(f.source_url) for f in group if f.source_url}
        best = max(group, key=lambda f: f.confidence)  # keep the most confident wording
        best.verified = best.verified or len(domains) >= 2  # never downgrade an authoritative fact
        best.supporting_urls = sorted({f.source_url for f in group if f.source_url != best.source_url})
        out.append(best)
    return out
