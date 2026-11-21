#!/usr/bin/env python3
"""Talk to the revel8 practice twins by hand.

    python3 chat.py

Needs REVEL8_API_KEY in .env. Type /help inside the chat for commands.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from datetime import datetime

import requests

try:
    import readline  # noqa: F401  arrow keys, Home/End and history in input() (Linux, macOS)
except ImportError:
    readline = None  # Windows consoles have line editing built in

# Set REVEL8_API_URL=http://127.0.0.1:8770/v1 to practise on the local bench personas instead.
API = os.environ.get("REVEL8_API_URL", "https://target-api.apps.01.cf.eu01.stackit.cloud/v1")
ROOT = pathlib.Path(__file__).resolve().parent
LOG_DIR = ROOT / "runs" / "chat"
SUBJECT_CHANNELS = {"email", "calendar_invite", "shared_document"}
MAX_TURNS = 10

HELP = [
    ("/edit", "write the next message in a text editor"),
    ("/to", "switch target"),
    ("/channel", "switch message channel"),
    ("/from", "change sender name and address"),
    ("/attach NAME", "attach a file name to the next message"),
    ("/page", "register a landing page for a link"),
    ("/call", "start a live call or chat (then /hangup)"),
    ("/history", "show the whole session again"),
    ("/new", "start a fresh session"),
    ("/quit", "leave (the session stays open)"),
]

# ---------- look ----------

if os.name == "nt":
    os.system("")  # enables colour codes in Windows terminals
USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _style(code):
    return lambda text: f"\033[{code}m{text}\033[0m" if USE_COLOR else str(text)


bold, dim, cyan, green, yellow, red, magenta = (
    _style(c) for c in ("1", "2", "36", "32", "33", "1;31", "35")
)


def read(prompt):
    """input() with colour codes marked as zero-width, so readline keeps the cursor in place."""
    if readline:
        prompt = re.sub(r"(\033\[[0-9;]*m)", "\001\\1\002", prompt)
    return input(prompt)


def width():
    return min(shutil.get_terminal_size((90, 20)).columns, 100)


def rule(title=""):
    line = "─" * max(0, width() - len(title) - 3)
    print(dim(f"── {title} {line}" if title else "─" * width()))


def block(lines, color):
    """Print text in an indented block with a coloured bar."""
    wrap = width() - 6
    for paragraph in lines.splitlines() or [""]:
        for line in textwrap.wrap(paragraph, wrap) or [""]:
            print(f"  {color('│')} {line}")


# ---------- setup ----------


def load_key():
    env_file = ROOT / ".env"
    if not env_file.exists():
        sys.exit("No .env file. Copy .env.example to .env and add your REVEL8_API_KEY.")
    for line in env_file.read_text().splitlines():
        if line.strip().startswith("REVEL8_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    sys.exit("REVEL8_API_KEY is empty in .env.")


class ApiError(Exception):
    HINTS = {
        401: "the team key in .env is wrong",
        409: "the session has ended or its touches are used up: /new",
        422: "the person declined or the request was invalid: change it, don't resend it as is",
    }

    def __init__(self, status, text):
        detail = text
        try:
            body = json.loads(text)
            detail = body.get("error") or body.get("detail") or text
        except (ValueError, AttributeError):
            pass
        hint = self.HINTS.get(status, "")
        super().__init__(f"HTTP {status}: {detail}" + (f" ({hint})" if hint else ""))


class Api:
    def __init__(self, key):
        self.http = requests.Session()
        self.http.headers["Authorization"] = f"Bearer {key}"

    def call(self, method, path, body=None, contact=False):
        # One idempotency key per contact, reused on retries, so a retry never costs a second touch.
        headers = {"Idempotency-Key": str(uuid.uuid4())} if contact else {}
        last = "no response"
        for attempt in range(4):
            try:
                r = self.http.request(method, API + path, json=body, headers=headers, timeout=120)
            except requests.RequestException as e:
                last = f"network error: {e}"
                time.sleep(3)
                continue
            if r.status_code in (429, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                time.sleep(int(r.headers.get("Retry-After", 3 * (attempt + 1))))
                continue
            if not r.ok:
                raise ApiError(r.status_code, r.text)
            return r.json() if r.content else {}
        raise ApiError(0, f"gave up after retries ({last})")


def ask(prompt, default=""):
    shown = f" {dim('[' + default + ']')}" if default else ""
    answer = read(f"  {prompt}{shown}: ").strip()
    return answer or default


def choose(title, options, default=0):
    """options: list of (label, value). Returns the chosen value."""
    print(bold(title))
    for i, (label, _) in enumerate(options, 1):
        print(f"  {cyan(str(i).rjust(2))}  {label}")
    while True:
        answer = read(f"  choose {dim('[' + str(default + 1) + ']')}: ").strip()
        if not answer:
            return options[default][1]
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1][1]
        print(red("  enter one of the numbers above"))


# ---------- chat ----------


class Chat:
    def __init__(self, api):
        self.api = api
        scenario = next(s for s in api.call("GET", "/scenarios") if s["id"] == "practice")
        self.targets = scenario["targets"]
        self.budget = scenario["touch_budget"]
        channels = api.call("GET", "/channels")
        self.message_channels = [c for c in channels if c["kind"] == "message"]
        self.live_channels = [c for c in channels if c["kind"] != "message"]
        self.names = {t["id"]: t["name"] for t in self.targets}
        self.target = None
        self.channel = "email"
        self.sender = {"name": "Lena Hofer", "address": "lena.hofer@eventcrew-muc.de"}
        self.subject = ""
        self.attachments = []
        self.sid = None
        self.used = 0
        self.call_id = None
        self.call_turns = 0

    # ----- log of this session, kept locally in runs/chat/<session>.jsonl -----

    def log(self, entry):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / f"{self.sid}.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")

    def read_log(self):
        path = LOG_DIR / f"{self.sid}.jsonl"
        return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []

    # ----- display -----

    def first_name(self, target_id):
        return self.names.get(target_id, target_id or "Target").split()[0]

    def show_sent(self, e):
        to = self.first_name(e["to"])
        print(cyan(f"\n  You → {to}") + dim(f"  {e['channel']} · from {e['from']['name']} <{e['from']['address']}>"))
        if e.get("subject"):
            print(f"  {cyan('│')} {bold(e['subject'])}")
        block(e["body"], cyan)
        for a in e.get("attachments", []):
            print(f"  {cyan('│')} {dim('attachment: ' + a['filename'])}")

    def show_event(self, e, who):
        kind = e["type"]
        if kind == "reply":
            print(green(f"\n  {who} → you") + dim(f"  {e.get('channel', '')}"))
            if e.get("subject"):
                print(f"  {green('│')} {bold(e['subject'])}")
            block(e.get("body", ""), green)
        elif kind == "link.opened":
            print(yellow(f"\n  ● {who} opened the link {e.get('url', '')}"))
        elif kind == "page.submitted":
            print(red(f"\n  ★ {who} submitted the page: {', '.join(e.get('fields', []))}"))
        elif kind == "attachment.opened":
            print(red(f"\n  ★ {who} opened the attachment {e.get('filename', '')}"))
        else:
            print(magenta(f"\n  ● {who}: {kind}"))

    def show_events(self, events, who):
        if not events:
            print(dim(f"\n  {who} did not react."))
        for e in events:
            self.show_event(e, who)

    def show_status(self):
        rule()
        print(
            f"  {bold('Session')} {self.sid}  {dim('·')}  {self.used}/{self.budget} touches  {dim('·')}  "
            f"{bold('To')} {self.names[self.target]}  {dim('·')}  {bold('Channel')} {self.channel}  {dim('·')}  "
            f"{bold('From')} {self.sender['name']} <{self.sender['address']}>"
        )
        print(dim("  Type a message and press Enter to send. /edit for a longer message, /help for commands."))
        rule()

    def show_history(self):
        rule("history")
        entries = self.read_log()
        who_by_message = {}
        shown = set()
        for e in entries:
            if e["kind"] == "sent":
                who_by_message[e["message_id"]] = self.first_name(e["to"])
                self.show_sent(e)
            elif e["kind"] == "event":
                shown.add(e["event"].get("id"))
                self.show_event(e["event"], e["who"])
            elif e["kind"] == "call":
                print(magenta(f"\n  📞 {e['channel']} with {self.first_name(e['to'])}"))
            elif e["kind"] == "turn":
                if e.get("say"):
                    print(f"  {cyan('You:')} {e['say']}")
                print(f"  {green(self.first_name(e['to']) + ':')} {e['heard']}")
        remote = self.api.call("GET", f"/sessions/{self.sid}/events")["events"]
        others = [e for e in remote if e.get("id") not in shown]
        if others:
            print(dim("\n  Reactions in this session not sent from this computer:"))
            for e in others:
                who = who_by_message.get(e.get("in_reply_to") or e.get("message_id"), "Target")
                self.show_event(e, who)
        if not entries and not remote:
            print(dim("  Nothing sent yet."))
        print()

    # ----- setup steps -----

    def pick_target(self):
        options = [(f"{t['name']}  {dim(t['role'])}", t["id"]) for t in self.targets]
        current = next((i for i, (_, v) in enumerate(options) if v == self.target), 0)
        self.target = choose("Who do you want to contact?", options, current)

    def session_summary(self, sid):
        """Who was contacted and the last line of the exchange, for the session list."""
        path = LOG_DIR / f"{sid}.jsonl"
        local = [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []
        people = sorted({self.first_name(e["to"]) for e in local if e.get("to")})
        last = ""
        for e in reversed(local):
            if e["kind"] == "event" and e["event"]["type"] == "reply":
                last = f"{e['who']}: {e['event'].get('body', '')}"
            elif e["kind"] == "sent":
                last = f"You: {e['body']}"
            elif e["kind"] == "turn":
                last = f"{self.first_name(e['to'])}: {e['heard']}"
            if last:
                break
        if not last:
            replies = [e for e in self.api.call("GET", f"/sessions/{sid}/events")["events"] if e["type"] == "reply"]
            if replies:
                last = f"Reply: {replies[-1].get('body', '')}"
        who = ", ".join(people) if people else "not started in chat.py here"
        last = " ".join(last.split())
        if len(last) > 60:
            last = last[:57] + "…"
        return who, (f"“{last}”" if last else "no reply yet")

    def pick_session(self):
        sessions = self.api.call("GET", "/sessions")["sessions"]
        active = [s for s in sessions if s["status"] == "active" and s["scenario_id"] == "practice"][:8]
        if active:
            print(dim("  loading open sessions…"))
        options = [("New session  " + dim("(clean slate: they remember nothing)"), None)]
        for s in active:
            started = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00")).astimezone().strftime("%H:%M")
            who, last = self.session_summary(s["session_id"])
            info = f"{started} · {s['touches_used']}/{s['touch_budget']} touches · {who}"
            options.append((f"Continue  {dim(info)}\n        {last}", s))
        choice = choose("Session" + dim("  (open sessions of the whole team, newest first)"), options)
        if choice is None:
            self.new_session()
        else:
            self.sid, self.used = choice["session_id"], choice["touches_used"]
            self.show_history()

    def new_session(self):
        s = self.api.call("POST", "/sessions", {"scenario_id": "practice"})
        self.sid, self.used = s["session_id"], s["touches_used"]
        print(green(f"  New session {self.sid}"))

    def pick_channel(self):
        options = [(f"{c['id'].ljust(28)}{dim(c['arrives_as'])}", c["id"]) for c in self.message_channels]
        current = next((i for i, (_, v) in enumerate(options) if v == self.channel), 0)
        self.channel = choose("Channel", options, current)

    def pick_sender(self):
        print(bold("Sender") + dim("  (what the person sees: a name and a mail address, number or handle)"))
        self.sender = {
            "name": ask("name", self.sender["name"]),
            "address": ask("address", self.sender["address"]),
        }

    # ----- actions -----

    def send(self, text):
        msg = {"to": self.target, "channel": self.channel, "from": self.sender, "body": text}
        if self.channel in SUBJECT_CHANNELS:
            self.subject = ask("Subject", self.subject)
            if self.subject:
                msg["subject"] = self.subject
        if self.attachments:
            msg["attachments"] = [{"filename": a} for a in self.attachments]
        who = self.first_name(self.target)
        print(dim(f"  sending… {who} is reading it (can take up to a minute)"))
        r = self.api.call("POST", f"/sessions/{self.sid}/messages", msg, contact=True)
        self.used = r["touches_used"]
        sent = {"kind": "sent", "message_id": r["message_id"], **msg}
        sent["attachments"] = msg.get("attachments", [])
        self.log(sent)
        print(dim(f"  ✓ sent · {self.used}/{self.budget} touches used"))
        self.attachments = []
        for e in r["events"]:
            self.log({"kind": "event", "who": who, "event": e})
            if e["type"] == "reply" and e.get("subject"):
                self.subject = e["subject"] if e["subject"].lower().startswith("re:") else "Re: " + e["subject"]
        self.show_events(r["events"], who)
        print()

    def start_call(self):
        options = [(f"{c['id'].ljust(14)}{dim(c['arrives_as'])}", c["id"]) for c in self.live_channels]
        channel = choose("Live channel", options)
        who = self.first_name(self.target)
        print(dim(f"  calling {who}…"))
        r = self.api.call(
            "POST", f"/sessions/{self.sid}/conversations",
            {"to": self.target, "channel": channel, "from": self.sender}, contact=True,
        )
        self.call_id, self.call_turns, self.used = r["conversation_id"], 0, r["touches_used"]
        self.log({"kind": "call", "to": self.target, "channel": channel, "conversation_id": self.call_id})
        self.log({"kind": "turn", "to": self.target, "say": "", "heard": r.get("persona_says", "")})
        rule(f"{channel} with {self.names[self.target]} · one touch for the whole call · max {MAX_TURNS} turns")
        print(f"  {green(who + ':')} {r.get('persona_says', '')}")
        print(dim("  Type one line at a time. /hangup to end the call."))

    def say(self, line):
        who = self.first_name(self.target)
        r = self.api.call("POST", f"/conversations/{self.call_id}/turns", {"say": line}, contact=True)
        self.call_turns = r.get("turns_used", self.call_turns + 1)
        heard = r.get("persona_says", "")
        self.log({"kind": "turn", "to": self.target, "say": line, "heard": heard})
        print(f"  {green(who + ':')} {heard}")
        for e in r.get("events", []):
            self.log({"kind": "event", "who": who, "event": e})
            self.show_event(e, who)
        if r.get("ended"):
            print(dim(f"  {who} hung up."))
            self.call_id = None
        elif self.call_turns >= MAX_TURNS:
            print(dim("  Turn limit reached."))
            self.hang_up()

    def hang_up(self):
        if self.call_id:
            try:
                self.api.call("POST", f"/conversations/{self.call_id}/end")
            except ApiError:
                pass
            print(dim("  Call ended."))
        self.call_id = None

    def register_page(self):
        print(bold("Landing page") + dim("  (put this exact URL in your message; they see the title, text and fields)"))
        url = ask("URL", "https://")
        page = {
            "url": url,
            "title": ask("Page title", "Sign in"),
            "text": ask("Visible text", "Please sign in to continue."),
            "fields": [f.strip() for f in ask("Fields", "email, password").split(",") if f.strip()],
        }
        r = self.api.call("POST", f"/sessions/{self.sid}/pages", page)
        self.log({"kind": "page", "page_id": r.get("page_id"), **page})
        print(green(f"  ✓ page registered for {url}"))

    # ----- input -----

    def prompt(self):
        if self.call_id:
            return f"{magenta('📞')} {self.first_name(self.target)} {dim(f'turn {self.call_turns + 1}/{MAX_TURNS}')} › "
        clip = f" 📎{len(self.attachments)}" if self.attachments else ""
        return f"{cyan(self.channel)} → {bold(self.first_name(self.target))} {dim(f'{self.used}/{self.budget}')}{clip} › "

    def edit_message(self):
        """Write a longer message in a text editor; sends when the editor is saved and closed."""
        if self.call_id:
            print(red("  /edit is for messages; in a call, type one line at a time"))
            return
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if not editor:
            editor = "notepad" if os.name == "nt" else next(
                (e for e in ("nano", "vim", "vi") if shutil.which(e)), None)
        if not editor:
            print(red("  no text editor found: set EDITOR, e.g. export EDITOR=nano"))
            return
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
            path = f.name
        print(dim(f"  opening {editor}… save and close it to send, leave it empty to cancel"))
        subprocess.call([*editor.split(), path])
        text = pathlib.Path(path).read_text().strip()
        os.unlink(path)
        if not text:
            print(dim("  cancelled, nothing sent"))
            return
        block(text, cyan)
        self.send(text)

    def command(self, text):
        name, _, arg = text.partition(" ")
        if name == "/help":
            for cmd, what in HELP:
                print(f"  {cyan(cmd.ljust(14))}{what}")
        elif name == "/edit":
            self.edit_message()
        elif name == "/to":
            self.pick_target()
            self.show_status()
        elif name == "/channel":
            self.pick_channel()
            self.show_status()
        elif name == "/from":
            self.pick_sender()
            self.show_status()
        elif name == "/attach":
            if arg.strip():
                self.attachments.append(arg.strip())
                print(dim(f"  {arg.strip()} will be attached to your next message"))
            else:
                print(red("  usage: /attach Invoice_4711.pdf"))
        elif name == "/page":
            self.register_page()
        elif name == "/call":
            self.start_call()
        elif name == "/hangup":
            self.hang_up()
        elif name == "/history":
            self.show_history()
        elif name == "/new":
            self.hang_up()
            self.new_session()
            self.subject = ""
            self.show_status()
        elif name in ("/quit", "/exit"):
            raise EOFError
        else:
            print(red(f"  unknown command {name}, try /help"))

    def run(self):
        print(bold("\n  revel8 · practice chat") + dim("   messages go only to the AI twins in revel8's simulation\n"))
        self.pick_target()
        self.pick_session()
        self.pick_sender()
        self.pick_channel()
        self.show_status()
        while True:
            try:
                text = read(self.prompt()).strip()
                if not text:
                    continue
                if text.startswith("/"):
                    self.command(text)
                elif self.call_id:
                    self.say(text)
                else:
                    self.send(text)
            except ApiError as e:
                print(red(f"  {e}"))


def main():
    api = Api(load_key())
    try:
        chat = Chat(api)
    except ApiError as e:
        hint = ""
        if "Connection refused" in str(e) and "127.0.0.1" in API:
            hint = "\n  The local bench is not running. Start it in another terminal: python3 -m bench.server"
        sys.exit(red(f"  Cannot reach {API}: {e}") + hint)
    try:
        chat.run()
    except (EOFError, KeyboardInterrupt):
        chat.hang_up()
        if chat.sid:
            print(dim(f"\n  Bye. Session {chat.sid} stays open; pick it again to continue."))
    except ApiError as e:
        sys.exit(red(f"  {e}"))


if __name__ == "__main__":
    main()
