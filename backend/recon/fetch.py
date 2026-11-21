"""fetch a url and return clean readable text.

- plain requests with a browser ua, then strip script/style bodies and tags
- used to read pages search only gave a snippet for, and to pull seed pages
- best-effort: a blocked or non-html page returns "", never raises to the caller
"""
import html
import re

import requests

TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
TAGS = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def fetch(url, max_chars=12000):
    # return readable text, or "" if the page can't be read
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException:
        return ""
    if "html" not in r.headers.get("Content-Type", "").lower():
        return ""  # skip pdfs, images, json for now
    body = SCRIPT_STYLE.sub(" ", r.text)  # drop script/style bodies first
    text = html.unescape(WS.sub(" ", TAGS.sub(" ", body))).strip()
    return text[:max_chars]  # cap so extraction prompts stay bounded
