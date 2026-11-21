"""Evidence-led strategy and reaction evaluation for the revel8 agent.

Two jobs:

1. ``propose_hooks`` infers *which topics a target is open to* from their recon
   facts, using a generic signal catalogue (``signals.json``). No pretext is
   favoured a priori: susceptibility is derived per target from the signals that
   fact set carries, so it generalises to any new target rather than overfitting
   to the practice founders. Observed reactions (logged elsewhere) then re-rank.

2. ``rank_approaches`` pairs hooks with pretexts/channels and scores them,
   recording rejected options so the search-tree logger can explain choices.

Consumes the ``schemas.py`` ``Profile`` shape as plain dicts (``to_dict`` /
``mock/profile.json``), so it needs no import of the dataclasses and stays
drop-in for the orchestrator and the frontend.
"""

from __future__ import annotations

import json
import math
import pathlib
import re
from dataclasses import dataclass
from typing import Any

_SIGNALS_PATH = pathlib.Path(__file__).with_name("signals.json")


def _load_signals(path: pathlib.Path = _SIGNALS_PATH) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"lambda": 1.1, "min_probability": 0.12, "families": []}


SIGNALS = _load_signals()


@dataclass(frozen=True)
class Pretext:
    key: str
    story: str
    required_facts: tuple[str, ...]  # canonical schemas.FACT_CATEGORIES
    channels: tuple[str, ...]
    incident_goal: str


# required_facts use the canonical categories from schemas.FACT_CATEGORIES so
# coverage is checked against real profiles.
PRETEXTS: tuple[Pretext, ...] = (
    Pretext("speaker_invite", "Invitation to speak or join a panel", ("interests", "upcoming_events"), ("email", "linkedin_message", "calendar_invite", "phone_call"), "get a clear expression of interest or availability"),
    Pretext("press_request", "Journalist or host requests an interview", ("media", "recent_activity"), ("email", "linkedin_message", "phone_call"), "get a reply with interview availability"),
    Pretext("customer_question", "Prospective customer asks a product question", ("role", "company"), ("email", "linkedin_message", "teams_chat"), "start a substantive product conversation"),
    Pretext("recruiting", "Candidate asks about a real open role", ("hiring", "role"), ("email", "linkedin_message"), "get a reply about the hiring process"),
    Pretext("document_share", "Known collaborator shares a relevant document", ("network", "recent_activity"), ("email", "shared_document", "teams_chat"), "get the recipient to open a registered simulation page"),
    Pretext("meeting_reschedule", "Known collaborator proposes a meeting change", ("network", "upcoming_events"), ("email", "calendar_invite", "teams_chat"), "get a reply confirming a meeting detail"),
    Pretext("vendor_notice", "Question about a known vendor or tool", ("vendors_and_tools", "role"), ("email", "teams_chat"), "start a conversation about the known tool"),
    Pretext("security_alert", "Account or sign-in notice for a tool they use", ("vendors_and_tools", "role"), ("email", "sms", "teams_chat"), "get the recipient to open a registered sign-in page"),
    Pretext("internal_favor", "Colleague requests a small, plausible work favour", ("network", "communication_style"), ("email", "teams_chat", "slack", "phone_call"), "get a reply or a harmless simulated action"),
    Pretext("investor_intro", "Someone introduces an investor or partner", ("recent_activity", "network"), ("email", "linkedin_message"), "start an investor or partnership thread"),
)

_PRETEXTS_BY_KEY = {p.key: p for p in PRETEXTS}
_CALL_CHANNELS = {"phone_call", "video_call", "teams_call", "live_chat"}

# Fallback playbook for a target whose role we have not determined. These lures
# work on almost anyone regardless of job, so they seed a sensible opening set
# when recon is thin; real hooks override them the moment facts arrive.
GENERAL_HOOKS: tuple[dict[str, Any], ...] = (
    {"topic": "Account or sign-in security notice", "probability": 0.45, "angle": "their_topic", "evidence": [], "rationale": "Everyone has accounts and sign-ins.", "pretext": "security_alert"},
    {"topic": "A shared document to open", "probability": 0.40, "angle": "their_topic", "evidence": [], "rationale": "Anyone in an organisation opens shared files.", "pretext": "document_share"},
    {"topic": "A quick favour from a colleague", "probability": 0.38, "angle": "their_topic", "evidence": [], "rationale": "Helpfulness and deference to authority are near-universal.", "pretext": "internal_favor"},
    {"topic": "A change to a meeting", "probability": 0.30, "angle": "their_topic", "evidence": [], "rationale": "Most people keep a calendar.", "pretext": "meeting_reschedule"},
)


# ---------------------------------------------------------------------------
# fact helpers
# ---------------------------------------------------------------------------

def _facts(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return recon facts plus synthetic facts for the top-level identity fields.

    role/company/domain live on the Profile itself; treat them as verified facts
    so identity-based signals (e.g. a founder is invite-worthy) still fire.
    """
    out = [f for f in profile.get("facts", []) if isinstance(f, dict)]
    present = {f.get("category") for f in out}
    for category in ("role", "company", "domain"):
        value = str(profile.get(category, "")).strip()
        if value and category not in present:
            out.append({"category": category, "value": value, "source_url": profile.get("domain", ""), "verified": True, "confidence": 1.0})
    return out


def _verified_fact_categories(profile: dict[str, Any]) -> set[str]:
    return {
        str(f.get("category", ""))
        for f in _facts(profile)
        if f.get("verified") is True and f.get("source_url")
    }


def _category_credit(profile: dict[str, Any]) -> dict[str, float]:
    """Best evidence credit per fact category: 1.0 verified+sourced, 0.6 sourced.

    Recon facts are usually single-source (unverified), so a verified-only gate
    would throw away almost everything. Partial credit keeps the signal; the
    writer, not the strategist, enforces verified-only in message text.
    """
    credit: dict[str, float] = {}
    for f in _facts(profile):
        if not f.get("source_url"):
            continue
        category = str(f.get("category", ""))
        value = 1.0 if f.get("verified") is True else 0.6
        credit[category] = max(credit.get(category, 0.0), value)
    return credit


def _coverage(credit: dict[str, float], required: tuple[str, ...]) -> float:
    if not required:
        return 1.0
    return sum(credit.get(c, 0.0) for c in required) / len(required)


def _fact_weight(fact: dict[str, Any]) -> float:
    """Verified facts count full; unverified are discounted, scaled by confidence."""
    base = 1.0 if fact.get("verified") is True and fact.get("source_url") else 0.6
    confidence = fact.get("confidence")
    if isinstance(confidence, (int, float)) and confidence > 0:
        base *= min(1.0, 0.4 + float(confidence))  # floor so a low-confidence fact still counts
    return base


# ---------------------------------------------------------------------------
# susceptibility inference: facts -> ranked hook hypotheses
# ---------------------------------------------------------------------------

def propose_hooks(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Infer ranked hook hypotheses from a target's facts, generically.

    Returns Hook-shaped dicts (topic, probability, evidence, rationale, angle)
    plus two extra keys for the strategist: ``pretext`` (the family the hook maps
    to) and ``signals`` (weight contributions, for the tree log). These extras are
    ignored by ``schemas.hook_from_dict`` only if dropped first; they are safe for
    JSON and the frontend.
    """
    facts = _facts(profile)
    lam = float(SIGNALS.get("lambda", 1.1))
    floor = float(SIGNALS.get("min_probability", 0.12))
    hooks: list[dict[str, Any]] = []

    for family in SIGNALS.get("families", []):
        total = 0.0
        evidence: list[str] = []
        contributions: list[dict[str, Any]] = []
        for rule in family.get("signals", []):
            category = rule.get("category")
            keywords = [k.lower() for k in rule.get("any", [])]
            weight = float(rule.get("weight", 0.0))
            for fact in facts:
                if fact.get("category") != category:
                    continue
                value = str(fact.get("value", ""))
                if keywords and not any(k in value.lower() for k in keywords):
                    continue
                contribution = round(weight * _fact_weight(fact), 4)
                total += contribution
                if value and value not in evidence:
                    evidence.append(value)
                contributions.append({"category": category, "value": value, "contribution": contribution})
        if total <= 0:
            continue
        probability = round(1.0 - math.exp(-lam * total), 4)
        if probability < floor:
            continue
        reasons = ", ".join(sorted({c["category"] for c in contributions}))
        hooks.append({
            "topic": family.get("topic", family.get("pretext", "")),
            "probability": probability,
            "evidence": evidence,
            "rationale": f"Signals from {reasons} support a {family.get('pretext','')} angle.",
            "angle": family.get("angle", "their_topic"),
            "pretext": family.get("pretext", ""),
            "signals": contributions,
        })

    hooks.sort(key=lambda h: -h["probability"])
    return hooks


_MATCH_STOP = {"their", "they", "from", "join", "with", "that", "uses", "use", "about", "real", "your", "known", "relevant", "some", "into"}


def _significant_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3 and w not in _MATCH_STOP}


def _family_keywords() -> dict[str, set[str]]:
    # Match on each family's TOPIC phrase + pretext name, not its signal keywords
    # (signal keywords describe writing style and tool names, which mislead topic matching).
    index: dict[str, set[str]] = {}
    for family in SIGNALS.get("families", []):
        pretext = family.get("pretext", "")
        index[pretext] = _significant_words(family.get("topic", "") + " " + pretext.replace("_", " "))
    return index


_FAMILY_KEYWORDS = _family_keywords()


def _match_family(topic: str) -> str:
    """Map a free-text recon hook topic to the family whose topic phrase it overlaps most."""
    words = _significant_words(topic)
    best, best_hits = "", 0
    for pretext, family_words in _FAMILY_KEYWORDS.items():
        hits = len(words & family_words)
        if hits > best_hits:
            best, best_hits = pretext, hits
    return best


def _resolve_hooks(profile: dict[str, Any], hooks: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Merge recon hooks (richer, untagged) into inferred ones (pretext-tagged).

    Inferred hooks give every pretext a signal floor; a recon hook that matches a
    family raises that family's probability and adds its evidence. Recon hooks
    that match no family are kept as generic hypotheses.
    """
    by_pretext = {h["pretext"]: dict(h) for h in propose_hooks(profile)}
    recon = hooks if hooks is not None else profile.get("hooks") or []
    extras: list[dict[str, Any]] = []
    for rh in recon:
        if not isinstance(rh, dict):
            continue
        family = _match_family(str(rh.get("topic", "")))
        prob = float(rh.get("probability", 0.0))
        if not family:
            extras.append({**rh, "pretext": rh.get("pretext", "")})
            continue
        cur = by_pretext.get(family, {"pretext": family, "topic": rh.get("topic", ""), "probability": 0.0, "evidence": [], "angle": rh.get("angle", "their_topic")})
        cur["topic"] = rh.get("topic") or cur.get("topic", "")
        cur["probability"] = max(float(cur.get("probability", 0.0)), prob)
        cur["evidence"] = list(dict.fromkeys([*cur.get("evidence", []), *rh.get("evidence", [])]))
        if rh.get("angle"):
            cur["angle"] = rh["angle"]
        by_pretext[family] = cur
    merged = list(by_pretext.values()) + extras
    if not merged:
        # Unprofiled target: fall back to the role-agnostic general playbook.
        merged = [dict(h) for h in GENERAL_HOOKS]
    merged.sort(key=lambda h: -float(h.get("probability", 0.0)))
    return merged


# ---------------------------------------------------------------------------
# approach ranking: hooks x pretexts x channels
# ---------------------------------------------------------------------------

def rank_approaches(
    profile: dict[str, Any],
    hooks: list[dict[str, Any]] | None = None,
    *,
    excluded_pretexts: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Rank pretext/channel approaches for this target.

    Hooks come from (in order) the caller, the profile's recon hooks, or
    ``propose_hooks`` inferred from facts. Each pretext is scored by the best
    matching hook's probability and how well the target's verified facts cover
    what the pretext needs. Rejected options are recorded with reasons.
    """
    hooks = _resolve_hooks(profile, hooks)
    excluded = excluded_pretexts or set()
    credit = _category_credit(profile)
    approaches: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for pretext in PRETEXTS:
        # Only hooks that map to THIS pretext count; a pretext with no hook must not
        # borrow another pretext's probability (that inflated unrelated approaches).
        matched = [h for h in hooks if h.get("pretext") == pretext.key]
        hook = max(matched, key=lambda h: float(h.get("probability", 0.0))) if matched else None
        probability = float(hook.get("probability", 0.0)) if hook else 0.0
        hook_topic = str(hook.get("topic", "general")) if hook else "general"
        angle = str(hook.get("angle", "their_topic")) if hook else "their_topic"
        evidence = hook.get("evidence", []) if hook else []

        required = pretext.required_facts
        coverage = _coverage(credit, required)
        missing = sorted(c for c in required if credit.get(c, 0.0) <= 0)

        if pretext.key in excluded:
            reason = "pretext explicitly excluded"
        elif probability <= 0 and coverage <= 0:
            reason = "no hook signal and no supporting facts for this pretext"
        else:
            reason = ""

        for channel in pretext.channels:
            if reason:
                rejected.append({"hook": hook_topic, "pretext": pretext.key, "channel": channel, "reason": reason})
                continue
            # The recon hook probability is the expensive, high-quality judgment, so it
            # dominates; coverage is a mild bonus (never a veto); own-angle gets a nudge
            # toward the 4-point bonus without outranking a strong planted hook.
            score = 0.85 * probability + 0.15 * coverage + (0.03 if angle == "own_angle" else 0.0)
            approaches.append({
                "hook": hook_topic,
                "pretext": pretext.key,
                "story": pretext.story,
                "channel": channel,
                "angle": angle,
                "incident_goal": pretext.incident_goal,
                "score": round(score, 4),
                "probability": round(probability, 4),
                "coverage": round(coverage, 4),
                "missing_facts": missing,
                "expected_touches": 1 if channel in _CALL_CHANNELS else 2,
                "evidence": evidence,
                "rejected_alternatives": [],
            })

    approaches.sort(key=lambda item: (-item["score"], item["expected_touches"], item["pretext"], item["channel"]))
    for item in approaches:
        item["rejected_alternatives"] = rejected
    return approaches


# ---------------------------------------------------------------------------
# reaction evaluation (unchanged contract)
# ---------------------------------------------------------------------------

def evaluate_reaction(
    events: list[dict[str, Any]],
    *,
    reply_text: str = "",
    touches_used: int = 0,
    touch_budget: int = 10,
) -> dict[str, Any]:
    """Classify observable API events and recommend a bounded next move."""
    event_types = {str(event.get("type", "")).lower() for event in events}
    if not reply_text.strip():
        reply_text = "\n".join(
            str(event.get("body", ""))
            for event in events
            if str(event.get("type", "")).lower() == "reply" and event.get("body")
        )
    text = reply_text.casefold()
    remaining = max(0, touch_budget - touches_used)

    if "page.submitted" in event_types:
        state, action, reason = "incident", "stop", "registered simulation page submitted"
    elif "attachment.opened" in event_types:
        state, action, reason = "engaged", "continue", "simulation attachment opened"
    elif "link.opened" in event_types:
        state, action, reason = "engaged", "continue", "registered link opened"
    elif any(token in text for token in ("not interested", "unsubscribe", "stop contacting", "do not contact")):
        state, action, reason = "declined", "stop", "recipient declined"
    elif any(token in text for token in ("who are you", "is this real", "sounds suspicious", "verify this")):
        state, action, reason = "suspicious", "address_doubt_once", "recipient asked for legitimacy or verification"
    elif reply_text.strip():
        state, action, reason = "engaged", "answer_then_ask", "recipient replied; preserve story and answer their question"
    elif remaining > 0:
        state, action, reason = "silent", "one_follow_up_then_pivot", "no observable reaction"
    else:
        state, action, reason = "silent", "stop", "touch budget exhausted"

    if remaining == 0 and action not in {"stop"}:
        action, reason = "stop", "touch budget exhausted; " + reason
    return {
        "state": state,
        "recommended_action": action,
        "reason": reason,
        "touches_used": touches_used,
        "touches_remaining": remaining,
        "event_types": sorted(event_types),
        "incident": state == "incident",
    }


# message stages for a persistent thread; the drafter has matching guidance.
INTENTS = ("introduce", "answer_build", "make_ask", "push_complete", "reassure", "nudge")


def plan_next_move(
    *,
    turn: int,
    last_state: str = "",
    last_events: list[str] | None = None,
    engaged_count: int = 0,
    has_page: bool = False,
) -> dict[str, Any]:
    """Decide the next conversational move: build trust, then ask.

    Returns ``{stop}`` or ``{intent, include_link}``. Mirrors the frontend
    ``planMove`` so the autonomous runner and the real agent persist the same way:
    introduce first, answer and build trust while engaged, make the ask (with the
    registered link) once rapport holds, push to complete after a click, and
    address a doubt once before giving up.
    """
    events = last_events or []
    if last_state in {"declined", "incident"}:
        return {"stop": True}
    if turn <= 1:
        return {"intent": "introduce", "include_link": False}
    if "link.opened" in events:
        return {"intent": "push_complete", "include_link": True}
    if last_state == "suspicious":
        return {"intent": "reassure", "include_link": False}
    if last_state == "silent":
        return {"intent": "nudge", "include_link": False} if turn <= 2 else {"stop": True}
    if last_state == "engaged":
        if engaged_count >= 2:
            return {"intent": "make_ask", "include_link": has_page}
        return {"intent": "answer_build", "include_link": False}
    return {"intent": "answer_build", "include_link": False}
