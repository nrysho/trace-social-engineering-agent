"""linkedin anchor via bright data's scraper api.

- bright data scrapes a public linkedin profile url (search gives us the url)
- the /scrape endpoint returns the record directly for one url, no polling
- the profile's name + current company become the anchor the match gate trusts
"""
import json

import requests

from schemas import Fact

DATASET = "gd_l1viktl72bvl7bjuj0"  # bright data's linkedin people-profile dataset
SCRAPE = "https://api.brightdata.com/datasets/v3/scrape"
TIMEOUT = 120  # scraping a live profile can take a while


def _first_record(text):
    # /scrape may return a json array or newline-delimited json; take the first object
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return (data[0] if data else None) if isinstance(data, list) else data
    except json.JSONDecodeError:
        return json.loads(text.splitlines()[0])  # ndjson


def profile(url, key):
    # return the bright data record (dict) for a linkedin profile url, or None
    r = requests.post(
        SCRAPE,
        headers={"Authorization": f"Bearer {key}"},
        params={"dataset_id": DATASET, "format": "json"},
        json=[{"url": url}],
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    rec = _first_record(r.text)
    if not rec or rec.get("error") or rec.get("warning"):
        return None
    return rec


def name_and_company(rec):
    # the two fields the match gate uses to confirm this is our target
    company = rec.get("current_company_name") or (rec.get("current_company") or {}).get("name", "")
    return rec.get("name", ""), company


def facts(rec, url=""):
    # map the useful profile fields to sourced facts
    src = url or rec.get("input_url") or rec.get("url", "")
    title = f"{rec.get('name', '')} - LinkedIn"
    out = []

    _, company = name_and_company(rec)
    if company:
        position = rec.get("position") or ""
        role = f"{position} at {company}" if position else f"Works at {company}"
        out.append(Fact("role", role, src, title, confidence=0.85))
        out.append(Fact("company", company, src, title, confidence=0.9))

    about = (rec.get("about") or "").strip()
    if about:
        out.append(Fact("interests", about[:300], src, title, confidence=0.6))

    for post in (rec.get("posts") or [])[:2]:
        headline = (post.get("title") or "").strip()
        if headline:
            out.append(Fact("recent_activity", f"Posted: {headline}", src, title, confidence=0.6))

    return out
