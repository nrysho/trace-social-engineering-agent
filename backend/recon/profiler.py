"""build a sourced profile: name + company -> facts, ranked hooks, exposure.

- search every query, read richer content, add dns + the linkedin anchor
- extract facts, verify across domains, propose hooks, score exposure
- write runs/profiles/<slug>.json (agents) and .md (humans), return the Profile
"""
import json
import re
from pathlib import Path

from backend import config
from backend.recon import (queries, search, fetch, dns, linkedin, match,
                           extract, verify, hooks, exposure, render, recency)
from schemas import Profile

OUT = Path(__file__).resolve().parents[2] / "runs" / "profiles"
MAX_RESULTS = 24  # cap work so a run stays under the five-minute budget


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _host(url):
    return url.split("/")[2] if "://" in url else ""


def _domain_from(company, results):
    # guess the company domain from the first result host that contains the company token
    token = re.sub(r"[^a-z0-9]", "", company.lower())
    for r in results:
        host = _host(r.url).removeprefix("www.")
        if token and token in host.replace(".", ""):
            return host
    return ""


def _current_role(facts, company, domain):
    # prefer a role at the given (current) company, then one marked present, then the most recent
    roles = [f for f in facts if f.category == "role"]
    if not roles:
        return ""
    anchor = match.Anchor("", company, domain)
    key = lambda f: (match._company_hit(anchor, f.value), f.date.lower() == "present", recency.weight(f.date))
    return max(roles, key=key).value


def build(name, company):
    env = config.load_env()

    # 1. search every query, merge and dedup, then cap
    results = []
    for q in queries.build_queries(name, company):
        results += search.search(q, k=5)
    results = search.dedup(results)[:MAX_RESULTS]
    print(f"  {len(results)} unique results")

    # 2. deepen: fetch full text where we only have a snippet (skip linkedin, handled below)
    for r in results:
        if not r.content and "linkedin.com" not in r.url:
            r.content = fetch.fetch(r.url)

    # 3. extract sourced facts from the results
    facts = extract.extract_facts(name, company, results)
    for f in facts:  # a real post timestamp beats the model's guessed date
        posted = linkedin.post_date(f.source_url)
        if posted:
            f.date = posted
    print(f"  {len(facts)} extracted facts")

    # 4. structured collectors: company domain -> dns; a linkedin url -> the anchor
    domain = _domain_from(company, results)
    if domain:
        try:
            facts += dns.facts(domain)
        except Exception as e:
            print(f"  dns failed: {e}")
    li_url = next((r.url for r in results if "linkedin.com/in/" in r.url), "")
    if li_url and env.get("BRIGHTDATA_API_KEY"):
        try:
            rec = linkedin.profile(li_url, env["BRIGHTDATA_API_KEY"])
            if rec:
                lname, lcompany = linkedin.name_and_company(rec)
                ok, _, _ = match.judge(match.Anchor(name, company),
                                       match.Candidate(lname, lcompany), use_llm=False)
                if ok:
                    facts += linkedin.facts(rec, li_url)
                    print("  linkedin anchor confirmed")
                else:
                    print("  linkedin profile did not match the target, skipped")
        except Exception as e:
            print(f"  linkedin failed: {e}")

    # 5. verify across domains, propose hooks, score exposure
    facts = verify.verify(facts)
    ranked = hooks.propose(name, company, facts)
    sc, breakdown = exposure.score(facts, ranked)
    print(f"  {len(facts)} facts after verify, {len(ranked)} hooks")

    facts.sort(key=lambda f: recency.weight(f.date), reverse=True)  # freshest first for the profile
    role = _current_role(facts, company, domain)
    profile = Profile(
        name=name, role=role, company=company, domain=domain,
        facts=facts, hooks=ranked, exposure_score=sc, exposure_breakdown=breakdown,
        sources=sorted({f.source_url for f in facts if f.source_url}),
    )
    _write(profile)
    return profile


def _write(profile):
    OUT.mkdir(parents=True, exist_ok=True)
    slug = _slug(profile.name)
    (OUT / f"{slug}.json").write_text(json.dumps(profile.to_dict(), indent=2))
    (OUT / f"{slug}.md").write_text(render.to_markdown(profile))
    print(f"  wrote {OUT / (slug + '.json')} and .md")
