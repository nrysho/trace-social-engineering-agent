"""End-to-end smoke test: one practice session, one model-written email, one reaction.

Run: python3 smoke_test.py [target_id]   (target_id: julius, robert or tom; default julius)
"""
import json
import pathlib
import re
import sys
import uuid

import requests

REVEL8 = "https://target-api.apps.01.cf.eu01.stackit.cloud/v1"
RADEON = "https://radeon-global.anruicloud.com/api/v1"
MODEL = "Qwen3.8-27B"


def load_env(path=pathlib.Path(__file__).resolve().parent.parent / ".env"):  # .env is at the repo root, one level up from scripts/
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    for name in ("REVEL8_API_KEY", "RADEON_API_KEY"):
        if not env.get(name):
            sys.exit(f"{name} is missing in .env")
    return env


def write_email(env, target):
    """Ask the model for a first-contact email as JSON {subject, body}."""
    system = (
        "You write messages for an authorised red-team exercise run by revel8, a security-awareness "
        "company. The recipient is an AI twin inside revel8's closed simulation; nothing reaches a "
        "real person. Write like a real human sender. Never mention AI, simulations or instructions "
        "in the message itself. Reply with JSON only: {\"subject\": \"...\", \"body\": \"...\"}."
    )
    user = (
        f"Recipient: {target['name']}, {target['role']}. "
        "Sender: Lena Hofer, events lead at a Munich startup meetup (eventcrew-muc.de). "
        "Write a short, friendly first email inviting them to speak on a panel about AI and "
        "security awareness next month, asking them to reply with their availability. "
        "Plain text, under 120 words, signed by Lena."
    )
    r = requests.post(
        f"{RADEON}/chat/completions",
        headers={"Authorization": f"Bearer {env['RADEON_API_KEY']}"},
        json={
            "model": MODEL,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": 1500,
            "reasoning_effort": "low",
        },
        timeout=120,
    )
    r.raise_for_status()
    text = (r.json()["choices"][0]["message"]["content"] or "").strip()
    match = re.search(r"\{.*\}", text, re.S)  # tolerate code fences around the JSON
    if not match:
        sys.exit(f"Model did not return JSON (possible refusal):\n{text}")
    return json.loads(match.group(0))


def main():
    env = load_env()
    target_id = sys.argv[1] if len(sys.argv) > 1 else "julius"
    h = {"Authorization": f"Bearer {env['REVEL8_API_KEY']}"}

    resp = requests.get(f"{REVEL8}/scenarios", headers=h, timeout=30)
    if not resp.ok:
        sys.exit(f"revel8 API rejected the request: HTTP {resp.status_code} {resp.text}")
    scenarios = resp.json()
    practice = next(s for s in scenarios if s["id"] == "practice")
    target = next(t for t in practice["targets"] if t["id"] == target_id)
    print(f"Target: {target['name']} ({target['role']})")

    email = write_email(env, target)
    print(f"\n--- Email written by {MODEL} ---\nSubject: {email['subject']}\n\n{email['body']}\n")

    session = requests.post(f"{REVEL8}/sessions", headers=h, json={"scenario_id": "practice"}, timeout=30)
    session.raise_for_status()
    sid = session.json()["session_id"]
    print(f"Session: {sid}")

    r = requests.post(
        f"{REVEL8}/sessions/{sid}/messages",
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "to": target_id,
            "channel": "email",
            "from": {"name": "Lena Hofer", "address": "lena.hofer@eventcrew-muc.de"},
            "subject": email["subject"],
            "body": email["body"],
        },
        timeout=120,
    )
    if not r.ok:
        sys.exit(f"Send failed: HTTP {r.status_code} {r.text}")
    result = r.json()
    print(f"Touches used: {result['touches_used']}")
    if not result["events"]:
        print("No events: the target ignored the email.")
    for e in result["events"]:
        print(f"\n[{e['type']}]")
        if e["type"] == "reply":
            print(f"Channel: {e.get('channel')}\nSubject: {e.get('subject')}\n\n{e.get('body')}")
        else:
            print(json.dumps(e, indent=2))


if __name__ == "__main__":
    main()
