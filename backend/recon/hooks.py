"""propose ranked hook hypotheses from the facts.

- the model reads the strongest facts and suggests topics the target is open to now
- each hook carries a probability, the evidence it rests on, and its angle
"""
import json
import re

from backend import llm
from schemas import Hook

SYSTEM = (
    "You are planning an authorised social-engineering awareness test. Given facts about a "
    "person, propose topics they are likely open to right now (a speaking invite, a vendor "
    "renewal, an investor intro, a press request, a recruiting lead, etc.). Return JSON only: "
    "{\"hooks\": [{\"topic\": ..., \"probability\": 0-1, \"evidence\": [..], "
    "\"rationale\": ..., \"angle\": \"their_topic\" or \"own_angle\"}]}. Prefer recent, "
    "specific facts. their_topic = a likely planted interest; own_angle = a topic they were "
    "not set up for."
)
JSON_MODE = {"type": "json_object"}


def propose(name, company, facts, top=6):
    strong = [f for f in facts if f.verified or f.confidence >= 0.6]
    lines = [f"- [{f.category}] {f.value}" for f in strong] or [f"- works at {company}"]
    user = f"Person: {name} ({company}).\nFacts:\n" + "\n".join(lines)
    try:
        text = llm.chat([{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}], response_format=JSON_MODE)
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
                evidence=[str(x) for x in h.get("evidence", [])],
                rationale=str(h.get("rationale", "")).strip(),
                angle=h.get("angle", "their_topic"),
            ))
    hooks.sort(key=lambda h: h.probability, reverse=True)
    return hooks[:top]
