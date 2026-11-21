"""duckduckgo fallback: free, no key, best-effort scrape of the lite endpoint.

- the html endpoint returns a 202 bot challenge, but lite serves a plain table
- pull result links, titles and snippets with regex; decode the uddg redirect wrapper
- only used when no keyed provider returned anything; brittle by nature, may break
"""
import html
import re
from urllib.parse import parse_qs, unquote, urlsplit

import requests

from backend.recon.search.result import SearchResult

ENDPOINT = "https://lite.duckduckgo.com/lite/"
TIMEOUT = 30
# a real browser ua; the bot-looking one gets challenged
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

# lite layout: an anchor with class result-link (href wraps the real url in uddg=), then a result-snippet cell
LINK_RE = re.compile(r'href="(?P<href>[^"]*uddg=[^"]*)"\s+class=[\'"]result-link[\'"][^>]*>(?P<title>.*?)</a>', re.S)
SNIPPET_RE = re.compile(r'class=[\'"]result-snippet[\'"][^>]*>(?P<snip>.*?)</td>', re.S)
TAGS_RE = re.compile(r"<[^>]+>")


def _clean(text):
    return html.unescape(TAGS_RE.sub("", text)).strip()  # strip tags, decode entities


def _real_url(href):
    # ddg wraps links as ...?uddg=<encoded target>; unescape the &amp; then pull uddg out
    q = parse_qs(urlsplit(html.unescape(href)).query)
    return unquote(q["uddg"][0]) if q.get("uddg") else href


def search(query, k=5, key=None):
    r = requests.get(ENDPOINT, params={"q": query}, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    if r.status_code != 200 or any(marker in r.text.lower() for marker in ('challenge-form', 'anomaly.js', 'bots use duckduckgo')):
        raise RuntimeError('DuckDuckGo returned a challenge/non-result response; configure TAVILY_API_KEY or SERPER_API_KEY for recon')
    links = LINK_RE.findall(r.text)  # [(href, title), ...]
    snippets = SNIPPET_RE.findall(r.text)  # [snip, ...], usually one per link
    out = []
    for i, (href, title) in enumerate(links[:k]):
        out.append(SearchResult(
            url=_real_url(href),
            title=_clean(title),
            snippet=_clean(snippets[i]) if i < len(snippets) else "",
        ))
    return out
