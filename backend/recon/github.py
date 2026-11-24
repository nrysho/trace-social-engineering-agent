"""github as a gated recon source.

- our web search already surfaces a target's github url; enrich() pulls the
  structured profile (bio, company, languages, email, recent push) the rendered
  page does not expose, but only when the profile names the target's company
  (usernames are unreliable, so a name match alone is never trusted)
- facts() is a name-search fallback when no github url was found
- useful mainly for technical targets; it simply adds nothing when unconfirmed
"""
import re
from collections import Counter

import requests

from backend.recon import match
from core.schemas import Fact

API = "https://api.github.com"
TIMEOUT = 20
HEADERS = {"User-Agent": "recon-research", "Accept": "application/vnd.github+json"}
RESERVED = {"orgs", "about", "features", "topics", "collections", "sponsors",
            "marketplace", "pricing", "login", "settings", "notifications", "explore"}


def _get(path, **params):
    r = requests.get(f"{API}{path}", headers=HEADERS, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _from_login(login, anchor):
    # fetch the profile, confirm identity, then pull facts
    try:
        p = _get(f"/users/{login}")
    except requests.RequestException:
        return []
    if (p.get("type") or "User") != "User":  # skip organisations
        return []
    text = " ".join(str(p.get(k) or "") for k in ("name", "company", "bio", "blog", "location"))
    # github usernames and display names rarely match a real name, so the company is the
    # only trusted signal: accept the profile only if it names the target's company
    if not match._company_hit(anchor, text):
        return []
    return _profile_facts(p, login)


def enrich(url, anchor):
    # enrich a github url search already found
    m = re.search(r"github\.com/([A-Za-z0-9-]+)", url)
    if not m or m.group(1).lower() in RESERVED:
        return []
    return _from_login(m.group(1), anchor)


def facts(name, anchor, max_users=4):
    # fallback: search github for the name, return the first confirmed profile
    try:
        users = _get("/search/users", q=name, per_page=max_users).get("items", [])
    except requests.RequestException:
        return []
    for u in users:
        got = _from_login(u["login"], anchor)
        if got:
            return got
    return []


def _profile_facts(p, login):
    src = p.get("html_url", f"https://github.com/{login}")
    title = f"{p.get('name') or login} - GitHub"
    out = []

    def add(category, value, date="", confidence=0.7):
        if value:
            out.append(Fact(category, str(value).strip(), src, title, date=date, confidence=confidence))

    add("interests", p.get("bio"))
    add("company", (p.get("company") or "").lstrip("@"))
    add("interests", f"personal site: {p['blog']}" if p.get("blog") else "")
    add("network", f"based in {p['location']}" if p.get("location") else "", confidence=0.6)
    add("network", f"public email: {p['email']}" if p.get("email") else "", confidence=0.8)

    try:
        repos = _get(f"/users/{login}/repos", sort="pushed", per_page=10)
    except requests.RequestException:
        repos = []
    langs = [r.get("language") for r in repos if r.get("language")]
    top = [lang for lang, _ in Counter(langs).most_common(4)]
    add("interests", f"codes in {', '.join(top)}" if top else "")
    if repos:
        pushed = (repos[0].get("pushed_at") or "")[:7]  # YYYY-MM of the most recent push
        add("recent_activity", f"recently active on GitHub (repo {repos[0].get('name', '')})", date=pushed, confidence=0.6)
    return out
