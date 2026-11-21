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
    "Write as the person in you_are, in their organisation's normal tone for this channel.",
    "Address the recipient by first name. Never greet the sender.",
    "Be specific: name a concrete product, plan, event, date, document or person. Use facts about the recipient only from verified_facts_about_recipient.",
    "Never use the wording of internal_plan_do_not_quote, and never write words like pretext, hook, target, 'known vendor' or 'known tool'.",
    "The subject must read like a real subject line from this sender, not a description of the message.",
    "Make exactly one clear ask that serves the plan. Mention a file or a link only if included_with_your_text has it; otherwise ask for a reply with one specific detail.",
    "Do not name other people or companies the recipient could look up and find missing; describe them in general terms (for example 'two founders from the Munich security scene').",
    "In a follow-up, refer to your earlier message and add one new reason or detail; never repeat it.",
    "Sign off with a full plausible name, role and organisation; a company sender adds a one-line footer.",
    "Any date you mention lies after today. Plain text, under 130 words, no markdown, no placeholders.",
    "Reply with the JSON object only.",
]


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
    facts = [
        {"category": f.get("category"), "value": f.get("value"), "source_url": f.get("source_url")}
        for f in verified_facts
        if f.get("verified") is True and f.get("source_url") and f.get("value")
    ]
    payload = {
        "task": CHANNEL_GUIDANCE.get(channel, "Write only the caller's next spoken line for a live call."),
        "recipient": {key: target.get(key) for key in ("name", "role", "company") if target.get(key)},
        "you_are": {key: sender.get(key) for key in ("name", "role", "organization", "email") if sender.get(key)},
        # the agent's own plan: guides the message, but its wording must never appear in it
        "internal_plan_do_not_quote": {key: approach.get(key) for key in ("hook", "pretext", "story", "incident_goal") if approach.get(key)},
        "verified_facts_about_recipient": facts,
        "conversation_history": conversation_history or [],
        "today": date.today().isoformat(),   # so dates and years in the message are plausible
        "included_with_your_text": {"attachment": attachment, "link_added_below_your_text": bool(link_follows)},
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
    facts = [
        {"category": f.get("category"), "value": f.get("value"), "source_url": f.get("source_url")}
        for f in verified_facts
        if f.get("verified") is True and f.get("source_url") and f.get("value")
    ]
    user_payload = {
        "instruction": "Write only the caller's next spoken line as JSON {\"body\": \"...\"}. Keep the sender persona and established details consistent. Answer the other party's last question briefly, then make at most one clear ask.",
        "target": {key: target.get(key) for key in ("name", "role", "company") if target.get(key)},
        "sender": {key: sender.get(key) for key in ("name", "role", "organization") if sender.get(key)},
        "approach": {key: approach.get(key) for key in ("hook", "pretext", "story", "incident_goal") if approach.get(key)},
        "verified_facts": facts,
        "transcript": transcript,
        "turn": turn_number,
        "max_turns": max_turns,
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
    "speaker_invite", "press_request", "customer_question", "document_share", "meeting_reschedule",
    "vendor_notice", "security_alert", "internal_favor", "investor_intro",
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
    slug = re.sub(r"[^a-z0-9]+", ".", str(name).lower()).strip(".")
    return slug or "contact"


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
    return {
        "name": name,
        "address": f"{_local_part(name)}@{domain}",
        "domain": domain,
        "technique": technique,
        "role": entry.get("role", ""),
    }


# Pretexts whose sender is an invented outsider: their identity is generated to fit the hook.
# Vendor and security notices impersonate a tool, colleague pretexts use the colleague's name.
GENERATED_SENDER_PRETEXTS = {"speaker_invite", "press_request", "recruiting", "customer_question", "investor_intro"}
REAL_ORG_DOMAINS = ("google.com", "microsoft.com", "linkedin.com", "docusign.com", "okta.com", "apple.com",
                    "amazon.com", "slack.com", "zoom.us", "github.com", "salesforce.com", "hubspot.com")


def generate_sender_persona(config: "ModelConfig", *, target: dict[str, Any], approach: dict[str, Any],
                            facts: list[dict[str, Any]], default: dict[str, Any]) -> dict[str, Any]:
    """Invent who sends this message so the identity fits the story: an organisation that
    would naturally write about this hook, a role that fits the question, a name from the
    recipient's region (never their own first name) and a matching registrable domain.
    Returns {name, role, organization, domain, address}; raises if no valid persona."""
    recipient_first = str(target.get("name", "")).split()[0].casefold() if target.get("name") else ""
    own = str(target.get("company_domain", "")).lower()
    payload = {
        "task": "Invent the sender of a first message for this plan. Return JSON only.",
        "recipient": {k: target.get(k) for k in ("name", "role", "company") if target.get(k)},
        "internal_plan_do_not_quote": {k: approach.get(k) for k in ("hook", "pretext", "story") if approach.get(k)},
        "facts_about_recipient": [f.get("value") for f in facts if f.get("value")][:12],
        "rules": [
            "The organisation is invented and would naturally send this message about this topic (e.g. a monitoring vendor for a cloud-cost topic, an executive search firm for a hiring topic, an events agency for a speaking invitation).",
            "The role fits the question being asked (an engineer for technical questions, a partner for investors, a researcher or editor for press).",
            "A realistic full name from the recipient's region; the first name must differ from the recipient's first name.",
            "The domain is a plausible, registrable domain for that invented organisation: never a real company's domain and never the recipient's.",
        ],
        "example_default_sender": {k: default.get(k) for k in ("name", "role", "domain") if default.get(k)},
        "output_schema": {"name": "First Last", "role": "string", "organization": "string", "domain": "example-org.de"},
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
        name, domain = str(out.get("name", "")).strip(), str(out.get("domain", "")).strip().lower().removeprefix("www.")
        first = name.split()[0].casefold() if name.split() else ""
        if (len(name.split()) < 2 or first == recipient_first or not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", domain)
                or (own and (domain == own or domain.endswith("." + own)))
                or any(domain == d or domain.endswith("." + d) for d in REAL_ORG_DOMAINS) or not out.get("organization")):
            problems.append(f"{model}: invalid persona {out}")
            continue
        return {"name": name, "role": str(out.get("role", "")).strip(), "organization": str(out["organization"]).strip(),
                "domain": domain, "address": f"{_local_part(name)}@{domain}"}
    raise RuntimeError("no valid sender persona: " + "; ".join(problems))


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
    return {
        "url": f"https://{domain}{page.get('path', '/')}",
        "title": page.get("title", "Details"),
        "fields": page.get("fields", []),
        "domain": domain,
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
    for f in profile.get("facts", []):
        if isinstance(f, dict) and f.get("category") == "network":
            m = re.search(r"[A-Z][a-z]+ [A-Z][a-z]+", str(f.get("value", "")))
            if m:
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
        "attachment": {"recruiting": "Candidate_Profile.pdf", "document_share": "Q1_Planning_Update.pdf"}.get(pretext),
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
