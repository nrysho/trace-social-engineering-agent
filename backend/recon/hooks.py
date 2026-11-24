"""propose ranked hook hypotheses from the facts.

- the model reads the strongest facts and suggests topics the target is open to now
- each hook carries a probability, the evidence it rests on, and its angle
"""
import json
import re

from backend import llm
from backend.recon import recency
from core.schemas import Hook

SYSTEM = (
    "You are planning an authorised social-engineering awareness test. Given facts about a "
    "person, propose topics they are likely open to right now (a speaking invite, a vendor "
    "renewal, an investor intro, a press request, a recruiting lead, etc.). Return JSON only: "
    "{\"hooks\": [{\"topic\": ..., \"probability\": 0-1, \"evidence\": [fact numbers], "
    "\"rationale\": ..., \"angle\": \"their_topic\" or \"own_angle\"}]}. evidence is a list of the "
    "integer NUMBERS of the facts the hook rests on, taken from the numbered facts list - numbers only, "
    "never reworded text. Each fact is tagged with its date; prefer recent or current facts and never "
    "base a hook on a fact marked stale. their_topic = a likely planted interest; own_angle = a topic "
    "they were not set up for. A need the person stated publicly (asking for recommendations, looking "
    "for a supplier, planning a purchase, replacing a tool, hiring) is the strongest hook: name it in "
    "their own concrete terms (\"a venue for a 180-person summer party in Munich\"), never as a generic "
    "label (\"vendor renewal\"), and rank it above interests inferred from their role."
)
JSON_MODE = {"type": "json_object"}


def _line(i, f):
    # number each fact and tag its freshness, so the model can cite facts by number
    w = recency.weight(f.date)
    when = "current" if f.date.lower() == "present" else (f.date or "undated")
    if w < 0.4:
        when += ", stale"
    return f"{i}. [{f.category}, {when}] {f.value}"


def _resolve(evidence, strong):
    # the model returns fact numbers; map each back to the exact fact text so the ui can
    # match a hook's evidence to its facts character-for-character
    out = []
    for x in evidence:
        s = str(x).strip()
        if s.lstrip("-").isdigit() and 0 <= int(s) < len(strong):
            out.append(strong[int(s)].value)
        else:  # tolerate the model echoing the fact text instead of its number
            match = next((f.value for f in strong if f.value == s), "")
            if match:
                out.append(match)
    return out


def propose(name, company, facts, top=6):
    strong = [f for f in facts if f.verified or f.confidence >= 0.6]
    strong.sort(key=lambda f: recency.weight(f.date), reverse=True)  # freshest first
    lines = [_line(i, f) for i, f in enumerate(strong)] or [f"0. works at {company}"]
    user = f"Person: {name} ({company}).\nFacts:\n" + "\n".join(lines)
    try:
        text = llm.chat([{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}], response_format=JSON_MODE, temperature=0)
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    except Exception as e:
        print(f"  hooks failed: {e}")
        return []
    hooks = []
    for h in data.get("hooks", []):
        if h.get("topic"):
            hooks.append(Hook(
                topic=str(h["topic"]).strip(),
                probability=float(h.get("probability", 0.5)),
                evidence=_resolve(h.get("evidence", []), strong),
                rationale=str(h.get("rationale", "")).strip(),
                angle=h.get("angle", "their_topic"),
            ))
    hooks.sort(key=lambda h: h.probability, reverse=True)
    return hooks[:top]
