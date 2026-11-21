"""verify facts by grouping the same claim, then counting independent domains.

- an llm groups facts that state the same thing even when worded differently
- a group is verified only when >=2 distinct domains carry it (llm groups, domains decide)
- a claim a source disputes is annotated and left unverified, to dodge the wrong-fact penalty
- falls back to exact-value grouping if the llm call fails
"""
import json
import re
from urllib.parse import urlsplit

from backend import llm

JSON_MODE = {"type": "json_object"}

SYSTEM = (
    "You group facts that make the IDENTICAL specific claim about one person, differing only in "
    "wording. Return JSON only: {\"groups\": [{\"members\": [indices], \"dispute\": \"\"}]}. Every "
    "index 0..N-1 appears in exactly one group. Only merge facts asserting the same attribute AND "
    "the same value (e.g. two phrasings of one job title). Keep distinct claims separate: different "
    "events, podcasts, clients, companies or topics are DIFFERENT claims even in one category; when "
    "unsure, keep them apart. If a group's claim is contradicted by another fact (for example a "
    "different city or title), set its \"dispute\" to a short note; otherwise leave it empty."
)


def _domain(url):
    return urlsplit(url).netloc.lower().removeprefix("www.")


def verify(facts):
    if not facts:
        return []
    groups = _llm_groups(facts) or _exact_groups(facts)
    out = []
    for members, dispute in groups:
        group = [facts[i] for i in members if 0 <= i < len(facts)]
        if not group:
            continue
        best = max(group, key=lambda f: f.confidence)  # keep the most confident wording
        domains = {_domain(f.source_url) for f in group if f.source_url}
        best.supporting_urls = sorted({f.source_url for f in group if f.source_url != best.source_url})
        if dispute:
            best.verified = False  # a contested claim is never verified
            if "[disputed" not in best.value:
                best.value = f"{best.value} [disputed: {dispute}]"
        else:
            best.verified = best.verified or len(domains) >= 2  # never downgrade an authoritative fact
        out.append(best)
    return out


def _llm_groups(facts):
    listing = "\n".join(f"{i}. [{f.category}] {f.value} ({_domain(f.source_url)})" for i, f in enumerate(facts))
    try:
        text = llm.chat([{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": listing}], response_format=JSON_MODE, temperature=0)
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    except Exception as e:
        print(f"  verify llm failed, using exact grouping: {e}")
        return None
    groups, seen = [], set()
    for g in data.get("groups", []):
        members = [i for i in g.get("members", []) if isinstance(i, int) and i not in seen]
        if members:
            seen.update(members)
            groups.append((members, str(g.get("dispute", "")).strip()))
    for i in range(len(facts)):  # any fact the model dropped becomes its own group
        if i not in seen:
            groups.append(([i], ""))
    return groups


def _exact_groups(facts):
    # deterministic fallback: group by (category, normalised value)
    buckets = {}
    for i, f in enumerate(facts):
        key = (f.category, " ".join(f.value.lower().split())[:80])
        buckets.setdefault(key, []).append(i)
    return [(members, "") for members in buckets.values()]
