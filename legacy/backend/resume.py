"""crash resume: find and reload a session after the agent died.

the api remembers every session (GET /sessions), and the client logs each session's
calls to runs/api/<sid>.jsonl. together they let a crashed run pick its session back up:
list the active sessions, take the one it was working, sync the touch count from the
api (the real truth) and replay its log for the story so far - without losing the
touches already spent or the history the target remembers.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_LOG_DIR = ROOT / "runs" / "api"


def active_sessions(client, scenario_id="practice"):
    """all our active sessions for a scenario, newest first (the api orders them)."""
    sessions = client.list_sessions().get("sessions", [])
    return [s for s in sessions
            if s.get("status") == "active" and s.get("scenario_id") == scenario_id]


def latest_active(client, scenario_id="practice"):
    """the most recent active session to resume, or None to start fresh."""
    found = active_sessions(client, scenario_id)
    return found[0] if found else None


def load_api_log(session_id, log_dir=API_LOG_DIR):
    """every logged call and reaction for a session, in order, for replay on resume."""
    path = Path(log_dir) / f"{session_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def replies_so_far(session_id, log_dir=API_LOG_DIR):
    """the target's replies already seen this session, oldest first, to rebuild context."""
    out = []
    for entry in load_api_log(session_id, log_dir):
        event = entry.get("event", {})
        if entry.get("kind") == "event" and event.get("type") == "reply":
            out.append(event.get("body", ""))
    return out
