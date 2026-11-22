"""serper provider: google search results (snippets only)."""
import threading
import time

import requests

from backend.recon.search.result import SearchResult

ENDPOINT = "https://google.serper.dev/search"
TIMEOUT = 30


# recon fires many queries at once and Serper answers a burst with 429: at most two in flight,
# and a rate-limited query waits (Retry-After when given) and tries again instead of being lost
_SLOTS = threading.BoundedSemaphore(2)
RETRIES = 3


def search(query, k=5, key=None):
    for attempt in range(RETRIES + 1):
        with _SLOTS:
            r = requests.post(
                ENDPOINT,
                headers={"X-API-KEY": key, "Content-Type": "application/json"},
                json={"q": query, "num": k},
                timeout=TIMEOUT,
            )
        if r.status_code != 429 or attempt == RETRIES:
            break
        wait = r.headers.get("Retry-After", "")
        time.sleep(float(wait) if wait.replace(".", "", 1).isdigit() else 2 * (attempt + 1))
    r.raise_for_status()
    out = []
    for hit in r.json().get("organic", []):
        out.append(SearchResult(
            url=hit.get("link", ""),
            title=hit.get("title", ""),
            snippet=hit.get("snippet", ""),
        ))
    return out
