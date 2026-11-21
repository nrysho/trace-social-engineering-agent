#!/usr/bin/env python3
"""Read-only server for the run replay viewer.

    python3 viewer/serve.py            # then open http://127.0.0.1:8765

Serves viewer/index.html and lists runs:
  - every run bundle in runs/*.json (written by the agent)
  - "sample": viewer/sample_run.json (a branching demo run)
  - "mock":   Mavis's mock/profile.json + mock/tree.json + mock/message.json
Only GET requests exist. Nothing here can contact a target.
"""
import json
import pathlib
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

VIEWER = pathlib.Path(__file__).resolve().parent
ROOT = VIEWER.parent
RUNS = ROOT / "runs"
MOCK = ROOT / "mock"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


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


def bundles():
    """id -> loader, newest agent runs first."""
    found = {}
    if RUNS.exists():
        for path in sorted(RUNS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            found[path.stem] = lambda p=path: load(p)
    if (VIEWER / "sample_run.json").exists():
        found["sample"] = lambda: load(VIEWER / "sample_run.json")
    if (MOCK / "tree.json").exists():
        found["mock"] = mock_bundle
    return found


def summary(run_id, bundle):
    nodes = bundle.get("nodes", [])
    profile = bundle.get("profile") or {}
    contacts = [n for n in nodes if n.get("level") == "contact"]
    return {
        "id": run_id,
        "target": profile.get("name", ""),
        "mode": bundle.get("mode", ""),
        "contacts": len(contacts),
        "incident": any(n.get("status") == "incident" for n in nodes),
    }


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
        if path == "/api/runs":
            out = []
            for run_id, loader in bundles().items():
                try:
                    out.append(summary(run_id, loader()))
                except (OSError, ValueError, KeyError) as e:
                    out.append({"id": run_id, "error": str(e)})
            return self.send_json(out)
        if path.startswith("/api/runs/"):
            loader = bundles().get(path[len("/api/runs/"):])
            if not loader:
                return self.send_json({"error": "unknown run"}, 404)
            try:
                return self.send_json(loader())
            except (OSError, ValueError) as e:
                return self.send_json({"error": f"cannot read run: {e}"}, 500)
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
