"""infer the company's country, for picking a lookalike domain tld.

- a national cctld on the domain (.de, .co.uk) is a strong, free signal
- otherwise ask the llm to read the location clues already in the facts (hq, role
  and event locations) and name the single most likely country
- used so a sender or landing-page domain can match the target's tld (e.g. .de)
"""
import json

from backend import llm

# national cctlds we trust as a country signal; generic ones (.com/.io/.ai/.co) say nothing
CCTLD = {
    "de": "Germany", "at": "Austria", "ch": "Switzerland", "fr": "France",
    "uk": "United Kingdom", "nl": "Netherlands", "es": "Spain", "it": "Italy",
    "se": "Sweden", "no": "Norway", "dk": "Denmark", "fi": "Finland", "pl": "Poland",
    "ie": "Ireland", "be": "Belgium", "pt": "Portugal", "cz": "Czechia", "gr": "Greece",
    "sg": "Singapore", "in": "India", "au": "Australia", "ca": "Canada", "nz": "New Zealand",
    "jp": "Japan", "cn": "China", "br": "Brazil", "mx": "Mexico", "us": "United States",
}
# categories that reflect the company's OWN base (hq / office / role), so the country is
# not dragged off by event-venue cities or a partner's / portfolio company's location
LOC_CATS = ("role", "company", "hiring")

JSON_MODE = {"type": "json_object"}
SYSTEM = (
    "You infer the HQ country of ONE company from location clues, for an authorised "
    "research exercise. Return JSON only: {\"country\": \"...\"}. Give the single most "
    "likely country as its common English name (e.g. \"Germany\"), or \"\" if the clues "
    "do not support a confident guess. Do not guess from the company name alone."
)


def from_domain(domain):
    # a national cctld is decisive; generic tlds are not in the map and return ""
    if not domain:
        return ""
    tld = domain.rsplit(".", 1)[-1].lower()
    return CCTLD.get(tld, "")


def _llm_country(company, domain, clues):
    if not clues:
        return ""
    user = f"Company: {company} ({domain}).\n\nLocation clues:\n- " + "\n- ".join(clues)
    try:
        text = llm.chat([{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}], response_format=JSON_MODE, temperature=0)
        return str(json.loads(text).get("country", "")).strip()
    except Exception as e:
        print(f"  country inference failed: {e}")
        return ""


def resolve(company, domain, facts):
    # trust a national cctld first, else read the location clues in the facts
    tld_country = from_domain(domain)
    if tld_country and tld_country != "United States":  # .us is rare and often generic
        return tld_country
    clues = [f.value for f in facts if f.category in LOC_CATS][:30]
    return _llm_country(company, domain, clues) or tld_country
