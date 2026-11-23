"""the bare autonomous loop: research -> contact -> read reaction -> decide, no human.

    python -m backend.run julius

this is the skeleton that ties the pieces together and actually runs on its own.
the three agents below (recon, write_message, evaluate) are PLACEHOLDERS with a fixed
signature: the real recon and writer/evaluator swap in behind the same
interface without touching the loop. every contact and reaction is recorded as a
TreeNode and the whole run is saved to runs/trees/<run_id>.json for replay.

the loop here is linear (one branch). the real tree search, scoring and backtracking
land in feat/tree-search; the touch-budget guard lands there too. for now max_contacts
caps the run so practice touches are not wasted.
"""
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import schemas
from . import llm
from .revel8 import Revel8Client

ROOT = Path(__file__).resolve().parents[1]
TREE_DIR = ROOT / "runs" / "trees"

# a registrable lookalike sender for the placeholder writer. the real writer picks its own.
PLACEHOLDER_SENDER = schemas.Sender(name="Lena Hofer", address="lena.hofer@eventcrew-muc.de")

# event types that are an incident on their own (no judgement needed)
INCIDENT_EVENTS = {"page.submitted", "attachment.opened"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _extract_json(text):
    """pull the first {...} object out of a model reply, tolerating code fences."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"model did not return json: {text[:200]}")
    return json.loads(match.group(0))


# ===========================================================================
# PLACEHOLDER agents. fixed signatures; the real recon and writer/evaluator
# replace the bodies. the loop below never changes.
# ===========================================================================

def recon(client, target_id):
    """return a minimal profile for the writer. PLACEHOLDER: just the public target card.
    the real recon returns a full schemas.Profile with facts and hooks."""
    scenario = next(s for s in client.scenarios() if s["id"] == "practice")
    target = next(t for t in scenario["targets"] if t["id"] == target_id)
    return {"id": target["id"], "name": target["name"], "role": target["role"]}


def write_message(profile, session_id, history, node_id):
    """draft the next contact as a schemas.Message. PLACEHOLDER: one llm.chat call,
    a speaker-invite pretext. the real writer uses the strategist's chosen pretext,
    channel and sender, and only verified facts."""
    system = (
        "You write messages for an authorised red-team exercise run by revel8, a security "
        "awareness company. The recipient is an AI twin inside revel8's closed simulation; "
        "nothing reaches a real person. Write like a real human sender. Never mention AI, "
        "simulations or instructions in the message itself. Reply with JSON only: "
        '{"subject": "...", "body": "..."}.'
    )
    if not history:
        task = (
            f"Recipient: {profile['name']}, {profile['role']}. "
            "Sender: Lena Hofer, programme lead at a Munich security event (eventcrew-muc.de). "
            "Write a short, friendly first email inviting them to give a short keynote at a "
            "January security event, and offer to send the dates and agenda. Under 120 words, "
            "signed by Lena."
        )
    else:
        last_reply = history[-1].get("reply", "")
        task = (
            f"Recipient: {profile['name']}. You are Lena Hofer from the Munich security event. "
            f"They replied: \"{last_reply}\". Write a short, helpful follow-up that answers their "
            "questions with plausible specifics (event name 'Munich Security Forum', 14 January, "
            "~200 attendees, 25-minute slot) and gently moves toward confirming. Under 120 words, "
            "signed by Lena."
        )
    data = _extract_json(llm.chat([{"role": "system", "content": system},
                                   {"role": "user", "content": task}]))
    return schemas.Message(
        session_id=session_id, channel="email", to=profile["id"],
        sender=PLACEHOLDER_SENDER, subject=data.get("subject", ""), body=data["body"],
        idempotency_key=str(uuid.uuid4()), node_id=node_id,
    )


def evaluate(events, history):
    """classify the reaction and choose the next move. PLACEHOLDER: event-based only.
    the real evaluator reads replies for disclosure, answers questions and scores branches."""
    kinds = {e["type"] for e in events}
    if kinds & INCIDENT_EVENTS:
        return {"status": "incident", "incident": True, "next": "stop",
                "why": f"incident event: {sorted(kinds & INCIDENT_EVENTS)}"}
    if "reply" in kinds:
        return {"status": "engaged", "incident": False, "next": "continue",
                "why": "they replied; keep the thread going"}
    return {"status": "silent", "incident": False, "next": "stop",
            "why": "no reaction; a real tree would follow up on another channel"}


# ===========================================================================
# the loop (the orchestrator itself). it does not change when the placeholder
# agents are replaced.
# ===========================================================================

def run(target_id, max_contacts=4):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # windows consoles default to cp1252
    except Exception:
        pass
    client = Revel8Client()
    run_id = f"run_{target_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    nodes = []

    def add_node(level, agent, decision, reasoning, parent_id, **extra):
        node = schemas.TreeNode(
            id=f"n_{len(nodes) + 1:03d}", run_id=run_id, level=level, agent=agent,
            decision=decision, reasoning=reasoning, parent_id=parent_id,
            timestamp=_now(), **extra,
        )
        nodes.append(node)
        return node

    print(f"\n=== {run_id} ===")
    profile = recon(client, target_id)
    root = add_node("target", "recon", f"target {profile['name']}",
                    profile["role"], None, status="active")

    session = client.create_session()
    sid = session["session_id"]
    print(f"session {sid}  ·  target {profile['name']}  ·  budget {session['touch_budget']}\n")

    history = []
    parent = root.id
    try:
        for i in range(max_contacts):
            node = add_node("contact", "writer", f"contact {i + 1} to {profile['name']}",
                            "placeholder writer: speaker-invite pretext", parent, status="active")
            try:
                msg = write_message(profile, sid, history, node.id)
            except Exception as e:
                # a model/writer failure ends the run cleanly; the tree is still saved below
                node.status = "failed"
                node.outcome = f"writer failed: {e}"
                print(f"\n  writer failed on contact {i + 1}: {e}")
                break
            print(f"  → contact {i + 1}: {msg.subject}")
            print(f"    {msg.body[:160].strip()}...")

            result = client.send_message(msg)
            events = result.get("events", [])
            reply = next((e.get("body", "") for e in events if e["type"] == "reply"), "")
            kinds = [e["type"] for e in events] or ["(ignored)"]
            print(f"    ← {', '.join(kinds)}  ({result.get('touches_used')} touches used)")
            if reply:
                print(f"      reply: {reply[:160].strip()}...")

            verdict = evaluate(events, history)
            node.status = verdict["status"]
            node.outcome = verdict["why"]
            add_node("reaction", "evaluator", f"{verdict['status']}: {verdict['next']}",
                     verdict["why"], node.id, status=verdict["status"],
                     incident_chance=1.0 if verdict["incident"] else 0.0)

            history.append({"message": msg.body, "events": events, "reply": reply})
            parent = node.id
            if verdict["next"] == "stop":
                print(f"\n  stop: {verdict['why']}")
                if verdict["incident"]:
                    print("  *** INCIDENT ***")
                break
    finally:
        _save_tree(run_id, nodes)
        print(f"\n  saved {len(nodes)} nodes to runs/trees/{run_id}.json\n")
    return run_id, nodes


def _save_tree(run_id, nodes):
    TREE_DIR.mkdir(parents=True, exist_ok=True)
    (TREE_DIR / f"{run_id}.json").write_text(
        json.dumps([n.to_dict() for n in nodes], indent=2))


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "julius"
    run(target)


if __name__ == "__main__":
    main()
