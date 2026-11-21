"""web search for recon.

- one search() chains providers: tavily and serper (keyed), ddg as a free fallback
- merge results and dedup by url, so two engines feed the two-source check
- a missing key or a failed provider is skipped, never fatal
"""
from urllib.parse import urlsplit, urlunsplit

from backend import config
from backend.recon.search.result import SearchResult
from backend.recon.search import tavily, serper, ddg

__all__ = ["SearchResult", "search"]


def search(query, k=5):
    env = config.load_env()
    results = []
    if env.get("TAVILY_API_KEY"):
        results += _safe(tavily.search, query, k, env["TAVILY_API_KEY"])
    if env.get("SERPER_API_KEY"):
        results += _safe(serper.search, query, k, env["SERPER_API_KEY"])
    if not results:  # nothing keyed worked, fall back to the free engine
        results += _safe(ddg.search, query, k, None)
    return _dedup(results)


def _safe(fn, query, k, key):
    # a provider error must never kill the run; skip it and say why
    try:
        return fn(query, k, key)
    except Exception as e:
        print(f"  search provider {fn.__module__} failed: {e}")
        return []


def _norm(url):
    # drop fragment and trailing slash so the same page from two engines dedups
    s = urlsplit(url)
    return urlunsplit((s.scheme.lower(), s.netloc.lower(), s.path.rstrip("/"), s.query, ""))


def _dedup(results):
    # keep one per normalised url, preferring the copy that carries page content
    by_url = {}
    for r in results:
        if not r.url:
            continue
        key = _norm(r.url)
        if key not in by_url:
            by_url[key] = r
        elif not by_url[key].content and r.content:
            by_url[key] = r  # upgrade to the richer copy
    return list(by_url.values())


def dedup(results):
    # public alias so other modules can merge result lists
    return _dedup(results)
