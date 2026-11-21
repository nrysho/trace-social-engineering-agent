"""tavily provider: web results with cleaned page text.

- posts to the tavily search api with raw content on
- maps each hit to a SearchResult (raw_content as the page text when present)
"""
import requests

from backend.recon.search.result import SearchResult

ENDPOINT = "https://api.tavily.com/search"
TIMEOUT = 30


def search(query, k=5, key=None):
    r = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "query": query,
            "max_results": k,
            "search_depth": "basic",
            "include_raw_content": True,  # full page text, so extraction has more than a snippet
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for hit in r.json().get("results", []):
        out.append(SearchResult(
            url=hit.get("url", ""),
            title=hit.get("title", ""),
            snippet=hit.get("content", ""),        # tavily's short relevance snippet
            content=hit.get("raw_content") or "",  # the cleaned page text, may be empty
        ))
    return out
