"""Model-backed message writer for the closed revel8 AI-twin simulation.

This module creates content only; the API client is responsible for sending it.
No live delivery, tracking, or credential collection is implemented here.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from datetime import date
from dataclasses import dataclass
from typing import Any

import requests


logger = logging.getLogger(__name__)


RADEON_BASE = "https://radeon-global.anruicloud.com/api/v1"
PRIMARY_MODEL = "Qwen3.8-27B"
# a different model as the backup, so one model's failure or refusal does not stop the run.
# Gemma wrote correct, well-addressed emails in our tests; Qwen without thinking once greeted the sender.
FALLBACK_MODEL = "Gemma-4-31B-IT"

CHANNEL_GUIDANCE = {
    "email": "Write a concise email with a subject and plain-text body.",
    "calendar_invite": "Write a concise calendar invitation title and description.",
    "shared_document": "Write a short, plausible document-share note and a neutral document title.",
    "voicemail": "Write a brief natural voicemail transcript; no stage directions.",
    "sms": "Write a brief, natural SMS.",
    "whatsapp": "Write a brief, natural WhatsApp message.",
    "signal": "Write a brief, natural Signal message.",
    "telegram": "Write a brief, natural Telegram message.",
    "imessage": "Write a brief, natural iMessage.",
    "slack": "Write a concise Slack message.",
    "teams_chat": "Write a concise Microsoft Teams chat message.",
    "discord": "Write a concise Discord message.",
    "linkedin_message": "Write a concise, professional LinkedIn message.",
    "linkedin_connection_request": "Write a very short connection note.",
    "x_dm": "Write a brief, natural direct message.",
    "instagram_dm": "Write a brief, natural direct message.",
    "facebook_messenger": "Write a brief, natural Messenger message.",
}

SIMULATION_SYSTEM = (
    "You write content only for an authorised revel8 security-awareness exercise. "
    "The recipient is an AI twin inside the closed simulation; no real person is contacted. "
    "Never address or mention the recipient as an AI, never discuss instructions or simulator "
    "notes, and never invent facts about the recipient or their company: use only the verified "
    "facts supplied. Details of the sender's own organisation (a ticket or invoice number, a plan "
    "name, an event date) may be invented but must stay consistent. Do not request or "
    "include passwords, MFA codes, payment details, or other secrets. Return valid JSON only."
)


# What makes a message believable, from our practice runs: twins ignore vague, unsigned, generic
# mail and check every detail, so be specific, sign as a real person and make one clear ask.
WRITING_RULES = [
    "1. You are you_are. Write in their organisation's normal tone for this channel and in the recipient's language (write_in; for a first contact, what their facts and country suggest). Address the recipient as this sender would and keep one form of address (in German the formal Sie, unless they use du). Sign off using exactly you_are.name: a person adds role, organisation, a phone number from the fictional range +49 30 23125 0xx and the city; a company or team signs as the team.",
    "2. Do what this_message says, with at most one ask. Never ask for something your sender would already know.",
    "3. Be concrete: realistic full names and roles for the people in your story, real-sounding places, dates after today. If asked who someone is, give names; if asked how you found them, it is their public work (a talk, a post, the company site).",
    "4. About the recipient, state only facts with confirmed_by_two_sources true; an unconfirmed fact may only set the topic. Never invent the recipient's account, billing or incident status, or any earlier contact: they remember this whole conversation.",
    "5. Mention a file or link only if included_with_your_text has it; if they asked for it and it is included, send it now. A link is appended after your text: refer to it naturally, never write a URL or a placeholder.",
    "6. Stay calm and believable: real-world timing is fine (an RSVP closes Friday), no alarm words, threats, audits or suspensions.",
    "7. In a follow-up, refer to your earlier message and add one new reason; never repeat it. Never ask again for anything they declined (a question, a file, a form): give them what they asked for instead.",
    "8. learned_earlier_in_this_session lists other senders' contacts this person already received and how they reacted. You are a different sender: never mention those contacts, but use what they reveal (language, what they refuse, what they ask for, their tools, who handles what).",
    "9. Never quote internal_plan_do_not_quote or words like pretext, hook or target. The subject reads like a real one from this sender. Plain text, under 130 words, no markdown. Reply with the JSON object only.",
]


_GERMAN = re.compile(r"\b(ich|nicht|und|der|die|das|bitte|danke|schicken|gerne|gern|ist|wir|sie|mir|mit|auf)\b", re.I)


_GERMAN_GREETING = re.compile(r"\b(hallo|guten (morgen|tag|abend)|servus|moin|grüß|ja bitte)\b", re.I)
_GERMAN_SPEAKING = ("germany", "deutschland", "austria", "österreich", "switzerland", "schweiz", "de", "at", "ch")


def _language_of(text: str) -> str | None:
    """German or English for a piece of their text; a short greeting is enough ("Müller, guten Morgen.")."""
    text = str(text or "")
    words = len(text.split())
    if _GERMAN_GREETING.search(text):
        return "German"
    if words < 4:
        return None
    return "German" if len(_GERMAN.findall(text)) >= max(2, words // 12) else "English"


def _reply_language(theirs: list[str] | None, country: str = "") -> str | None:
    """the language to write or speak in: what the recipient last used (their own words only),
    else their country's (recon's country), so we never open in English with someone who answers
    the phone in German."""
    for text in reversed(list(theirs or [])):
        lang = _language_of(text)
        if lang:
            return lang
    return "German" if str(country or "").strip().casefold() in _GERMAN_SPEAKING else None


def _sourced_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every sourced recon fact, flagged confirmed or not. Recon confirms mostly DNS tool records;
    the events, open roles, interests and activity that make a hook are single-source. The writer
    states confirmed facts and only alludes to the topic of unconfirmed ones (never quoting them),
    which the quality gate checks."""
    return [{"category": f.get("category"), "value": f.get("value"), "source_url": f.get("source_url"),
             "confirmed_by_two_sources": f.get("verified") is True}
            for f in facts if isinstance(f, dict) and f.get("source_url") and f.get("value")]


# What each planned move (strategy.plan_next_move intent) asks of the message.
MOVE_GUIDANCE = {
    "introduce": "First contact. Introduce yourself and a concrete, relevant reason for writing that fits the recipient's verified facts. Ask only for interest or a quick reply (a yes, a time that suits); nothing internal, no link or file unless included_with_your_text has one.",
    "nudge": "They did not answer. A short, friendly follow-up that adds one new, concrete reason; no pressure and no repeat of the first message.",
    "answer_build": "They replied with some doubt. Answer their questions concretely, add one detail that makes you more credible, and keep the ask small.",
    "reassure": "They are doubtful. Address the doubt directly and calmly with something they can check about you or your organisation (your role, the publication or event, an official next step); make no new ask. Never invent a past meeting, call or referral.",
    "make_ask": "They engaged. Now ask one direct question whose honest answer is an internal detail the plan needs (which tool or VPN client they use, who approves or decides, a number, an internal process), framed as something your story genuinely needs, so they can answer in one line of their reply. If a file is included, mention it in one sentence. Build on what they said.",
    "push_complete": "They opened the link but did not finish. Briefly help them complete it, as the sender would.",
}


@dataclass(frozen=True)
class ModelConfig:
    api_key: str
    fallback_model: str
    base_url: str = RADEON_BASE
    primary_model: str = PRIMARY_MODEL
    timeout: int = 120


def _completion(config: ModelConfig, model: str, messages: list[dict[str, str]]) -> str:
    # Token Factory rate-limits busy models (429): wait as told (or a few seconds) and try again.
    for attempt in range(3):
        try:
            return _completion_once(config, model, messages)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status not in (429, 502, 503, 504) or attempt == 2:
                raise
            wait = e.response.headers.get("Retry-After", "") if e.response is not None else ""
            time.sleep(float(wait) if wait.replace(".", "", 1).isdigit() else 3 * (attempt + 1))
    raise RuntimeError("unreachable")


def _completion_once(config: ModelConfig, model: str, messages: list[dict[str, str]]) -> str:
    response = requests.post(
        f"{config.base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {config.api_key}"},
        json={
            "model": model,
            "messages": messages,
            "max_tokens": 1400,
            # no thinking: ~8 s instead of ~50 s per message, and the thinking can no longer use
            # up max_tokens and leave an empty answer (measured on Token Factory)
            "reasoning_effort": "none",
        },
        timeout=config.timeout,
    )
    response.raise_for_status()
    text = (response.json()["choices"][0]["message"].get("content") or "").strip()
    if not text:
        raise ValueError(f"{model} returned an empty answer")
    return text


def _parse_json(content: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise ValueError("model response did not contain a JSON object")
    result = json.loads(match.group(0))
    if not isinstance(result, dict):
        raise ValueError("model response JSON must be an object")
    return result


def _looks_like_refusal(content: str) -> bool:
    lower = content.casefold()
    return not content or any(phrase in lower for phrase in (
        "i cannot help", "i can't help", "i cannot assist", "i can't assist",
        "unable to help with", "unable to assist with",
    ))


def generate_message(
    config: ModelConfig,
    *,
    target: dict[str, Any],
    approach: dict[str, Any],
    sender: dict[str, Any],
    verified_facts: list[dict[str, Any]],
    conversation_history: list[dict[str, str]] | None = None,
    attachment: str | None = None,
    link_follows: bool = False,
) -> dict[str, Any]:
    """Generate a structured message; use fallback automatically on refusal.

    ``attachment`` (a file name) and ``link_follows`` say what actually goes out with the text,
    so the message never refers to a file or link that is not there.

    Returns ``{content, model, fallback_used, refusal_logged}``. The caller can
    attach this decision to its run tree. Facts without source URLs are omitted.
    """
    channel = str(approach["channel"])
    if channel not in CHANNEL_GUIDANCE and channel not in {"phone_call", "video_call", "teams_call", "live_chat"}:
        raise ValueError(f"unsupported channel: {channel}")
    facts = _sourced_facts(verified_facts)
    payload = {
        "task": CHANNEL_GUIDANCE.get(channel, "Write only the caller's next spoken line for a live call."),
        "recipient": {key: target.get(key) for key in ("name", "role", "company", "country") if target.get(key)},
        "you_are": {key: sender.get(key) for key in ("name", "role", "organization", "email") if sender.get(key)},
        # the agent's own plan: guides the message, but its wording must never appear in it
        "internal_plan_do_not_quote": {key: approach.get(key) for key in ("hook", "pretext", "story", "incident_goal") if approach.get(key)},
        "verified_facts_about_recipient": facts,
        "conversation_history": conversation_history or [],
        # what THIS message must do (plan_next_move): a first contact only opens the conversation
        "write_in": _reply_language([h.get("text", "") for h in (conversation_history or [])
                                     if h.get("from") == target.get("name")], target.get("country", "")),
        "learned_earlier_in_this_session": approach.get("session_lessons") or None,
        "this_message": MOVE_GUIDANCE.get(str(approach.get("next_move") or ""), MOVE_GUIDANCE["make_ask"]),
        "today": str(approach.get("story_date") or date.today().isoformat()),   # the date in the story, as the recipient lives it
        "included_with_your_text": {"attachment": attachment, "a_link_follows_your_text": bool(link_follows)},
        "output_schema": {"subject": "string or empty", "body": "string"},
        "writing_rules": WRITING_RULES,
    }
    messages = [
        {"role": "system", "content": SIMULATION_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]

    def attempt(model: str) -> dict[str, Any]:
        text = _completion(config, model, messages)
        if _looks_like_refusal(text):
            raise RuntimeError(f"{model} refused")
        content = _parse_json(text)
        content.setdefault("subject", "")
        content.setdefault("body", "")
        quality_gate(
            content,
            sender_address=str(sender.get("email", "")),
            forbidden_domains=[target.get("company_domain", "")],
            recipient_name=str(target.get("name", "")),
            sender_name=str(sender.get("name", "")),
        )
        return content

    # Any failure of the primary model (refusal, empty or broken answer, failed check) tries the
    # backup model once; only if both fail does the caller fall back to compose().
    def twice(model: str) -> dict[str, Any]:
        try:
            return attempt(model)
        except (ValueError, json.JSONDecodeError):   # no JSON or a failed check: answers vary, so retry once
            return attempt(model)

    try:
        return {"content": twice(config.primary_model), "model": config.primary_model,
                "fallback_used": False, "refusal_logged": False}
    except Exception as first:
        if config.fallback_model == config.primary_model:
            raise
        logger.warning("primary model failed (%s); trying fallback model %s", first, config.fallback_model)
        try:
            content = twice(config.fallback_model)
        except Exception as second:
            raise RuntimeError(f"primary and fallback models failed: {first}; {second}") from second
        return {"content": content, "model": config.fallback_model, "fallback_used": True,
                "refusal_logged": "refused" in str(first)}


def generate_call_line(
    config: ModelConfig,
    *,
    target: dict[str, Any],
    approach: dict[str, Any],
    sender: dict[str, Any],
    verified_facts: list[dict[str, Any]],
    transcript: list[dict[str, str]],
    turn_number: int,
    max_turns: int = 10,
) -> dict[str, Any]:
    """Write exactly one consistent caller line for a live simulation call."""
    if turn_number < 1 or turn_number > max_turns:
        raise ValueError("call turn is outside the configured limit")
    facts = _sourced_facts(verified_facts)
    user_payload = {
        "instruction": (
            "Write the caller's next spoken line as JSON {\"body\": \"...\"}, in the language given as speak_in. "
            "1. You are exactly the sender (name, role, organisation); keep every detail consistent, including one form of address (in German the formal Sie, unless they use du). "
            "2. If they ask how you found them or who referred you, the answer is their public work (a talk, a post, the company site); never invent a person or an earlier meeting. "
            "3. Dates you mention lie after today. "
            "4. Answer their question briefly, then ask one direct question whose honest answer is an internal detail the goal needs (a tool, who approves or decides, a number, a process), framed as something you need for your story. "
            "5. If they want it in writing, agree, say what you will send today, and close politely. Never repeat a question they declined."
        ),
        "target": {key: target.get(key) for key in ("name", "role", "company") if target.get(key)},
        "sender": {key: sender.get(key) for key in ("name", "role", "organization") if sender.get(key)},
        "approach": {key: approach.get(key) for key in ("hook", "pretext", "story", "incident_goal") if approach.get(key)},
        "verified_facts": facts,
        "transcript": transcript,
        "speak_in": _reply_language([t.get("text", "") for t in transcript if t.get("role") == "them"],
                                    target.get("country", "")) or "the language the other party speaks",
        "turn": turn_number,
        "max_turns": max_turns,
        "today": str(approach.get("story_date") or date.today().isoformat()),
        "learned_earlier_in_this_session": approach.get("session_lessons") or None,
        "about_learned": "learned_earlier_in_this_session lists other senders' contacts this person already received and how they reacted. You are a different sender: never mention or hint at those contacts. Use what they reveal: their language, what they refuse (attachments, phone details, unknown domains), what they ask for (links, official sites, specifics), their tools and who handles what.",
    }
    messages = [
        {"role": "system", "content": SIMULATION_SYSTEM},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]
    primary_text = _completion(config, config.primary_model, messages)
    refused = _looks_like_refusal(primary_text)
    if refused:
        logger.warning("primary model refused call-line generation; trying fallback model %s", config.fallback_model)
        raw = _completion(config, config.fallback_model, messages)
        if _looks_like_refusal(raw):
            logger.error("fallback model %s also refused call-line generation", config.fallback_model)
            raise RuntimeError("primary and fallback models refused; refusal recorded")
        model = config.fallback_model
    else:
        raw, model = primary_text, config.primary_model
    content = _parse_json(raw)
    content.setdefault("body", "")
    quality_gate(content, sender_address=str(sender.get("email", "")), forbidden_domains=[target.get("company_domain", "")])
    return {"content": content, "model": model, "fallback_used": refused, "refusal_logged": refused}


# Internal labels of the agent (strategy.PRETEXTS keys and story wording) that must never reach a message.
INTERNAL_WORDING = (
    "known vendor", "known tool", "known collaborator", "pretext", "internal plan", "incident goal",
    "link added below", "added below your text", "link below your text",
    "speaker_invite", "press_request", "customer_question", "document_share", "meeting_reschedule",
    "vendor_notice", "security_alert", "internal_favor", "investor_intro",
    "invoice_approval", "hr_policy", "it_helpdesk", "exec_request",
)
GREETING = re.compile(r"^\s*(?:hi|hello|hey|dear|good (?:morning|afternoon|evening))\s+([A-ZÄÖÜ][\w'’-]+)", re.I)


def quality_gate(
    message: dict[str, Any],
    *,
    sender_address: str = "",
    forbidden_domains: list[str] | None = None,
    recipient_name: str = "",
    sender_name: str = "",
) -> None:
    """Raise ValueError for common rule, placeholder, domain or addressing violations."""
    text = f"{message.get('subject', '')}\n{message.get('body', '')}"
    if not message.get("body", "").strip():
        raise ValueError("message body is empty")
    lower = text.casefold()
    blocked = ("as an ai", "ai twin", "simulator", "system prompt", "ignore previous instructions", "[insert", "<recipient>")
    found = [phrase for phrase in blocked if phrase in lower]
    if found:
        raise ValueError("quality gate rejected AI-directed or placeholder wording: " + ", ".join(found))
    leaked = [phrase for phrase in INTERNAL_WORDING if phrase in lower]
    if leaked:
        raise ValueError("quality gate rejected internal plan wording: " + ", ".join(leaked))
    if re.search(r"\[[A-Za-z][A-Za-z _-]{1,24}\d*\]", text):
        raise ValueError("quality gate rejected a bracket placeholder such as [article1]")
    if re.search(r"https?://|\bwww\.", text, re.I):
        # the only link that goes out is the registered page we append; any other URL has no page behind it
        raise ValueError("quality gate rejected a URL in the text; the registered link is appended separately")
    greeting = GREETING.match(str(message.get("body", "")))
    if greeting:
        greeted = greeting.group(1).casefold()
        recipient_first = recipient_name.split()[0].casefold() if recipient_name.split() else ""
        sender_first = sender_name.split()[0].casefold() if sender_name.split() else ""
        if sender_first and greeted == sender_first and greeted != recipient_first:
            raise ValueError(f"quality gate rejected a greeting to the sender ({greeting.group(1)}) instead of the recipient")
    domains = [domain.strip().lower().removeprefix("www.") for domain in forbidden_domains or []]
    sender_domain = sender_address.rpartition("@")[2].lower().removeprefix("www.")
    if sender_domain and sender_domain in domains:
        raise ValueError("quality gate rejected a sender using the recipient organisation's domain")
    referenced_domains = {
        match.casefold().removeprefix("www.")
        for match in re.findall(r"(?:https?://|www\.)?([a-z0-9.-]+\.[a-z]{2,})(?:/|\b)", text, re.I)
    }
    if referenced_domains.intersection(filter(None, domains)):
        raise ValueError("quality gate rejected a link using the recipient organisation's domain")


def make_landing_page(*, title: str, heading: str, body: str, fields: list[str] | None = None) -> dict[str, Any]:
    """Create a static simulation page with no scripts, network assets, or secrets."""
    safe_fields = [field for field in (fields or []) if field in {"name", "email", "availability", "rsvp"}]
    inputs = "".join(
        f'<label>{html.escape(field.title())}<input name="{html.escape(field, quote=True)}"></label>'
        for field in safe_fields
    )
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title><main><h1>{html.escape(heading)}</h1>"
        f"<p>{html.escape(body)}</p><form>{inputs}</form></main></html>"
    )
    return {"title": title, "html": page, "fields": safe_fields}


def make_file_name(label: str, extension: str = "pdf") -> str:
    """Return a safe filename only; no attachment content is created."""
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-_")[:64] or "document"
    suffix = re.sub(r"[^A-Za-z0-9]+", "", extension).lower()[:8] or "pdf"
    return f"{stem}.{suffix}"


def _load_senders(path: str = "") -> dict[str, Any]:
    import json as _json
    import pathlib as _pathlib
    p = _pathlib.Path(path) if path else _pathlib.Path(__file__).with_name("senders.json")
    try:
        return _json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"pretexts": {}}


SENDERS = _load_senders()


def _brand_tld(target_domain: str) -> tuple[str, str]:
    host = str(target_domain or "").strip().lower().removeprefix("www.").split("/")[0]
    labels = [p for p in host.split(".") if p]
    if len(labels) >= 2:
        return labels[-2], labels[-1]
    return (labels[0] if labels else "company"), "com"


def _fill(template: str, brand: str, tld: str) -> str:
    return str(template).replace("{brand}", brand).replace("{tld}", tld)


def _local_part(name: str) -> str:
    """'Dr. Tom Müller' -> 'tom.mueller': umlauts spelled out, titles dropped, ASCII only."""
    import unicodedata
    text = str(name).lower()
    for k, v in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(k, v)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"\b(dr|prof|mr|mrs|ms)\.?\s+", "", text)
    slug = re.sub(r"[^a-z0-9]+", ".", text).strip(".")
    return slug or "contact"


# ----- sender and page domains must be ones an attacker could still register -----
# A domain someone already owns (okta-verify.com, secure-login.com, ...) may be that organisation's
# own: a page or sender there voids the session. So every domain we use is checked for NS records
# (dns.google, as recon already uses) and replaced by a free variant when it is taken.
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "or", "ne"}
_TAKEN: dict[str, bool | None] = {}


def _registrable(domain: str) -> str:
    """The part someone registers: 'a.b.secure-login.com' -> 'secure-login.com', 'x.co.uk' kept."""
    labels = [p for p in str(domain).lower().strip(".").split(".") if p]
    keep = 3 if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2 else 2
    return ".".join(labels[-keep:])


def domain_taken(domain: str) -> bool | None:
    """True if the registrable domain already exists (has NS records), False if it does not
    (NXDOMAIN), None if DNS could not tell."""
    base = _registrable(domain)
    if base not in _TAKEN:
        try:
            r = requests.get("https://dns.google/resolve", params={"name": base, "type": "NS"}, timeout=8)
            status = r.json().get("Status")
            _TAKEN[base] = True if status == 0 else False if status == 3 else None
        except (requests.RequestException, ValueError):
            _TAKEN[base] = None
    return _TAKEN[base]


def free_domain(domain: str) -> str:
    """domain itself if nobody owns it, else the first unregistered variant of its registrable
    part ('okta-verify.com' -> 'okta-verify-notice.com'), keeping any subdomain in front."""
    domain = str(domain).lower().strip(".")
    if domain_taken(domain) is not True:
        return domain
    base = _registrable(domain)
    prefix = domain[: -len(base)]
    label, _, suffix = base.partition(".")
    # closest lookalikes first: the same name on another ending, then a hyphen, then an added word.
    # No homoglyphs (Cyrillic 'е'): browsers show such domains as xn--… punycode, which looks worse.
    near = [f"{label}.{t}" for t in ("co", "io", "net", "de", "eu", "org", "com") if t != suffix]
    near += [f"{label[:i]}-{label[i:]}.{suffix}" for i in range(3, len(label) - 2) if "-" not in label][:2]
    near += [f"{label}-{extra}.{suffix}" for extra in ("notice", "mail", "portal", "service", "online", "secure-mail")]
    for candidate in near:
        if domain_taken(candidate) is False:
            logger.info("domain %s is registered; using %s", base, candidate)
            return prefix + candidate
    raise RuntimeError(f"no unregistered variant of {base}")


# Tools worth impersonating, by keyword found in the target's vendors_and_tools facts.
# When recon shows the target uses one, we lookalike THAT brand instead of a generic
# vendor — a DocuSign user gets a DocuSign-shaped lure. `kind` picks which pretexts it
# fits: "identity" (sign-in/credentials), "docs" (file/signature shares), "billing".
VENDOR_LOOKALIKES: tuple[dict[str, Any], ...] = (
    {"match": ("docusign",), "brand": "DocuSign", "domain": "docusign-notifications.net", "kind": "docs"},
    {"match": ("dropbox",), "brand": "Dropbox", "domain": "dropbox-share.net", "kind": "docs"},
    {"match": ("google drive", "google workspace", "gmail", "google"), "brand": "Google Workspace", "domain": "workspace-notice.com", "kind": "identity"},
    {"match": ("microsoft", "365", "outlook", "sharepoint"), "brand": "Microsoft 365", "domain": "m365-security.com", "kind": "identity"},
    {"match": ("okta",), "brand": "Okta", "domain": "okta-verify.com", "kind": "identity"},
    {"match": ("workday",), "brand": "Workday", "domain": "workday-login.com", "kind": "identity"},
    {"match": ("github",), "brand": "GitHub", "domain": "github-security.net", "kind": "identity"},
    {"match": ("aws", "amazon web"), "brand": "AWS", "domain": "aws-billing.net", "kind": "billing"},
    {"match": ("salesforce",), "brand": "Salesforce", "domain": "salesforce-login.net", "kind": "identity"},
    {"match": ("sap",), "brand": "SAP", "domain": "sap-portal.net", "kind": "billing"},
    {"match": ("hubspot",), "brand": "HubSpot", "domain": "hubspot-billing.net", "kind": "billing"},
    {"match": ("sendgrid",), "brand": "SendGrid", "domain": "sendgrid-mail.net", "kind": "billing"},
    {"match": ("slack",), "brand": "Slack", "domain": "slack-alerts.com", "kind": "identity"},
)

# Which vendor kind each pretext should impersonate when a matching tool is known.
_PRETEXT_VENDOR_KIND = {"security_alert": "identity", "document_share": "docs", "vendor_notice": "billing"}


def _tool_vectors(profile_or_facts: Any) -> list[str]:
    facts = profile_or_facts.get("facts", []) if isinstance(profile_or_facts, dict) else (profile_or_facts or [])
    return [str(f.get("value", "")) for f in facts if isinstance(f, dict) and f.get("category") == "vendors_and_tools"]


def detect_vendor(pretext: str, vendor_texts: list[str]) -> dict[str, Any] | None:
    """Find a tool the target uses that fits this pretext, to impersonate directly."""
    kind = _PRETEXT_VENDOR_KIND.get(pretext)
    if not kind:
        return None
    blob = " ".join(vendor_texts).lower()
    # prefer a tool of the matching kind; fall back to any known tool
    for want_kind in (kind, None):
        for v in VENDOR_LOOKALIKES:
            if (want_kind is None or v["kind"] == want_kind) and any(m in blob for m in v["match"]):
                return v
    return None


def _org_from_domain(domain: str) -> str:
    """'feld-talent-search.de' -> 'Feld Talent Search'."""
    label = str(domain).split(".")[0]
    return " ".join(w.capitalize() for w in re.split(r"[-_]+", label) if w) or "Our team"


def _unclash(name: str, avoid_first_name: str, domain: str) -> str:
    """Offline fallback only: a fixed sender sharing the recipient's first name signs as its
    organisation instead (generated personas avoid the clash by rule)."""
    first = name.split(" ")[0]
    if not avoid_first_name or first.casefold() != avoid_first_name.casefold():
        return name
    return _org_from_domain(domain)


def build_sender(pretext: str, target_domain: str, colleague: str = "", vendors: list[str] | None = None,
                 avoid_first_name: str = "") -> dict[str, Any]:
    """Pick a lookalike/invented sender for a pretext, derived from the target's brand.

    Domains are registrable lookalikes an attacker could own, never the target's own
    domain (the quality gate still enforces that on the final message).
    """
    brand, tld = _brand_tld(target_domain)
    entry = SENDERS.get("pretexts", {}).get(pretext) or {
        "technique": "invented_third_party", "sender_name": "Alex Wagner", "role": "contact", "domain": "mail-relay-eu.com", "page": None,
    }
    name = entry.get("sender_name", "Alex Wagner")
    if name == "{colleague}":
        # a named colleague only when recon found one; never a practice founder for an unseen target
        name = colleague or "Alex Wagner"
    domain = _fill(entry.get("domain", "mail-relay-eu.com"), brand, tld)
    if entry.get("sender_name") != "{colleague}":
        name = _unclash(name, avoid_first_name, domain)
    technique = entry.get("technique", "invented_third_party")
    # Vendor vector: if the target uses a tool that fits this pretext, impersonate it.
    vendor = detect_vendor(pretext, vendors or [])
    if vendor:
        name = vendor["brand"]
        domain = vendor["domain"]
        technique = f"vendor_impersonation:{vendor['brand']}"
    domain = free_domain(domain)
    return {
        "name": name,
        "address": f"{_local_part(name)}@{domain}",
        "domain": domain,
        "technique": technique,
        "role": entry.get("role", ""),
    }


# Who sends a message, per kind of sender (strategy.Pretext.sender). Every message gets a generated
# sender that fits its story; the fixed senders.json entry is only the offline/failure fallback.
SENDER_KIND_RULES = {
    "outsider": [
        "The sender works at an invented organisation that would naturally write about this topic (e.g. a monitoring vendor for a cloud-cost topic, an executive search firm for a hiring topic, an events agency for a speaking invitation).",
        "The role fits the question being asked (an engineer for technical questions, a partner for investors, a researcher or editor for press).",
        "The name is a realistic full name from the recipient's region; the first name differs from the recipient's.",
        "The domain is a plausible, registrable domain for that invented organisation.",
    ],
    "vendor": [
        "The sender writes for a tool, service or supplier the recipient's company uses (see impersonated_tool or the facts), or for the recipient's own IT team if none fits.",
        "The name is either a team name such as '<Tool> Account Security' or '<Company> IT Service Desk', or a support agent's realistic full name.",
        "The organisation is the tool or team being impersonated.",
        "The domain is a believable lookalike an attacker could register (an extra word or hyphen, a different ending), never the tool's real domain.",
    ],
    "colleague": [
        "The sender is a colleague at the recipient's company. If known_colleague is given, use exactly that name; otherwise invent a realistic full name from the recipient's region whose first name differs from the recipient's.",
        "The role is one that would plausibly make this request of the recipient (finance for an invoice, operations for a document, an assistant for a meeting).",
        "The organisation is the recipient's company.",
        "The domain is a lookalike of the company's own domain that an attacker could register (a small typo, an extra word, a different ending), never the real domain.",
    ],
}
REAL_ORG_DOMAINS = ("google.com", "microsoft.com", "linkedin.com", "docusign.com", "okta.com", "apple.com",
                    "amazon.com", "slack.com", "zoom.us", "github.com", "salesforce.com", "hubspot.com",
                    "atlassian.com", "notion.so", "dropbox.com", "box.com", "office.com", "outlook.com")


def generate_sender_persona(config: "ModelConfig", *, target: dict[str, Any], approach: dict[str, Any],
                            facts: list[dict[str, Any]], colleague: str = "", tool: str = "",
                            avoid_names: list[str] | None = None) -> dict[str, Any]:
    """Invent who sends this message so the identity fits the story and the kind of sender
    (approach["sender_kind"]: outsider, vendor or colleague). No fixed name is shown to the
    model, so it cannot copy one. Returns {name, role, organization, domain, address};
    raises if neither model gives a valid persona."""
    kind = approach.get("sender_kind") if approach.get("sender_kind") in SENDER_KIND_RULES else "outsider"
    recipient_first = str(target.get("name", "")).split()[0].casefold() if target.get("name") else ""
    own = str(target.get("company_domain", "")).lower().removeprefix("www.")
    payload = {
        "task": "Invent the sender of a message for this plan. Return JSON only.",
        "recipient": {k: target.get(k) for k in ("name", "role", "company") if target.get(k)},
        "company_domain": own or None,
        "recipient_country": target.get("country") or None,
        "channel": approach.get("channel"),
        "internal_plan_do_not_quote": {k: approach.get(k) for k in ("hook", "pretext", "story") if approach.get(k)},
        "facts_about_recipient": [f.get("value") for f in facts if f.get("value")][:12],
        "known_colleague": colleague or None,
        "impersonated_tool": tool or None,
        "names_already_used_in_this_conversation": avoid_names or None,
        "rules": SENDER_KIND_RULES[kind] + [
            "Never use a real company's own domain and never the recipient's company domain.",
            "An outside organisation and its domain ending fit the recipient's country (recipient_country), e.g. a .de domain for Germany.",
            "The recipient remembers every earlier sender: the first and last name must both differ from names_already_used_in_this_conversation.",
        ],
        "output_schema": {"name": "string", "role": "string", "organization": "string", "domain": "example-org.de"},
    }
    messages = [{"role": "system", "content": SIMULATION_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    problems = []
    for model in (config.primary_model, config.fallback_model):
        try:
            out = _parse_json(_completion(config, model, messages))
        except Exception as e:
            problems.append(f"{model}: {e}")
            continue
        name = colleague if (kind == "colleague" and colleague) else " ".join(str(out.get("name", "")).split())
        domain = str(out.get("domain", "")).strip().lower().removeprefix("www.")
        words = name.split()
        used = {w.casefold() for n in (avoid_names or []) for w in n.split()[:1]}
        if not (kind == "colleague" and colleague) and words and words[0].casefold() in used:
            problems.append(f"{model}: reused an earlier sender's first name ({name})")
            continue
        person = kind != "vendor"            # a vendor may sign as a team ("Acme Account Security")
        if (not words or len(words) > 6 or (person and len(words) < 2)
                or (person and words[0].casefold() == recipient_first)
                or not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", domain)
                or (own and (domain == own or domain.endswith("." + own)))
                or any(domain == d or domain.endswith("." + d) for d in REAL_ORG_DOMAINS)
                or not str(out.get("organization", "")).strip()):
            problems.append(f"{model}: invalid persona {out}")
            continue
        domain = free_domain(domain)           # a domain someone already owns could be theirs
        return {"name": name, "role": str(out.get("role", "")).strip(), "organization": str(out["organization"]).strip(),
                "domain": domain, "address": f"{_local_part(name)}@{domain}"}
    raise RuntimeError("no valid sender persona: " + "; ".join(problems))


# ----- the look: landing pages and vendor mails as the sender would really make them -----
# revel8 renders every eval mail (~700 px) and page (~1200 px) in Chrome with scripts off and nothing
# loaded from the network, then rates: fits the sender, right format, clean, details hold. So the HTML
# is self-contained (inline styles, system fonts, and only registered local image assets): a
# context-matched page heading, accessible form controls, and a consistent footer.
_BRAND_COLOURS = ("#1a73e8", "#0b6e4f", "#5b3cc4", "#c2410c", "#0f766e", "#1e3a8a", "#9d174d", "#334155")
_FIELD_LABELS = {"email": "Work email", "password": "Password", "name": "Full name", "availability": "Your availability",
                 "username": "Username", "phone": "Phone number", "company": "Company", "job_title": "Job title",
                 "internal_tool": "Tools currently in place on your side (helps our moderator prepare)",
                 "approver": "Who approves this invoice on your side?", "vpn_client": "VPN client on this device"}
_PAGE_COPY = {   # heading, text, button: what this kind of page says (never the internal plan)
    "security_alert": ("Verify it's you", "We noticed a sign-in from a new device. Sign in to review the activity and keep your account secure.", "Continue"),
    "vendor_notice": ("Review your account", "Sign in to review your account and keep your subscription running without interruption.", "Sign in"),
    "document_share": ("A document was shared with you", "Sign in with your work account to open the document.", "Open document"),
    "invoice_approval": ("Confirm invoice 2026-1184", "Confirm the invoice and tell us who approves it on your side, so payment is not delayed.", "Confirm invoice"),
    "hr_policy": ("Acknowledge the updated policy", "Sign in with your work account to read and acknowledge the updated policy.", "Sign in"),
    "it_helpdesk": ("Confirm your device", "Sign in with your work account and tell us which VPN client your device uses, so we can finish the update.", "Confirm device"),
    "press_request": ("Sign in to keep reading", "This article is for registered readers. Sign in with your work account to read the full piece.", "Continue reading"),
    "speaker_invite": ("Speaker RSVP", "Thank you for your interest. Tell us when you are available and we will send the full programme.", "Send RSVP"),
    "recruiting": ("Candidate profile", "Sign in with your work account to view the candidate profile and CV.", "View profile"),
    "investor_intro": ("Data room", "Sign in with your work account to view our thesis, portfolio and the introduction deck.", "Enter data room"),
    "meeting_reschedule": ("Confirm the new time", "Sign in to confirm the updated meeting details.", "Confirm"),
}
_PAGE_COPY_DE = {
    "security_alert": ("Anmeldung bestätigen", "Melden Sie sich an, um die Aktivität zu prüfen und Ihr Konto zu schützen.", "Weiter"),
    "vendor_notice": ("Konto ansehen", "Melden Sie sich an, um Ihre Kontoinformationen aufzurufen.", "Anmelden"),
    "document_share": ("Ein Dokument wurde geteilt", "Melden Sie sich mit Ihrem Arbeitskonto an, um das Dokument zu öffnen.", "Dokument öffnen"),
    "invoice_approval": ("Rechnung 2026-1184 bestätigen", "Bestätigen Sie die Rechnung und nennen Sie uns die zuständige Ansprechperson.", "Rechnung bestätigen"),
    "hr_policy": ("Aktualisierte Richtlinie bestätigen", "Melden Sie sich an, um die aktualisierte Richtlinie zu lesen und zu bestätigen.", "Anmelden"),
    "it_helpdesk": ("Gerät bestätigen", "Melden Sie sich mit Ihrem Arbeitskonto an und geben Sie den VPN-Client Ihres Geräts an.", "Gerät bestätigen"),
    "press_request": ("Zum Artikel anmelden", "Dieser Artikel ist für registrierte Leserinnen und Leser. Melden Sie sich an, um weiterzulesen.", "Weiterlesen"),
    "speaker_invite": ("Rückmeldung zur Einladung", "Vielen Dank für Ihr Interesse. Teilen Sie uns mit, wann Sie verfügbar sind.", "Rückmeldung senden"),
    "recruiting": ("Kandidatenprofil", "Melden Sie sich an, um das Kandidatenprofil und den Lebenslauf aufzurufen.", "Profil ansehen"),
    "investor_intro": ("Datenraum", "Melden Sie sich an, um die Unterlagen und das Intro-Deck aufzurufen.", "Zum Datenraum"),
    "meeting_reschedule": ("Neuen Termin bestätigen", "Melden Sie sich an, um die aktualisierten Termindetails zu bestätigen.", "Bestätigen"),
}
_PAGE_UI = {
    "security_alert": ("ACCOUNT ACCESS", "Account security", "Sign-in details", "Account help", "Use the account associated with this service."),
    "vendor_notice": ("SERVICE ACCOUNT", "Account", "Account details", "Account help", "Use the account associated with this service."),
    "document_share": ("SHARED DOCUMENT", "Shared files", "Sign-in details", "Document access", "Use your work account to open the shared file."),
    "invoice_approval": ("INVOICE REVIEW", "Invoices", "Approval contact", "Invoice details", "Confirm which person handles invoice approvals for your organisation."),
    "hr_policy": ("PEOPLE PORTAL", "People", "Sign-in details", "Policy acknowledgement", "Review the policy and record your acknowledgement."),
    "it_helpdesk": ("DEVICE CHECK", "IT services", "Device details", "Service desk", "Enter the details requested for this device check."),
    "press_request": ("READER ACCESS", "Articles", "Reader sign-in", "Member access", "Sign in with your reader account for this publication."),
    "speaker_invite": ("EVENT RSVP", "Events", "Your response", "About your response", "Share your availability so the events team can follow up."),
    "recruiting": ("CANDIDATE PORTAL", "Candidates", "Candidate sign-in", "Candidate profile", "Use your account to view the candidate material."),
    "investor_intro": ("INVESTOR DATA ROOM", "Data room", "Account sign-in", "Shared materials", "Sign in to view the shared materials."),
    "meeting_reschedule": ("CALENDAR UPDATE", "Calendar", "Meeting details", "Updated meeting", "Review the details before confirming the change."),
}
_PAGE_UI_DE = {
    "security_alert": ("KONTOZUGANG", "Kontosicherheit", "Anmeldedaten", "Kontohilfe", "Verwenden Sie das Konto, das mit diesem Dienst verknüpft ist."),
    "vendor_notice": ("SERVICEKONTO", "Konto", "Kontodaten", "Kontohilfe", "Verwenden Sie das Konto, das mit diesem Dienst verknüpft ist."),
    "document_share": ("GETEILTES DOKUMENT", "Geteilte Dateien", "Anmeldedaten", "Dokumentzugriff", "Verwenden Sie Ihr Arbeitskonto, um die geteilte Datei zu öffnen."),
    "invoice_approval": ("RECHNUNGSPRÜFUNG", "Rechnungen", "Zuständige Ansprechperson", "Rechnungsdetails", "Geben Sie an, wer bei Ihnen für Rechnungsfreigaben zuständig ist."),
    "hr_policy": ("PERSONALPORTAL", "Personal", "Anmeldedaten", "Richtlinienbestätigung", "Lesen Sie die Richtlinie und bestätigen Sie Ihre Kenntnisnahme."),
    "it_helpdesk": ("GERÄTEPRÜFUNG", "IT-Service", "Gerätedaten", "Service Desk", "Geben Sie die für diese Geräteprüfung angefragten Informationen ein."),
    "press_request": ("LESERZUGANG", "Artikel", "Leser-Anmeldung", "Mitgliederzugang", "Melden Sie sich mit Ihrem Konto für diese Publikation an."),
    "speaker_invite": ("EVENT-RÜCKMELDUNG", "Veranstaltungen", "Ihre Rückmeldung", "Zu Ihrer Rückmeldung", "Teilen Sie Ihre Verfügbarkeit, damit sich das Event-Team bei Ihnen melden kann."),
    "recruiting": ("BEWERBUNGSPORTAL", "Bewerbungen", "Kandidaten-Anmeldung", "Kandidatenprofil", "Melden Sie sich an, um die Bewerbungsunterlagen aufzurufen."),
    "investor_intro": ("INVESTOREN-DATENRAUM", "Datenraum", "Konto-Anmeldung", "Geteilte Unterlagen", "Melden Sie sich an, um die geteilten Unterlagen aufzurufen."),
    "meeting_reschedule": ("KALENDER-UPDATE", "Kalender", "Termindetails", "Aktualisierter Termin", "Prüfen Sie die Angaben, bevor Sie die Änderung bestätigen."),
}
_FIELD_LABELS_DE = {
    "email": "Geschäftliche E-Mail-Adresse", "password": "Passwort", "name": "Vollständiger Name",
    "availability": "Ihre Verfügbarkeit", "username": "Benutzername", "phone": "Telefonnummer",
    "company": "Unternehmen", "job_title": "Position",
    "internal_tool": "Welche Tools möchten Sie im Gespräch thematisieren?",
    "approver": "Wer ist bei Ihnen für diese Rechnung zuständig?", "vpn_client": "VPN-Client auf diesem Gerät",
}


# Real brands we impersonate (VENDOR_LOOKALIKES): their logo file in assets/logos/, brand colour,
# and whether the logo is an icon only (then the name is written next to it).
BRAND_STYLE = {
    "Google Workspace": ("google-workspace.png", "#1a73e8", False), "Microsoft 365": ("microsoft.png", "#0067b8", True),
    "Okta": ("okta.png", "#191919", False), "Dropbox": ("dropbox.png", "#0061fe", False),
    "DocuSign": ("docusign.png", "#4c00ff", False), "Workday": ("workday.png", "#005cb9", False),
    "GitHub": ("github.png", "#24292f", True), "AWS": ("aws.png", "#232f3e", False),
    "Salesforce": ("salesforce.png", "#0176d3", False), "SAP": ("sap.png", "#0070f2", False),
    "HubSpot": ("hubspot.png", "#ff5c35", False), "SendGrid": ("sendgrid.png", "#1a82e2", False),
    "Slack": ("slack.png", "#4a154b", False),
}
LOGO_DIR = __import__("pathlib").Path(__file__).with_name("assets") / "logos"


def brand_of(organization: str) -> str | None:
    """The real brand an organisation name stands for ('Google Workspace Security' -> 'Google
    Workspace', 'HubSpot Support' -> 'HubSpot'), or None for an invented organisation."""
    org = f" {str(organization).casefold()} "
    for v in VENDOR_LOOKALIKES:
        if re.search(rf"\b{re.escape(v['brand'].casefold())}\b", org) or any(re.search(rf"\b{re.escape(m)}\b", org) for m in v["match"] if len(m) > 3):
            return v["brand"] if v["brand"] in BRAND_STYLE else None
    return None


def _brand_colour(org: str) -> str:
    brand = brand_of(org)
    if brand:
        return BRAND_STYLE[brand][1]
    return _BRAND_COLOURS[sum(map(ord, org)) % len(_BRAND_COLOURS)]


def _logo(org: str, logo_src: str, size: int) -> str:
    """The real logo (an uploaded asset) for a known brand; the name beside it if the logo is an icon."""
    brand = brand_of(org)
    icon_only = BRAND_STYLE[brand][2] if brand else True
    img = f'<img src="{html.escape(logo_src, quote=True)}" alt="{html.escape(brand or org)}" style="height:{size + 12}px;display:block">'
    if not icon_only:
        return img
    return (f'<div style="display:flex;align-items:center;gap:10px">{img}'
            f'<div style="font-weight:600;font-size:{size}px;color:#111827">{html.escape(org)}</div></div>')


def _wordmark(org: str, colour: str, size: int = 20, logo_src: str = "") -> str:
    if logo_src:
        return _logo(org, logo_src, size)
    initial = html.escape((org.strip() or "?")[0].upper())
    return (f'<div style="display:flex;align-items:center;gap:10px">'
            f'<div style="width:{size + 12}px;height:{size + 12}px;border-radius:8px;background:{colour};color:#fff;'
            f'font-weight:700;font-size:{size - 2}px;display:flex;align-items:center;justify-content:center">{initial}</div>'
            f'<div style="font-weight:600;font-size:{size}px;color:#111827">{html.escape(org)}</div></div>')


def render_landing_html(*, pretext: str, organization: str, title: str, fields: list[str],
                        logo_src: str = "", german: bool = False) -> tuple[str, str]:
    """A self-contained page for this sender and occasion. Returns (html, visible text)."""
    org = organization.strip() or "Account services"
    colour = _brand_colour(org)
    copy = _PAGE_COPY_DE if german else _PAGE_COPY
    ui_copy = _PAGE_UI_DE if german else _PAGE_UI
    fallback_text = "Bitte füllen Sie das folgende Formular aus." if german else "Please fill in the form below."
    fallback_button = "Weiter" if german else "Continue"
    heading, text, button = copy.get(pretext, (title, fallback_text, fallback_button))
    brand = brand_of(org)
    tab_title = BRAND_TAB_TITLES.get(brand) if brand and "password" in fields else None
    tab_title = (f"{heading} – {org}" if german else f"{title} – {org}") if not tab_title or german else tab_title
    labels = ["Datenschutz", "Nutzungsbedingungen", "Hilfe", "Impressum"] if german else ["Privacy", "Terms", "Help"]
    footer_links = " <span aria-hidden=\"true\">·</span> ".join(html.escape(x) for x in labels)
    field_labels = _FIELD_LABELS_DE if german else _FIELD_LABELS
    autocomplete = {"email": "username", "password": "current-password", "name": "name", "phone": "tel"}
    inputs = "".join(
        f'<label class="field"><span>{html.escape(field_labels.get(f, f.replace("_", " ").capitalize()))}</span>'
        f'<input name="{html.escape(f, quote=True)}" type="{"password" if f == "password" else "email" if f == "email" else "tel" if f == "phone" else "text"}" '
        f'autocomplete="{autocomplete.get(f, "off")}" aria-label="{html.escape(field_labels.get(f, f.replace("_", " ").capitalize()), quote=True)}"></label>'
        for f in fields[:20])
    year = date.today().year
    locale = "de" if german else "en"
    home = "Startseite" if german else "Home"
    ui = ui_copy.get(pretext)
    if ui:
        browser_label, section, form_heading, help_label, help_text = ui
    else:
        browser_label = "SERVICE-ZUGANG" if german else "SERVICE ACCESS"
        section = "Konto" if german else "Account"
        form_heading = section
        help_label = "Hilfe" if german else "Help"
        help_text = ("Bei Fragen wenden Sie sich bitte an Ihre Ansprechperson." if german
                     else "If you have questions, contact your usual point of contact.")
    header_note = "Serviceportal" if german else "Service centre"
    note = "Ihre Angaben werden für diese Anfrage verwendet." if german else "Your details are used for this request."
    page = (
        f'<!doctype html><html lang="{locale}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="{colour}">'
        f'<title>{html.escape(tab_title)}</title><style>'
        f':root{{--brand:{colour};--ink:#17212f;--muted:#647184;--line:#e3e8ef;--surface:#fff;--canvas:#f5f7fa}}'
        '*{box-sizing:border-box}html,body{min-height:100%;margin:0}body{background:var(--canvas);color:var(--ink);'
        'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}'
        '.site-header{background:#fff;border-bottom:1px solid var(--line)}'
        '.header-inner{max-width:1120px;margin:auto;padding:20px 32px;display:flex;align-items:center;justify-content:space-between;gap:20px}'
        '.header-note,.crumbs,.footer{font-size:13px;color:var(--muted)}.header-note{display:flex;align-items:center;gap:9px}'
        '.dot{width:8px;height:8px;border-radius:50%;background:#24a06b;display:inline-block}'
        '.page{max-width:1120px;margin:0 auto;padding:34px 32px 52px}.crumbs{display:flex;gap:9px;margin:0 0 24px}'
        '.crumb-sep{color:#a0aaba}.content{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:22px;align-items:stretch}'
        '.card,.aside{background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 26px rgba(24,39,60,.045)}'
        '.card{max-width:720px;width:100%;padding:38px 42px}.eyebrow{color:var(--brand);font-size:12px;line-height:1.4;font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin:0 0 12px}'
        'h1{font-size:28px;line-height:1.25;letter-spacing:-.025em;margin:0 0 11px;font-weight:650}.intro{font-size:15px;line-height:1.65;color:#556275;margin:0;max-width:590px}'
        '.form-heading{font-size:14px;font-weight:650;margin:28px 0 0}.field{display:block;margin-top:17px;font-size:13px;font-weight:600;color:#344154}'
        '.field input{display:block;width:100%;height:46px;margin-top:7px;padding:0 13px;border:1px solid #cbd3de;border-radius:7px;background:#fff;color:var(--ink);font-size:15px;font-family:inherit;outline:none;transition:border-color .15s,box-shadow .15s}'
        '.field input:focus{border-color:var(--brand);box-shadow:0 0 0 3px rgba(23,33,47,.10)}'
        '.submit{width:100%;height:47px;margin-top:25px;border:0;border-radius:7px;background:var(--brand);color:#fff;font-size:15px;font-weight:600;font-family:inherit;cursor:pointer}'
        '.submit:hover{filter:brightness(.95)}.form-note{display:flex;gap:9px;align-items:flex-start;margin:17px 0 0;color:var(--muted);font-size:12px;line-height:1.5}'
        '.lock{width:11px;height:8px;margin:5px 2px 0;border:1.5px solid var(--brand);border-radius:2px;position:relative;flex:none}'
        '.lock:before{content:"";position:absolute;width:5px;height:5px;left:1.5px;top:-6px;border:1.5px solid var(--brand);border-bottom:0;border-radius:4px 4px 0 0}'
        '.aside{align-self:start;padding:27px 25px;display:flex;flex-direction:column;justify-content:center;min-height:0}'
        '.aside-icon{width:40px;height:40px;border-radius:11px;background:#eef3fa;color:var(--brand);display:grid;place-items:center;font-size:18px;font-weight:700;margin-bottom:18px}'
        '.aside h2{font-size:16px;margin:0 0 8px}.aside p{font-size:13px;line-height:1.6;color:var(--muted);margin:0}'
        '.footer{max-width:1120px;margin:0 auto;padding:0 32px 26px;display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}'
        '.footer-links{display:flex;gap:8px;flex-wrap:wrap}'
        '@media(max-width:760px){.header-inner{padding:17px 20px}.page{padding:25px 20px 36px}.content{grid-template-columns:1fr}.card{max-width:none;padding:30px 25px}.aside{min-height:0;padding:22px}.footer{padding:0 20px 24px}h1{font-size:25px}}'
        '@media(max-width:420px){.header-note{font-size:12px}.header-inner{gap:12px}.card{padding:26px 20px}.footer{font-size:12px}}'
        '</style></head><body>'
        f'<header class="site-header"><div class="header-inner">{_wordmark(org, colour, logo_src=logo_src)}'
        f'<div class="header-note"><span class="dot" aria-hidden="true"></span>{header_note}</div></div></header>'
        f'<main class="page"><nav class="crumbs" aria-label="Breadcrumb"><span>{home}</span><span class="crumb-sep">/</span><span>{section}</span></nav>'
        f'<div class="content"><section class="card"><p class="eyebrow">{browser_label}</p>'
        f'<h1>{html.escape(heading)}</h1><p class="intro">{html.escape(text)}</p>'
        f'<form autocomplete="on"><p class="form-heading">{form_heading}</p>{inputs}'
        f'<button class="submit" type="submit">{html.escape(button)}</button>'
        f'<p class="form-note"><span class="lock" aria-hidden="true"></span><span>{note}</span></p></form></section>'
        f'<aside class="aside"><div class="aside-icon" aria-hidden="true">?</div><h2>{help_label}</h2><p>{help_text}</p></aside></div></main>'
        f'<footer class="footer"><span>© {year} {html.escape(org)}</span><span class="footer-links">{footer_links}</span></footer>'
        f'</body></html>')
    return page, f"{heading}. {text}"


def render_mail_html(*, body: str, organization: str, link: dict[str, str] | None = None, logo_src: str = "") -> str:
    """A vendor or IT notice as such senders send it: brand header, short text, one button whose
    address is also printed, and a footer. Plain text stays right for people writing as themselves."""
    org = organization.strip() or "Account services"
    colour = _brand_colour(org)
    font = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    blocks = [p for p in str(body).strip().split("\n\n") if p.strip()]
    # the button belongs above the sign-off ("Best,\nAccount Security"), as real notices put it
    sign_off = blocks.pop() if len(blocks) > 1 and len(blocks[-1].split()) <= 8 else ""
    para = lambda t: f'<p style="margin:0 0 14px;font-size:15px;line-height:1.55">{html.escape(t).replace(chr(10), "<br>")}</p>'
    paras = "".join(para(t) for t in blocks)
    cta = ""
    if link and link.get("url"):
        url = html.escape(link["url"], quote=True)
        cta = (f'<p style="margin:22px 0 8px"><a href="{url}" style="display:inline-block;background:{colour};color:#fff;'
               f'text-decoration:none;padding:11px 22px;border-radius:6px;font-weight:600;font-size:15px">'
               f'{html.escape(link.get("title") or "Continue")}</a></p>'
               f'<p style="margin:0 0 14px;font-size:12px;color:#6b7280">Or open this link: <a href="{url}" style="color:{colour}">{url}</a></p>')
    year = date.today().year
    return (f'<div style="background:#f3f4f6;padding:24px 0;font-family:{font};color:#111827">'
            f'<div style="max-width:600px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:10px">'
            f'<div style="padding:20px 28px;border-bottom:3px solid {colour}">{_wordmark(org, colour, 17, logo_src=logo_src)}</div>'
            f'<div style="padding:24px 28px">{paras}{cta}{para(sign_off) if sign_off else ""}</div></div>'
            f'<p style="max-width:600px;margin:14px auto 0;font-size:11px;line-height:1.5;color:#6b7280;text-align:center">'
            f'You are receiving this service message because of your {html.escape(org)} account. '
            f'© {year} {html.escape(org)}. All rights reserved.</p></div>')


# The address bar is part of the craft rating: a real sign-in sits on accounts.<brand>/…?continue=…,
# a shared file on docs.<brand>/…?usp=sharing. The subdomain is ours, on our registrable domain.
PAGE_HOST = {
    "security_alert": ("accounts", "?continue=mail&hl=en"), "document_share": ("docs", "?usp=sharing"),
    "vendor_notice": ("billing", "?ref=renewal"), "speaker_invite": ("events", "?ref=speaker-invite"),
    "press_request": ("www", "?utm_source=linkedin"), "recruiting": ("portal", "?ref=candidate"),
    "investor_intro": ("", "?ref=intro"), "meeting_reschedule": ("calendar", "?view=event"),
    "invoice_approval": ("", "?ref=email"), "hr_policy": ("hr", "?doc=policy-2026"),
    "it_helpdesk": ("servicedesk", "?ticket=INC-48213"),
}
# what the browser tab says for a known brand's sign-in page
BRAND_TAB_TITLES = {"Google Workspace": "Sign in – Google Accounts", "Microsoft 365": "Sign in to your account",
                    "Okta": "Okta – Sign In", "Dropbox": "Dropbox – Sign in", "Slack": "Sign in | Slack",
                    "GitHub": "Sign in to GitHub · GitHub", "Salesforce": "Login | Salesforce",
                    "DocuSign": "DocuSign", "HubSpot": "HubSpot Login", "Workday": "Workday"}


def build_landing(pretext: str, target_domain: str, vendors: list[str] | None = None) -> dict[str, Any] | None:
    """Landing-page URL + fields for a pretext, on a technique-appropriate domain.

    If the target uses a matching tool, the page sits on that tool's lookalike domain.
    """
    brand, tld = _brand_tld(target_domain)
    page = (SENDERS.get("pretexts", {}).get(pretext) or {}).get("page")
    if not page:
        return None
    domain = _fill(page["domain"], brand, tld)
    vendor = detect_vendor(pretext, vendors or [])
    if vendor:
        domain = vendor["domain"]
    domain = free_domain(domain)
    sub, query = PAGE_HOST.get(pretext, ("", ""))
    host = f"{sub}.{domain}" if sub else domain
    return {
        "url": f"https://{host}{page.get('path', '/')}{query}",
        "title": page.get("title", "Details"),
        "fields": page.get("fields", []),
        "domain": domain,
        "sub": sub,
    }


def suggest_sender_domains(
    brand: str,
    *,
    suffixes: tuple[str, ...] = ("events", "community", "connect"),
    tlds: tuple[str, ...] = ("de", "com"),
) -> list[dict[str, Any]]:
    """Suggest neutral, syntactically registrable candidates; availability must be checked.

    This deliberately avoids typo-squats and never claims a candidate is
    registered or available.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", brand.casefold()).strip("-")[:35] or "sender"
    return [
        {"candidate": f"{slug}-{suffix}.{tld}", "registration_verified": False}
        for suffix in suffixes
        for tld in tlds
        if re.fullmatch(r"[a-z]{2,24}", tld)
    ]


def _first_colleague(profile: dict[str, Any]) -> str:
    """A named coworker from recon's network facts, never the target themself
    ("Julius Muth's co-founder is Tom Müller" -> "Tom Müller" for Julius)."""
    own = str(profile.get("name", "")).casefold()
    for f in profile.get("facts", []):
        if isinstance(f, dict) and f.get("category") == "network":
            for m in re.finditer(r"\b([A-ZÄÖÜ][a-zäöüß]+) ([A-ZÄÖÜ][a-zäöüß]+)\b", str(f.get("value", ""))):
                if m.group(0).casefold() != own and m.group(1).casefold() not in own.split():
                    return m.group(0)
    return ""


# Natural subject and opening per pretext for compose(), the no-model fallback. Never the internal
# story text: that read "Question about a known vendor or tool" and got ignored by the twins.
FALLBACK_COPY = {
    "speaker_invite": ("Speaking invitation: security awareness panel",
                       "We're putting together a short panel on how fast-growing teams handle security awareness, and your name came up. Would you be open to joining us? The outline and dates are below."),
    "press_request": ("Interview request",
                      "I'm writing a feature on how growing companies keep their teams secure and would love 20 minutes with you next week. Would that work?"),
    "customer_question": ("Question before we sign up",
                          "We're evaluating {company} for our team of about 40 and have one question before we move forward: how does onboarding usually work?"),
    "recruiting": ("Candidate for your open role",
                   "I'm working with a strong candidate who could be a great fit for your team. Their CV is attached; happy to set up an introduction if it looks interesting."),
    "document_share": ("Updated document for your review",
                       "I've shared the latest version of the document with you. Could you take a look before we next speak?"),
    "meeting_reschedule": ("Small change to our meeting",
                           "Something came up on my side. Could we move our meeting to Thursday at 10:00? The updated details are below."),
    "vendor_notice": ("Your {vendor} renewal for {company}",
                      "Your {vendor} subscription for {company} is due for renewal at the end of the month. Please review the renewal details below so nothing is interrupted."),
    "security_alert": ("New sign-in to your {vendor} account",
                       "We noticed a new sign-in to your {vendor} account from an unrecognised device. If this wasn't you, please review your recent activity below."),
    "internal_favor": ("Quick favour",
                       "Do you have a minute today? I need a quick hand with something before a deadline; details below."),
    "invoice_approval": ("Invoice 2026-1184 for {company}",
                         "Please find our invoice attached. Could you confirm who approves it on your side so it reaches the right person before the payment run?"),
    "hr_policy": ("Updated policy: please acknowledge",
                  "We've updated a company policy that applies to everyone. Please read it and confirm in the HR portal below."),
    "it_helpdesk": ("Your IT ticket: device update",
                    "We're following up on the device and VPN update for your account. Please confirm your device below so we can close the ticket."),
    "exec_request": ("Quick favour",
                     "Are you at your desk? I need a quick hand with something discreet before my next meeting."),
    "investor_intro": ("Introduction",
                       "I'd like to introduce you to a partner at a fund that has been following {company} closely. Would you be open to a short call next week?"),
}


def _fallback_copy(pretext: str, *, company: str, vendor: str) -> tuple[str, str]:
    subject, opening = FALLBACK_COPY.get(pretext, ("Quick question", "I hope you don't mind me reaching out directly. Do you have a moment this week?"))
    fill = {"company": company, "vendor": vendor or "workspace"}
    return subject.format(**fill), opening.format(**fill)


def compose(profile: dict[str, Any], approach: dict[str, Any]) -> dict[str, Any]:
    """Build a ready-to-send message for an approach WITHOUT calling the model.

    Deterministic, dependency-light, always returns output — the easy entry point
    for the backend to wire up and smoke-test. For a model-written body instead,
    call ``generate_message`` with a ``ModelConfig``. Returns a dict the revel8
    client can send: ``{channel, to, sender, subject, body, landing_page, attachment}``.
    """
    pretext = str(approach.get("pretext") or approach.get("key") or approach.get("id") or "")
    channel = str(approach.get("channel") or (approach.get("channels") or ["email"])[0])
    domain = str(profile.get("domain", ""))
    vendors = _tool_vectors(profile)
    first = str(profile.get("name", "")).split()[0] if profile.get("name") else ""
    sender = build_sender(pretext, domain, colleague=_first_colleague(profile), vendors=vendors, avoid_first_name=first)
    landing = build_landing(pretext, domain, vendors=vendors)
    first_name = str(profile.get("name", "there")).split()[0]
    vendor = detect_vendor(pretext, vendors)   # a real tool name ("Google Workspace"), never the raw fact sentence
    subject, opening = _fallback_copy(pretext, company=str(profile.get("company") or "your team"),
                                      vendor=vendor["brand"] if vendor else "")
    body = f"Hi {first_name},\n\n{opening}"
    if landing:
        body += f"\n\n{landing['title']}: {landing['url']}"
    body += f"\n\nBest,\n{sender['name']}"
    if sender.get("role"):
        body += f"\n{sender['role']}"
    return {
        "channel": channel,
        "to": profile.get("target_id") or (profile.get("name", "").split()[0].lower() if profile.get("name") else ""),
        "sender": {"name": sender["name"], "address": sender["address"]},
        "sender_technique": sender["technique"],
        "subject": subject if channel in ("email", "calendar_invite", "shared_document") else "",
        "body": body,
        "landing_page": landing,
        # the recipient sees this name, so it must read like a real file, never an internal label
        "attachment": approach.get("attachment") or {"recruiting": "Candidate_Profile.pdf", "document_share": "Q1_Planning_Update.pdf",
                                                     "invoice_approval": "Invoice_2026-1184.pdf"}.get(pretext),
    }


if __name__ == "__main__":  # python writer.py  -> sample output for backend wiring
    import json
    import pathlib

    sample = pathlib.Path(__file__).with_name("mock") / "profile.json"
    if sample.exists():
        profile = json.loads(sample.read_text(encoding="utf-8"))
    else:
        profile = {"name": "Julius Muth", "domain": "revel8.ai",
                   "facts": [{"category": "network", "value": "Co-founders Tom Mueller and Robert Seilbeck"},
                             {"category": "vendors_and_tools", "value": "Company uses DocuSign and Okta SSO"}]}
    print(f"# writer.compose() output for {profile.get('name')} ({profile.get('domain')})\n")
    for pretext in ("speaker_invite", "security_alert", "document_share", "vendor_notice", "recruiting"):
        msg = compose(profile, {"pretext": pretext, "channel": "email", "story": f"an {pretext.replace('_', ' ')}"})
        print(json.dumps(msg, indent=2, ensure_ascii=False))
        print()
