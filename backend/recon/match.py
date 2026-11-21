"""disambiguation gate: is a candidate really our target.

- anchors are the few things we are sure of: the name and the company
- a candidate (from github, podcasts, a people-data api) is accepted only if it
  matches the anchors well enough, so noisy sources never add the wrong person
- cheap string checks decide the clear cases; an llm judge only for borderline ones
"""
import json
import re
from dataclasses import dataclass

from backend import llm


@dataclass
class Anchor:
    name: str
    company: str
    domain: str = ""


@dataclass
class Candidate:
    name: str
    text: str = ""  # bio, snippet, company - anything that could corroborate
    source: str = ""


def _tokens(s):
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) > 1}


def name_overlap(anchor_name, candidate_name):
    # share of the anchor's name tokens present in the candidate's name
    a, b = _tokens(anchor_name), _tokens(candidate_name)
    return len(a & b) / len(a) if a and b else 0.0


def judge(anchor, candidate, use_llm=True):
    # return (accepted, confidence, reason)
    name_score = name_overlap(anchor.name, candidate.name)
    if name_score < 0.5:
        return False, name_score, "name does not match"
    blob = f"{candidate.name} {candidate.text}".lower()
    company_hit = anchor.company.lower() in blob or bool(anchor.domain and anchor.domain.lower() in blob)
    if name_score >= 0.99 and company_hit:
        return True, 0.95, "name and company both match"  # the anchor rule
    if company_hit:
        return True, 0.8, "company matches, name partial"
    if use_llm:
        return _llm_judge(anchor, candidate)  # name matches but no company signal in the text
    return False, name_score, "name matches but no company corroboration"


def _llm_judge(anchor, candidate):
    system = ('You decide if two descriptions are the same real person. '
              'Reply JSON only: {"same": true or false, "confidence": 0 to 1}.')
    user = (f"Target: {anchor.name}, works at {anchor.company}.\n"
            f"Candidate: {candidate.name}. Info: {candidate.text[:500]}\n"
            "Are these the same person?")
    try:
        text = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
        m = re.search(r"\{.*\}", text, re.S)  # tolerate prose around the json
        data = json.loads(m.group(0)) if m else {}
        return bool(data.get("same")), float(data.get("confidence", 0.5)), "llm judge"
    except Exception as e:
        return False, 0.0, f"llm judge failed: {e}"
