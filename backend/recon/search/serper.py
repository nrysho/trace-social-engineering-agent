"""serper provider: google search results (snippets only)."""
import requests

from backend.recon.search.result import SearchResult

ENDPOINT = "https://google.serper.dev/search"
TIMEOUT = 30


def search(query, k=5, key=None):
    r = requests.post(
        ENDPOINT,
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json={"q": query, "num": k},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for hit in r.json().get("organic", []):
        out.append(SearchResult(
            url=hit.get("link", ""),
            title=hit.get("title", ""),
            snippet=hit.get("snippet", ""),
        ))
    return out
