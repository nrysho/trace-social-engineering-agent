"""revel8 api client: the one place that talks to the target api.

- one method per endpoint (scenarios, channels, sessions, messages, conversations, pages, assets)
- an idempotency key per contact, reused on retries, so a timeout never costs a second touch
- retry 429/502/503/504 with backoff (honour Retry-After); fail fast on 400/422 (they repeat)
- log every call and reaction to runs/api/<session>.jsonl, for crash-resume and the replay viewer

send_message/start_conversation take the schemas dataclasses, and a landing page is
registered before the message that links to it. the orchestrator loop and the
experiment runner call this, not requests. keys come from .env via config.
"""
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import config

# this client duck-types the schemas dataclasses (Message, LandingPage, Sender): it reads
# their attributes and also accepts plain dicts, so it does not import schemas directly.

# REVEL8_API_URL=http://127.0.0.1:8770/v1 runs the agent against the local bench personas (unseen
# people with planted hooks) to test generalisation; unset, it talks to revel8.
BASE = os.environ.get("REVEL8_API_URL", "https://target-api.apps.01.cf.eu01.stackit.cloud/v1")
ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "runs" / "api"
TIMEOUT = 120  # the persona model can take up to 90s, so give it headroom
RETRY_STATUS = (429, 502, 503, 504)  # transient: wait and retry
MAX_ATTEMPTS = 4


class ApiError(Exception):
    """A revel8 response we cannot use. 400/422 mean 'change the request, do not resend'."""

    HINTS = {
        401: "the team key in .env is wrong",
        403: "the scenario is not open yet",
        409: "the session or conversation ended, or the touch budget is used up",
        422: "the request was rejected or the persona declined: change it, do not resend as is",
    }

    def __init__(self, status, text):
        detail = text
        try:
            body = json.loads(text)
            detail = body.get("error") or body.get("detail") or text
        except (ValueError, AttributeError):
            pass
        hint = self.HINTS.get(status, "")
        self.status = status
        super().__init__(f"HTTP {status}: {detail}" + (f" ({hint})" if hint else ""))


class Revel8Client:
    def __init__(self, key=None, log_dir=RUN_DIR):
        key = key or config.load_env().get("REVEL8_API_KEY")
        if not key:
            raise RuntimeError("REVEL8_API_KEY missing: set it in .env")
        self.http = requests.Session()
        self.http.headers["Authorization"] = f"Bearer {key}"
        self.log_dir = Path(log_dir)

    # ----- core request with retries -----

    def _call(self, method, path, body=None, idempotent=False, idem_key=None):
        """One request, retried on transient errors. The idempotency key is set once
        and reused across attempts, so a retry after a timeout never costs a second touch."""
        headers = {}
        if idempotent:
            headers["Idempotency-Key"] = idem_key or str(uuid.uuid4())
        last = "no response"
        for attempt in range(MAX_ATTEMPTS):
            try:
                r = self.http.request(method, BASE + path, json=body, headers=headers, timeout=TIMEOUT)
            except requests.RequestException as e:
                last = f"network error: {e}"
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code in RETRY_STATUS:
                last = f"HTTP {r.status_code}"
                time.sleep(int(r.headers.get("Retry-After", 3 * (attempt + 1))))
                continue
            if not r.ok:
                raise ApiError(r.status_code, r.text)  # 400/422/etc: do not retry
            return r.json() if r.content else {}
        raise ApiError(0, f"gave up after {MAX_ATTEMPTS} attempts ({last})")

    # ----- local log, for crash-resume and the replay viewer -----

    def _log(self, sid, entry):
        if not sid:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        entry = {"at": datetime.now(timezone.utc).isoformat(), **entry}
        with (self.log_dir / f"{sid}.jsonl").open("a") as f:
            f.write(json.dumps(entry) + "\n")

    # ----- read-only -----

    def scenarios(self):
        return self._call("GET", "/scenarios")

    def channels(self):
        return self._call("GET", "/channels")

    # ----- sessions -----

    def create_session(self, scenario_id="practice"):
        s = self._call("POST", "/sessions", {"scenario_id": scenario_id})
        self._log(s.get("session_id"), {"kind": "session.create", "scenario_id": scenario_id})
        return s

    def get_session(self, sid):
        return self._call("GET", f"/sessions/{sid}")

    def list_sessions(self):
        return self._call("GET", "/sessions")

    def get_events(self, sid):
        return self._call("GET", f"/sessions/{sid}/events")

    def end_session(self, sid):
        return self._call("POST", f"/sessions/{sid}/end")

    # ----- landing pages -----

    def register_page(self, sid, page):
        """page is a schemas.LandingPage (or a dict). Register it before linking to it."""
        body = _page_body(page)
        r = self._call("POST", f"/sessions/{sid}/pages", body)
        self._log(sid, {"kind": "page", "page_id": r.get("page_id"), **body})
        return r

    # ----- messages -----

    def send_message(self, msg, sent_at=None, *, qa=None):
        """msg is a schemas.Message. Registers its landing page first, then sends.
        sent_at (ISO 8601) sets the story time, so the target senses how much time
        passed: spacing contacts avoids chasing within seconds, which makes them hold off.
        Returns the raw reaction {message_id, touches_used, events}."""
        sid = msg.session_id
        if msg.landing_page is not None:
            self.register_page(sid, msg.landing_page)
        body = _message_body(msg)
        if sent_at:
            body["sent_at"] = sent_at
        key = msg.idempotency_key or str(uuid.uuid4())
        r = self._call("POST", f"/sessions/{sid}/messages", body, idempotent=True, idem_key=key)
        self._log(sid, {"kind": "sent", "node_id": msg.node_id,
                        "message_id": r.get("message_id"), "touches_used": r.get("touches_used"),
                        "idempotency_key": key, "message": body, "qa": qa})
        for e in r.get("events", []):
            self._log(sid, {"kind": "event", "message_id": r.get("message_id"), "event": e})
        return r

    # ----- conversations (live calls and chats) -----

    def start_conversation(self, sid, to, channel, sender=None, idem_key=None, sent_at=None, *, qa=None):
        """Begin a call/chat. A whole conversation costs one touch, max 10 turns.
        sent_at (ISO 8601) is the story time the phone rings."""
        body = {"to": to, "channel": channel}
        if sender is not None:
            body["from"] = _sender_body(sender)
        if sent_at:
            body["sent_at"] = sent_at
        key = idem_key or str(uuid.uuid4())
        r = self._call("POST", f"/sessions/{sid}/conversations", body,
                       idempotent=True, idem_key=key)
        self._log(sid, {"kind": "call.start", "conversation_id": r.get("conversation_id"),
                        "to": to, "channel": channel, "from": body.get("from"),
                        "touches_used": r.get("touches_used"), "idempotency_key": key,
                        "sent_at": sent_at, "persona_says": r.get("persona_says"), "qa": qa})
        return r

    def say(self, cid, line, sid=None, idem_key=None, sent_at=None, *, qa=None):
        """One turn in an open conversation. Returns {persona_says, ended, events, turns_used}."""
        body = {"say": line}
        if sent_at:
            body["sent_at"] = sent_at
        key = idem_key or str(uuid.uuid4())
        r = self._call("POST", f"/conversations/{cid}/turns", body,
                       idempotent=True, idem_key=key)
        self._log(sid, {"kind": "turn", "conversation_id": cid, "say": line,
                        "idempotency_key": key, "sent_at": sent_at,
                        "persona_says": r.get("persona_says"), "ended": r.get("ended"), "qa": qa})
        for e in r.get("events", []):
            self._log(sid, {"kind": "event", "conversation_id": cid, "event": e})
        return r

    def end_conversation(self, cid):
        return self._call("POST", f"/conversations/{cid}/end")

    # ----- assets (images and declared files) -----

    def upload_asset(self, file_path):
        """Upload an image or PDF, returns {asset_id, type, size}. Costs no touch."""
        path = Path(file_path)
        for attempt in range(MAX_ATTEMPTS):
            with path.open("rb") as fh:
                r = self.http.post(f"{BASE}/assets", files={"file": fh}, timeout=TIMEOUT)
            if r.status_code in RETRY_STATUS:
                time.sleep(3 * (attempt + 1))
                continue
            if not r.ok:
                raise ApiError(r.status_code, r.text)
            return r.json()
        raise ApiError(0, "asset upload gave up after retries")


# ----- translate schemas dataclasses into api json -----

def _sender_body(sender):
    if sender is None:
        return None
    if isinstance(sender, dict):
        return sender
    return {"name": sender.name, "address": sender.address}


def _message_body(msg):
    body = {
        "to": msg.to,
        "channel": msg.channel,
        "from": _sender_body(msg.sender),
        "body": msg.body,
    }
    if msg.subject:
        body["subject"] = msg.subject
    if msg.attachments:
        body["attachments"] = msg.attachments
    return body


def _page_body(page):
    if isinstance(page, dict):
        return {k: v for k, v in page.items() if v not in (None, "")}
    body = {"url": page.url, "title": page.title}
    if page.fields:
        body["fields"] = page.fields
    if page.html:
        body["html"] = page.html
    elif page.text:
        body["text"] = page.text
    return body
