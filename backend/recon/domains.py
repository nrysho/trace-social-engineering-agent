"""resolve a company's primary web domain.

- prefer a search-result host that contains the company name and is not a social/aggregator site
- used to seed dns, the tech-stack probe, and the profile
"""
import re
from urllib.parse import urlsplit

from backend.recon import search

# hosts that are never a company's own domain
SKIP = ("linkedin.", "twitter.", "x.com", "facebook.", "instagram.", "youtube.", "youtu.be",
        "crunchbase.", "wikipedia.", "github.", "gitlab.", "medium.", "bloomberg.", "glassdoor.",
        "indeed.", "pitchbook.", "tracxn.", "reddit.", "tiktok.", "apple.com", "play.google",
        "amazon.", "substack.", "notion.site", "devpost.", "producthunt.", "ycombinator.")


def _host(url):
    return urlsplit(url).netloc.lower().removeprefix("www.")


def resolve(company, results=None):
    # the first non-social host whose name contains the company token
    token = re.sub(r"[^a-z0-9]", "", company.lower())
    pool = results if results is not None else search.search(f"{company} official website", k=6)
    for r in pool:
        host = _host(r.url)
        if not host or any(s in host for s in SKIP):
            continue
        if token and token in host.replace(".", "").replace("-", ""):
            return host
    if results is not None:  # the main results had no match, try a dedicated search
        return resolve(company, None)
    return ""
