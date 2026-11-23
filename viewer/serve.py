#!/usr/bin/env python3
"""Read-only server for the run replay viewer.

    python3 viewer/serve.py            # then open http://127.0.0.1:8765

Serves viewer/index.html and lists runs:
  - agent runs: runs/trees/<run_id>.json (orchestrator), joined with runs/api/ and runs/profiles/,
    or a single run bundle in runs/*.json
  - bench sessions in runs/bench/*.json, with ground truth (see bench/)
  - chat.py conversations with the revel8 twins in runs/chat/*.jsonl
  - "sample": viewer/sample_run.json (a branching demo run)
  - "mock":   the fictional demo data in mock/profile.json + mock/tree.json + mock/message.json
/api/results summarises all of them for the results table.
Only GET requests exist. Nothing here can contact a target.
"""
import hashlib
import json
import pathlib
import re
import threading
from urllib.parse import parse_qs, urlsplit
import statistics
import sys
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


VIEWER = pathlib.Path(__file__).resolve().parent
ROOT = VIEWER.parent
RUNS = ROOT / "runs"
MOCK = ROOT / "mock"
sys.path.insert(0,str(ROOT))
from viewer import sessions
from viewer.qa_metrics import quality_summary, by_version
from backend.outcomes import classify_incident, credible_judged
from viewer.judging_evidence import judging_evidence
PERSONAS = ROOT / "bench" / "personas.json"
DEMO_RUNS = {"sample", "mock"}  # replayable, but never counted as results


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalise(bundle):
    """events grouped by contact node, the shape the viewer reads. Runs saved before the per-contact
    format kept one flat list: regroup it by message id; events that match no contact are dropped
    from the per-contact view rather than breaking the whole run list."""
    events = bundle.get("events")
    if isinstance(events, list):
        node_of = {m.get("message_id"): m.get("node_id") for m in bundle.get("messages", []) if m.get("message_id")}
        grouped = {}
        for e in events:
            node = node_of.get(e.get("message_id")) or node_of.get(e.get("in_reply_to"))
            if node:
                grouped.setdefault(node, []).append(e)
        bundle["events"] = grouped
    return bundle


TRANSLATIONS = RUNS / "translations.json"
_GERMAN = re.compile(r"\b(ich|nicht|und|der|die|das|bitte|danke|schicken|gerne|gern|ist|wir|sie|mir|mit|auf|ihr|ihnen|für|wenn|aber)\b", re.I)
_LOCK = threading.Lock()


def translate(text):
    """an English translation of a German message, reply or call (None if it is already English).
    Uses the team's model once per text and caches the result in runs/translations.json; the
    viewer stays read-only towards targets: this calls the model, never the revel8 API."""
    text = str(text or "").strip()
    words = len(text.split())
    if words < 3 or len(_GERMAN.findall(text)) < max(2, words // 15):
        return None
    key = hashlib.sha1(text.encode()).hexdigest()
    with _LOCK:
        try:
            cache = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
    if key in cache:
        return cache[key]
    sys.path.insert(0, str(ROOT))
    from backend import llm            # imported lazily: the viewer works without model keys
    out = llm.chat([{"role": "system", "content": "Translate the user's text into natural English. Keep names, line breaks "
                     "and speaker labels like 'them:' or 'us:'. Reply with the translation only."},
                    {"role": "user", "content": text[:6000]}]).strip()
    with _LOCK:
        try:
            cache = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        cache[key] = out
        TRANSLATIONS.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def mock_bundle():
    nodes = load(MOCK / "tree.json")
    message = load(MOCK / "message.json")
    return {
        "run_id": nodes[0]["run_id"] if nodes else "mock",
        "mode": "mock",
        "profile": load(MOCK / "profile.json"),
        "nodes": nodes,
        "messages": [message],
        "events": {},
    }


def by_mtime(paths):
    return sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)


def bundles():
    """id -> loader. A loader may return None for an empty session, which is then skipped."""
    found = {}
    if RUNS.exists():
        for path in by_mtime(RUNS.glob("*.json")):
            found[path.stem] = lambda p=path: normalise(load(p))
    for path in by_mtime((RUNS / "trees").glob("*.json")) if (RUNS / "trees").exists() else []:
        found.setdefault(path.stem, lambda p=path: sessions.from_agent_tree(p, RUNS))  # the orchestrator's runs
    personas = sessions.load_personas(PERSONAS)
    bench_ids = set()
    for path in by_mtime((RUNS / "bench").glob("*.json")) if (RUNS / "bench").exists() else []:
        bench_ids.add(path.stem)
        found[f"bench-{path.stem}"] = lambda p=path: sessions.from_bench(p, personas)
    for path in by_mtime((RUNS / "chat").glob("*.jsonl")) if (RUNS / "chat").exists() else []:
        if path.stem not in bench_ids:  # bench sessions typed in chat.py are already shown from the bench record
            found[f"chat-{path.stem}"] = lambda p=path: sessions.from_chat_log(p, personas)
    if (VIEWER / "sample_run.json").exists():
        found["sample"] = lambda: load(VIEWER / "sample_run.json")
    if (MOCK / "tree.json").exists():
        found["mock"] = mock_bundle
    return found


def metrics(bundle):
    """Results-table numbers: from the converter when present, else computed from the run's nodes."""
    if bundle.get("metrics"):
        return bundle["metrics"]
    contacts = sorted((n for n in bundle.get("nodes", []) if n.get("level") == "contact"), key=lambda n: str(n.get("timestamp")))
    first = next((i for i, n in enumerate(contacts, 1) if n.get("status") == "incident"), None)
    types = {e.get("type") for evs in (bundle.get("events") or {}).values() for e in evs}
    return {
        "source": "agent" if bundle.get("mode") not in ("sample", "mock") else bundle["mode"],
        "label": bundle.get("agent_version", ""), "created_at": (contacts[0].get("timestamp") if contacts else ""),
        "touches": len(contacts), "first_incident_touch": first,
        "incidents": sorted({candidate for evs in (bundle.get('events') or {}).values()
                             for event in evs for candidate,_ in [classify_incident([event])] if candidate}),
        "topic_hits": None, "voided": False,
    }


def summary(run_id, bundle):
    m = metrics(bundle)
    return {"id": run_id, "target": (bundle.get("profile") or {}).get("name", ""), "mode": bundle.get("mode", ""),
            "contacts": m["touches"], "incident": bool(m["first_incident_touch"]), "qa": quality_summary(bundle),
            # disclosures or acts only our judge saw: shown apart from recorded objectives (revel8 decides them)
            "judged": len(credible_judged(bundle.get("judged_disclosures"))),
            "run_status": bundle.get('run_status'), "abort_reason": bundle.get('abort_reason')}


def when(row):
    """Sort key: timestamps come in different time zones, so compare them as instants, not text."""
    try:
        t = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
        return t if t.tzinfo else t.astimezone()
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def results():
    rows = []
    for run_id, loader in bundles().items():
        if run_id in DEMO_RUNS:  # invented data, not tests: keep it out of the numbers
            continue
        try:
            bundle = loader()
        except (OSError, ValueError, KeyError):
            continue
        if bundle:
            rows.append({"id": run_id, "target": (bundle.get("profile") or {}).get("name", ""), **metrics(bundle), "qa": quality_summary(bundle),
                         "run_status": bundle.get('run_status'), "abort_reason": bundle.get('abort_reason')})
    totals = []
    for key in sorted({(r["source"], r["label"]) for r in rows}):
        group = [r for r in rows if (r["source"], r["label"]) == key and r["touches"]]
        if not group:
            continue
        wins = [r["first_incident_touch"] for r in group if r["first_incident_touch"] and not r["voided"]]
        known = [r for r in group if r["topic_hits"] is not None]
        totals.append({
            "source": key[0], "label": key[1], "runs": len(group),
            "incident_rate": round(len(wins) / len(group), 2),
            "median_touches_to_incident": statistics.median(wins) if wins else None,
            "topic_hit_share": round(sum(r["topic_hits"] for r in known) / sum(r["touches"] for r in known), 2) if known else None,
            "voided": sum(1 for r in group if r["voided"]),
        })
    return {"totals": totals, "runs": sorted(rows, key=when, reverse=True)}


def progress():
    """Agent versions (bench labels) in the order they were first run, with ground-truth numbers per persona."""
    personas = sessions.load_personas(PERSONAS)
    versions = {}
    for path in (RUNS / "bench").glob("*.json") if (RUNS / "bench").exists() else []:
        r = load(path)
        if not r.get("label") or not r["truth"]:
            continue
        target = r["truth"][0]["to"]
        versions.setdefault(r["label"], []).append({
            "session_id": r["session_id"], "created_at": r["created_at"],
            "persona": sessions.name_of(target, personas), "touches": len(r["truth"]),
            "first_incident_touch": None if r["voided"] else r["first_incident_touch"],
            "topic_hits": sum(1 for c in r["truth"] if c["hook_hit"]), "voided": r["voided"],
        })
    out = []
    for label, runs in versions.items():
        wins = [x["first_incident_touch"] for x in runs if x["first_incident_touch"]]
        touches = sum(x["touches"] for x in runs)
        out.append({
            "label": label, "first_run": min(x["created_at"] for x in runs), "runs": len(runs),
            "incident_rate": round(len(wins) / len(runs), 2),
            "median_touches_to_incident": statistics.median(wins) if wins else None,
            "topic_hit_share": round(sum(x["topic_hits"] for x in runs) / touches, 2) if touches else None,
            "voided": sum(1 for x in runs if x["voided"]),
            "sessions": sorted(runs, key=when),
        })
    return {"versions": sorted(out, key=lambda v: when({"created_at": v["first_run"]})),
            "personas": sorted({x["persona"] for v in out for x in v["sessions"]})}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(VIEWER), **kwargs)

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == '/api/quality/versions':
            records = []
            for loader in bundles().values():
                try:
                    item = loader()
                    if isinstance(item,dict): records.append(item)
                except (OSError,ValueError,KeyError): continue
            return self.send_json(by_version(records))
        if path == "/api/runs":
            out = []
            for run_id, loader in bundles().items():
                try:
                    bundle = loader()
                    if bundle:
                        out.append(summary(run_id, bundle))
                except (OSError, ValueError, KeyError) as e:
                    out.append({"id": run_id, "error": str(e)})
            return self.send_json(out)
        if path == "/api/results":
            return self.send_json(results())
        if path == "/api/progress":
            return self.send_json(progress())
        if path == "/api/translate":
            text = (parse_qs(urlsplit(self.path).query).get("text") or [""])[0]
            try:
                return self.send_json({"translation": translate(text)})
            except Exception as e:     # no model key or the model is down: the page just shows no translation
                return self.send_json({"translation": None, "error": str(e)[:200]})
        if path.startswith("/api/runs/"):
            loader = bundles().get(path[len("/api/runs/"):])
            if not loader:
                return self.send_json({"error": "unknown run"}, 404)
            try:
                bundle = loader()
            except (OSError, ValueError, KeyError) as e:
                return self.send_json({"error": f"cannot read run: {e}"}, 500)
            if bundle:
                bundle = dict(bundle, judged_disclosures=credible_judged(bundle.get("judged_disclosures")))
            return self.send_json(dict(bundle,judging_evidence=judging_evidence(bundle))) if bundle else self.send_json({"error": "empty session"}, 404)
        if path in ("/", "/index.html"):
            return super().do_GET()
        self.send_error(404)

    def log_message(self, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Run viewer on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
