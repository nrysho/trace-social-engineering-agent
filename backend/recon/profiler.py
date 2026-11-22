"""build a sourced profile: name + company -> facts, ranked hooks, exposure.

- search every query, read richer content, add dns + the linkedin anchor
- extract facts, verify across domains, propose hooks, score exposure
- write runs/profiles/<slug>.json (agents) and .md (humans), return the Profile
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend import config
from backend.recon import (queries, search, fetch, dns, tech, domains, linkedin, github, match,
                           extract, verify, hooks, exposure, render, recency, bench_osint, geo, channel)
from backend.recon import company as company_osint  # aliased: `company` is a param name in build()
from schemas import Profile

OUT = Path(__file__).resolve().parents[2] / "runs" / "profiles"
MAX_RESULTS = 24  # cap work so a run stays under the five-minute budget


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _host(url):
    return url.split("/")[2] if "://" in url else ""


def _best_linkedin(results, name):
    # prefer a profile whose slug carries the target's name tokens, not just the first /in/ hit
    toks = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if len(t) > 1]
    profiles = [r.url for r in results if "linkedin.com/in/" in r.url]
    for url in profiles:
        slug = url.split("/in/")[1].lower()
        if toks and all(t in slug for t in toks):
            return url
    return profiles[0] if profiles else ""


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


def _search_all(name, company):
    # run the query searches concurrently, then merge and dedup
    qs = queries.build_queries(name, company)
    results = []
    with ThreadPoolExecutor(max_workers=min(len(qs), 10)) as ex:
        for hits in ex.map(lambda q: search.search(q, k=5), qs):
            results += hits
    return search.dedup(results)[:MAX_RESULTS]


def _deepen(results):
    # fetch full page text for snippet-only results, concurrently (linkedin handled elsewhere)
    todo = [r for r in results if not r.content and "linkedin.com" not in r.url]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=min(len(todo), 10)) as ex:
        for r, text in zip(todo, ex.map(lambda r: fetch.fetch(r.url), todo)):
            r.content = text


def _extract(name, company, results, role):
    facts = extract.extract_facts(name, company, results, role)
    for f in facts:  # a real post timestamp beats the model's guessed date
        posted = linkedin.post_date(f.source_url)
        if posted:
            f.date = posted
    print(f"  {len(facts)} extracted facts")
    return facts


def _dns_tech(domain):
    # mail provider + spf vendors, plus txt tokens, m365 realm, website fingerprint
    if not domain:
        return []
    try:
        return dns.facts(domain) + tech.facts(domain)
    except Exception as e:
        print(f"  dns/tech failed: {e}")
        return []


def _linkedin_anchor(name, company, role, domain, results, env):
    li_url = _best_linkedin(results, name)
    if not (li_url and env.get("BRIGHTDATA_API_KEY")):
        return []
    try:
        rec = linkedin.profile(li_url, env["BRIGHTDATA_API_KEY"])
        if not rec:
            return []
        lname, lcompany = linkedin.name_and_company(rec)
        slug = li_url.split("/in/")[1].split("?")[0].replace("-", " ")  # the slug carries the full name
        ok, _, _ = match.judge(match.Anchor(name, company, domain=domain, role=role),
                               match.Candidate(slug, f"{lname} {lcompany}"), use_llm=False)
        if ok:
            print("  linkedin anchor confirmed")
            return linkedin.facts(rec, li_url)
        print("  linkedin profile did not match the target, skipped")
        return []
    except Exception as e:
        print(f"  linkedin failed: {e}")
        return []


def _github(name, company, role, domain, results):
    gh_url = next((r.url for r in results if "github.com/" in r.url and "/in/" not in r.url), "")
    if not gh_url:
        return []
    try:
        return github.enrich(gh_url, match.Anchor(name, company, domain=domain, role=role))
    except Exception as e:
        print(f"  github failed: {e}")
        return []


def build(name, company, role="", bench_target=None):
    env = config.load_env()
    domain = ""

    if bench_target:
        # bench personas are fictional: read their fake public pages instead of the live web,
        # and skip the live-only collectors (dns, tech, linkedin, github find nothing for them)
        results = bench_osint.pages(bench_target)
        print(f"  {len(results)} bench osint pages")
        facts = _extract(name, company, results, role)
    else:
        # 1. search all queries in parallel, then fetch snippet-only pages in parallel
        results = _search_all(name, company)
        print(f"  {len(results)} unique results")
        _deepen(results)
        domain = domains.resolve(company, results)

        # 2. extract and each structured collector are independent, so run them together
        facts = []
        with ThreadPoolExecutor(max_workers=5) as ex:
            jobs = [
                ex.submit(_extract, name, company, results, role),
                ex.submit(_dns_tech, domain),
                ex.submit(_linkedin_anchor, name, company, role, domain, results, env),
                ex.submit(_github, name, company, role, domain, results),
                ex.submit(company_osint.collect, company, domain),  # company facts: relationships etc.
            ]
            for j in jobs:
                facts += j.result()

    # 3. verify across domains, propose hooks, score exposure
    facts = verify.verify(facts)
    ranked = hooks.propose(name, company, facts)
    sc, breakdown = exposure.score(facts, ranked)
    print(f"  {len(facts)} facts after verify, {len(ranked)} hooks")

    facts.sort(key=lambda f: recency.weight(f.date), reverse=True)  # freshest first for the profile
    role = _current_role(facts, company, domain)
    country = geo.resolve(company, domain, facts)  # for choosing a lookalike domain tld
    pref = channel.infer(facts)  # best-guess contact channel, the evaluator refines it
    profile = Profile(
        name=name, role=role, company=company, domain=domain, country=country,
        preferred_channel=pref,
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
