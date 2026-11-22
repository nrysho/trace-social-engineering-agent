"""Turn saved practice conversations into viewer runs.

Two sources:
  runs/bench/<sid>.json   bench sessions, with ground truth (hook hits, the persona's thought)
  runs/chat/<sid>.jsonl   chat.py logs of revel8 sessions (only what the API reveals)
A session that exists in both is shown from the bench record, which has everything.

Each conversation becomes a chain: target -> contact -> reaction -> contact -> ...
The output uses the same run format as agent runs (see README.md), plus "metrics" for the results table.
"""
import json
from datetime import datetime, timedelta
from backend.outcomes import classify_incident

FOUNDERS = {
    "julius": ("Julius Muth", "Co-Founder & Co-CEO, revel8 (business and go-to-market)"),
    "robert": ("Robert Seilbeck", "Co-Founder & CTO, revel8"),
    "tom": ("Tom Müller", "Co-Founder & Co-CEO, revel8 (product)"),
}
# Compatibility label map; form outcomes require classify_incident, not event type alone.
WINS = {"attachment.opened": "action"}


def load_personas(path):
    return {p["id"]: p for p in json.loads(path.read_text())} if path.exists() else {}


def name_of(target, personas):
    if target in personas:
        return personas[target]["name"]
    return FOUNDERS.get(target, (target.title(), ""))[0]


def profile_for(target, personas):
    p = personas.get(target)
    if not p:
        name, role = FOUNDERS.get(target, (target.title(), ""))
        return {"name": name, "role": role, "company": "revel8" if target in FOUNDERS else "", "facts": [], "hooks": []}
    return {
        "name": p["name"], "role": p["role"], "company": p["company"], "domain": p["domain"],
        "hooks_label": "Planted hooks (bench ground truth)",
        "hooks": [{"topic": h["topic"], "probability": 1.0, "rationale": h["detail"], "angle": "their_topic"} for h in p["hooks"]],
        "facts": [{"category": "public page", "value": pg["text"], "source_url": pg["url"], "source_title": pg["title"],
                   "confidence": 1.0, "verified": True, "supporting_urls": []} for pg in p["public_pages"]],
    }


def page_in(body, pages):
    return next((pg for url, pg in pages.items() if url in (body or "")), None)


def reaction_summary(who, events, incidents, call_lines=None):
    if call_lines is not None:  # a call: the reaction is the conversation itself
        talk = f"{who} talked on the call ({call_lines} lines)" if call_lines else f"{who} picked up; nothing else was recorded"
        return talk + (", ★ disclosed internal facts" if "disclosure" in incidents else "")
    if not events:
        return f"{who} did not react"
    parts = []
    for e in events:
        if e["type"] == "attachment.opened":
            parts.append(f"★ opened {e.get('filename', 'the attachment')}")
        elif e["type"] == "page.submitted":
            parts.append(f"★ submitted the page ({', '.join(e.get('fields') or [])})")
        elif e["type"] == "link.opened":
            parts.append("opened the link")
        elif e["type"] == "reply":
            parts.append("replied")
    if "disclosure" in incidents:
        parts.append("★ disclosed internal facts")
    return f"{who} " + ", ".join(parts)


def chain(run_id, mode, created, contacts, profile, label=""):
    """contacts: dicts with kind, to, who, channel, sender, subject, body, attachments, page,
    events, incidents, and optional truth (hook_hit, topic, suspicion, thought, disclosed)."""
    start = datetime.fromisoformat(created.replace("Z", "+00:00"))
    stamp = lambda i: (start + timedelta(seconds=i)).isoformat()
    has_truth = any(c.get("truth") for c in contacts)
    first_win = next((i for i, c in enumerate(contacts, 1) if c["incidents"]), None)
    nodes = [{
        "id": "t", "run_id": run_id, "level": "target", "agent": "you" if mode != "bench" else "bench",
        "decision": "Session with " + ", ".join(dict.fromkeys(c["who_full"] for c in contacts)),
        "reasoning": ("Practice conversation on the local bench. Reactions come from a fictional persona with planted hooks."
                      if has_truth else "Practice conversation typed by hand in chat.py. No agent reasoning was recorded."),
        "parent_id": None, "rejected": [], "evidence": [], "status": "incident" if first_win else "active",
        "outcome": f"First incident on touch {first_win}." if first_win else "No incident.", "timestamp": stamp(0),
    }]
    messages, events, parent = [], {}, "t"
    for i, c in enumerate(contacts, 1):
        truth = c.get("truth") or {}
        replied = any(e["type"] == "reply" for e in c["events"])
        status = ("incident" if c["incidents"] else "engaged" if replied or c["kind"] == "call"
                  else "suspicious" if (truth.get("suspicion") or 0) >= 6 else "failed")
        snippet = c["subject"] or " ".join(str(c["body"]).split())[:70]
        cid, rid = f"c{i}", f"r{i}"
        nodes.append({
            "id": cid, "run_id": run_id, "level": "contact", "agent": "you", "parent_id": parent,
            "decision": f"{c['channel'].replace('_', ' ')} to {c['who']}: {snippet}",
            "reasoning": "Sent by hand." if not label else f"Sent in a session labelled {label}.",
            "rejected": [], "evidence": [], "status": status, "timestamp": stamp(2 * i - 1),
            "outcome": reaction_summary(c["who"], c["events"], c["incidents"], c.get("call_lines")) + ".",
        })
        messages.append({"session_id": run_id, "channel": c["channel"], "to": c["to"], "sender": c["sender"] or {},
                         "subject": c["subject"], "body": c["body"], "attachments": [{"filename": a} for a in c["attachments"]],
                         "landing_page": c.get("page"), "node_id": cid})
        events[cid] = c["events"]
        if truth:
            hook = f"Hit planted hook: {truth.get('topic', '?')}." if truth.get("hook_hit") else "Not about a planted hook."
            reasoning = f"{c['who']}'s private thought: {truth.get('thought') or '(none)'}\n{hook} Suspicion {truth.get('suspicion', '?')}/10."
            if truth.get("disclosed"):
                reasoning += f" Disclosed internal facts: {', '.join(truth['disclosed'])}."
            if truth.get("voided"):
                reasoning += " This contact broke a rule and voided the session."
        else:
            reasoning = "revel8 does not reveal what the twin thought; only the events below came back."
        nodes.append({
            "id": rid, "run_id": run_id, "level": "reaction", "agent": "bench persona" if truth else "revel8 twin",
            "parent_id": cid, "decision": reaction_summary(c["who"], c["events"], c["incidents"], c.get("call_lines")), "reasoning": reasoning,
            "rejected": [], "evidence": [], "status": status, "timestamp": stamp(2 * i), "outcome": "",
        })
        parent = rid
    return {
        "run_id": run_id, "mode": mode, "profile": profile, "nodes": nodes, "messages": messages, "events": events,
        "metrics": {
            "source": "bench" if mode == "bench" else "revel8 practice", "label": label, "created_at": created,
            "touches": len(contacts), "first_incident_touch": first_win,
            "incidents": sorted({i for c in contacts for i in c["incidents"]}),
            "topic_hits": sum(1 for c in contacts if (c.get("truth") or {}).get("hook_hit")) if has_truth else None,
            "voided": any((c.get("truth") or {}).get("voided") for c in contacts),
        },
    }


def from_bench(path, personas):
    r = json.loads(path.read_text())
    if not r["truth"]:
        return None
    pages = {pg["url"]: pg for pg in r.get("pages", [])}
    contacts = []
    for t in r["truth"]:
        who_full = name_of(t["to"], personas)
        if t["kind"] == "call":
            body = "\n".join(f"{'You' if x['who'] == 'Caller' else x['who']}: {x['line']}" for x in t.get("transcript") or [])
            evs = []
        else:
            body = t.get("body", "")
            evs = [e for e in r["events"] if e.get("message_id") == t.get("message_id") or e.get("in_reply_to") == t.get("message_id")]
        contacts.append({
            "kind": t["kind"], "to": t["to"], "who": who_full.split()[0], "who_full": who_full, "channel": t["channel"],
            "sender": t.get("from"), "subject": t.get("subject", ""), "body": body or "(no conversation recorded)", "call_lines": (len(t.get("transcript") or []) if t["kind"] == "call" else None),
            "attachments": t.get("attachments", []), "page": page_in(body, pages), "events": evs,
            "incidents": t["incidents"], "truth": t,
        })
    target = r["truth"][0]["to"]
    run = chain(r["session_id"], "bench", r["created_at"], contacts, profile_for(target, personas), r.get("label", ""))
    # The session flag is the source of truth: a landing page on the target's own domain voids
    # the session without marking any single contact.
    run["metrics"]["voided"] = bool(r.get("voided"))
    return run


def from_chat_log(path, personas):
    contacts, pages = [], {}
    for line in path.read_text().splitlines():
        e = json.loads(line)
        if e["kind"] == "sent":
            who_full = name_of(e["to"], personas)
            contacts.append({"kind": "message", "to": e["to"], "who": who_full.split()[0], "who_full": who_full,
                             "channel": e["channel"], "sender": e.get("from"), "subject": e.get("subject", ""),
                             "body": e["body"], "attachments": [a.get("filename", "") for a in e.get("attachments", [])],
                             "page": page_in(e["body"], pages), "events": [], "incidents": []})
        elif e["kind"] == "call":
            who_full = name_of(e["to"], personas)
            contacts.append({"kind": "call", "to": e["to"], "who": who_full.split()[0], "who_full": who_full,
                             "channel": e["channel"], "sender": None, "subject": "", "body": "", "attachments": [],
                             "page": None, "events": [], "incidents": [], "call_lines": 0})
        elif e["kind"] == "turn" and contacts:
            c = contacts[-1]
            line_ = (f"You: {e['say']}\n" if e.get("say") else "") + f"{c['who']}: {e['heard']}"
            c["body"] = f"{c['body']}\n{line_}".strip()
            c["call_lines"] = len(c["body"].splitlines())
        elif e["kind"] == "event" and contacts:
            contacts[-1]["events"].append(e["event"])
            win, _ = classify_incident([e['event']])
            if win and win not in contacts[-1]["incidents"]:
                contacts[-1]["incidents"].append(win)
        elif e["kind"] == "page":
            pages[e["url"]] = {k: e.get(k) for k in ("url", "title", "text", "html", "fields")}
    if not contacts:
        return None
    created = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
    return chain(path.stem, "practice chat", created, contacts, profile_for(contacts[0]["to"], personas))


def _when(ts):
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def from_agent_tree(path, runs_dir):
    """An orchestrator run: runs/trees/<run_id>.json holds only the TreeNodes. The messages and
    reactions come from the revel8 client's log (runs/api/<sid>.jsonl, matched by the node ids of
    the contacts and the run's time window) and the profile from recon (runs/profiles/*.json)."""
    nodes = json.loads(path.read_text())
    if not nodes:
        return None
    contact_ids = {n["id"] for n in nodes if n.get("level") == "contact"}
    start = min(_when(n["timestamp"]) for n in nodes) - timedelta(minutes=2)
    end = max(_when(n["timestamp"]) for n in nodes) + timedelta(minutes=10)
    best, best_hits = None, 0
    for log in (runs_dir / "api").glob("*.jsonl") if (runs_dir / "api").exists() else []:
        entries = _read_jsonl(log)
        sent = [e for e in entries if e.get("kind") == "sent" and start <= _when(e["at"]) <= end]
        hits = sum(1 for e in sent if e.get("node_id") in contact_ids)
        if hits > best_hits:
            best, best_hits = entries, hits
    messages, events, pages = [], {}, {}
    by_message = {}
    for e in best or []:
        if e.get("kind") == "page":
            pages[e.get("url")] = {k: e.get(k) for k in ("url", "title", "text", "html", "fields")}
        elif e.get("kind") == "sent":
            m = e.get("message") or {}
            by_message[e.get("message_id")] = e.get("node_id")
            events.setdefault(e.get("node_id"), [])
            messages.append({"session_id": path.stem, "channel": m.get("channel", ""), "to": m.get("to", ""),
                             "sender": m.get("from") or {}, "subject": m.get("subject", ""), "body": m.get("body", ""),
                             "attachments": [a if isinstance(a, dict) else {"filename": str(a)} for a in m.get("attachments", [])],
                             "landing_page": page_in(m.get("body", ""), pages), "node_id": e.get("node_id"),
                             "qa": e.get("qa"), "message_id": e.get("message_id"),
                             "idempotency_key": e.get("idempotency_key")})
        elif e.get("kind") == "event" and e.get("message_id") in by_message:
            events[by_message[e["message_id"]]].append(e["event"])
    target = next((n for n in nodes if n.get("level") == "target"), nodes[0])
    name = str(target.get("decision", "")).removeprefix("target ").removeprefix("Target ").strip()
    profile = {"name": name, "role": target.get("reasoning", ""), "facts": [], "hooks": []}
    candidates = []
    for pf in (runs_dir / "profiles").glob("*.json") if (runs_dir / "profiles").exists() else []:
        try:
            data = json.loads(pf.read_text())
        except ValueError:
            continue
        if str(data.get("name", "")).lower() == name.lower():
            candidates.append((pf.stat().st_mtime, data))
    if candidates:
        profile = max(candidates, key=lambda c: c[0])[1]
    return {"run_id": path.stem, "mode": "agent", "profile": profile, "nodes": nodes, "messages": messages, "events": events}
