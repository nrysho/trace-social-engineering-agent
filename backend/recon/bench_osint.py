"""read a bench persona's public pages so recon can profile fictional targets.

- bench personas are made up, so they are not on the real web
- GET /bench/osint/<target> stands in for the public web (title + text per page)
- return those pages as SearchResult, the same shape web search hands the profiler
- target_info reads the agent-visible name + role from /v1/scenarios, never ground truth
"""
import os

import requests

from backend.recon.search.result import SearchResult

DEFAULT_BASE = "http://127.0.0.1:8770"  # bench server default, see bench/server.py
TIMEOUT = 20


def base_url(env=None):
    # BENCH_API_URL wins if set, else the bench's default local address; we want the host root
    env = env if env is not None else os.environ
    url = env.get("BENCH_API_URL") or DEFAULT_BASE
    return url.removesuffix("/v1").rstrip("/")  # callers may set the /v1 api base, strip it


def pages(target, base=None):
    # fetch the persona's fake public pages as search results (osint takes no auth)
    root = base or base_url()
    r = requests.get(f"{root}/bench/osint/{target}", timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for p in r.json().get("pages", []):
        text = p.get("text", "")
        # content is set, so the profiler's _deepen skips the live fetch for these
        out.append(SearchResult(url=p.get("url", ""), title=p.get("title", ""),
                                snippet=text[:300], content=text))
    return out


def target_info(target, base=None):
    # agent-visible id/name/role from /v1/scenarios (any bearer is accepted on the bench)
    root = base or base_url()
    r = requests.get(f"{root}/v1/scenarios", headers={"Authorization": "Bearer bench"}, timeout=TIMEOUT)
    r.raise_for_status()
    for sc in r.json():
        for t in sc.get("targets", []):
            if t.get("id") == target:
                return t
    return {}
