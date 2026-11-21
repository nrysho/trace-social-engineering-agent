"""company-level osint: facts about the company, not the person.

- the person extractor is deliberately person-strict, so anything about the
  company (its partners, open roles, events) never lands there
- this collector hunts those with company-focused searches, reads the company's
  own pages, and emits each as a fact in the right category
- organised as a list of ASPECTS: each aspect is one kind of company fact with its
  own queries, seed pages, prompt and category, so a new one is a few lines
- why relationships matter: a real relationship is an impersonable sender identity.
  the writer can pose as a known partner or investor instead of inventing an agency
  the twin rejects ("we have no agreement with your agency")
"""
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from backend import llm
from backend.recon import search, fetch
from backend.recon.extract import _chunks, _slice, CHUNK, CONTENT_CHARS, MIN_CONF
from backend.recon.search.result import SearchResult
from schemas import Fact

POOL_CAP = 15  # bound the pages fed to the llm per aspect, so a run stays fast
JSON_MODE = {"type": "json_object"}


@dataclass
class Aspect:
    category: str       # the FACT_CATEGORIES bucket these facts go in
    queries: list       # company-centric query templates, "{company}" filled in
    seed_paths: tuple   # paths on the company's own domain to read directly
    system: str         # the extraction prompt for this aspect


# --- relationships: who the company works with --------------------------------
REL_SYSTEM = (
    "You research ONE company and extract its real business RELATIONSHIPS, for an "
    "authorised research exercise. Return JSON only: {\"facts\": [{\"value\": ..., "
    "\"source_url\": ..., \"date\": ..., \"confidence\": 0-1}]}. A relationship is a "
    "NAMED other party the company works with: a partner, a customer or client, an "
    "investor or backer, or a named service firm (PR, legal, recruiting, accounting, "
    "design). value names the other party and the relationship in one short sentence, "
    "e.g. 'Backed by Sequoia Capital' or 'Lists Siemens as a customer'. Extract ONLY "
    "relationships clearly stated for THIS company; never invent one, and never include "
    "the company's own products, features or employees. source_url MUST be copied exactly "
    "from a result. date is YYYY-MM (or YYYY) when stated, else \"\". confidence (0-1) is "
    "how sure you are it is a real, current relationship of this company."
)
RELATIONSHIPS = Aspect(
    category="network",
    queries=[
        '"{company}" partners OR partnership',
        '"{company}" customers OR clients OR "case study"',
        '"{company}" investors OR "backed by" OR funding OR raised',
        '"{company}" "partners with" OR announces',
        '"{company}" agency OR vendor OR supplier',
    ],
    seed_paths=("partners", "customers", "clients", "investors", "portfolio"),
    system=REL_SYSTEM,
)

# --- open roles: what the company is hiring for ------------------------------
ROLE_SYSTEM = (
    "You research ONE company and extract the specific OPEN ROLES it is currently "
    "hiring for, for an authorised research exercise. Return JSON only: {\"facts\": "
    "[{\"value\": ..., \"source_url\": ..., \"date\": ..., \"confidence\": 0-1}]}. value "
    "is one open role in a short phrase: the exact job title, plus team or location when "
    "stated, e.g. 'Hiring a Senior Backend Engineer (Berlin, Platform team)'. Extract "
    "ONLY roles the company itself is currently hiring for, one fact per distinct role; "
    "never invent a role, and never include filled positions, named employees, or roles "
    "at other companies. source_url MUST be copied exactly from a result. date is the "
    "posting date YYYY-MM when stated, else \"\". confidence (0-1) is how sure you are the "
    "role is a real, current opening at this company."
)
OPEN_ROLES = Aspect(
    category="hiring",
    queries=[
        '"{company}" careers OR jobs OR "open positions"',
        '"{company}" hiring OR "we are hiring" OR "join our team"',
        '"{company}" "apply now" OR vacancy OR vacancies',
        '"{company}" jobs greenhouse OR lever OR ashby OR workday OR personio',
    ],
    seed_paths=("careers", "jobs", "join", "join-us", "careers/jobs"),
    system=ROLE_SYSTEM,
)

# --- events: where the company is showing up ---------------------------------
EVENT_SYSTEM = (
    "You research ONE company and extract the EVENTS it is taking part in, for an "
    "authorised research exercise, so prefer upcoming or recent ones. Return JSON only: "
    "{\"facts\": [{\"value\": ..., \"source_url\": ..., \"date\": ..., \"confidence\": "
    "0-1}]}. An event is a named conference, trade show, summit, webinar or meetup the "
    "company exhibits at, sponsors, speaks at or hosts. value names the event and the "
    "company's part in one short phrase, e.g. 'Exhibiting at CES 2026 (Las Vegas)' or "
    "'Hosting a webinar on AI annotation'. Extract ONLY events clearly tied to THIS "
    "company; never invent one. source_url MUST be copied exactly from a result. date is "
    "the event date YYYY-MM (or YYYY) when stated, else \"\"; never guess. confidence "
    "(0-1) is how sure you are the company is really taking part."
)
EVENTS = Aspect(
    category="upcoming_events",
    queries=[
        '"{company}" event OR conference OR summit 2026',
        '"{company}" booth OR exhibitor OR exhibiting',
        '"{company}" sponsor OR keynote OR webinar',
        '"{company}" "will be at" OR "join us at" OR "meet us at"',
    ],
    seed_paths=("events", "news", "blog", "press", "events/upcoming"),
    system=EVENT_SYSTEM,
)

# every aspect the collector runs; a new kind of company fact is a new entry here
ASPECTS = [RELATIONSHIPS, OPEN_ROLES, EVENTS]


def _search_all(queries, company):
    # run an aspect's queries concurrently, then merge
    qs = [q.format(company=company) for q in queries]
    out = []
    with ThreadPoolExecutor(max_workers=len(qs)) as ex:
        for hits in ex.map(lambda q: search.search(q, k=5), qs):
            out += hits
    return out


def _seed_pages(domain, paths):
    # the company's own pages (partners, careers, ...), read straight off the domain
    if not domain:
        return []
    urls = [f"https://{domain}/{p}" for p in paths]
    out = []
    with ThreadPoolExecutor(max_workers=len(urls)) as ex:
        for url, text in zip(urls, ex.map(fetch.fetch, urls)):
            if text:  # a 404 or non-html page comes back empty, so drop it
                out.append(SearchResult(url=url, title=url.split("/")[-1], content=text))
    return out


def _gather(company, domain, queries, seed_paths):
    # seed pages first so the company's own lists survive the cap, then searches
    pool = search.dedup(_seed_pages(domain, seed_paths) + _search_all(queries, company))
    # read snippet-only pages so the model sees real lists, not a teaser
    todo = [r for r in pool if not r.content and "linkedin.com" not in r.url]
    if todo:
        with ThreadPoolExecutor(max_workers=min(len(todo), 10)) as ex:
            for r, text in zip(todo, ex.map(fetch.fetch, todo)):
                r.content = text
    return pool[:POOL_CAP]


def _extract_chunk(company, batch, urls, titles, system, category):
    block = "\n\n".join(
        f"URL: {r.url}\nTITLE: {r.title}\nTEXT: {(r.content or r.snippet)[:CONTENT_CHARS]}"
        for r in batch
    )
    user = f"Company: {company}.\n\nResults:\n{block}"
    try:
        text = llm.chat([{"role": "system", "content": system},
                         {"role": "user", "content": user}], response_format=JSON_MODE, temperature=0)
        data = json.loads(_slice(text))
    except Exception as e:
        print(f"  company extract chunk failed: {e}")
        return []
    out = []
    for f in data.get("facts", []):
        url = f.get("source_url", "")
        if url in urls and f.get("value") and float(f.get("confidence", 0.5)) >= MIN_CONF:
            out.append(Fact(
                category=category, value=str(f["value"]).strip(),
                source_url=url, source_title=titles.get(url, ""),
                date=str(f.get("date", "")).strip(),
                confidence=float(f.get("confidence", 0.5)),
            ))
    return out


def _extract_pool(company, pool, system, category):
    urls = {r.url for r in pool}
    titles = {r.url: r.title for r in pool}
    out = []
    for batch in _chunks(pool, CHUNK):  # sequential: concurrent openai calls get rate-limited
        out += _extract_chunk(company, batch, urls, titles, system, category)
    return out


def collect(company, domain):
    # all company facts across the aspects; [] when there is nothing to go on
    if not company:
        return []
    # gather each aspect's pages in parallel (http), then extract sequentially (bounded llm)
    with ThreadPoolExecutor(max_workers=len(ASPECTS)) as ex:
        pools = list(ex.map(lambda a: _gather(company, domain, a.queries, a.seed_paths), ASPECTS))
    out = []
    for aspect, pool in zip(ASPECTS, pools):
        out += _extract_pool(company, pool, aspect.system, aspect.category)
    print(f"  {len(out)} company facts")
    return out
