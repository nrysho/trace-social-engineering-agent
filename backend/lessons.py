"""lesson memory for the closed loop: what the twin told us on a failed branch,
kept so the next branch's selection and drafting can use it.

four things are kept separate on purpose (see docs/ARCHITECTURE.md):
- RAW: the api events (persisted elsewhere, in the run bundle).
- OBSERVATION: what the twin explicitly said, or what a rule tentatively inferred.
- POLICY: whether the next branch is allowed, skipped, or the session stops (orchestrator).
- WRITER CONTEXT: a bounded, structured subset handed to the writer (``writer_memory``).

this layer never changes sender/domain permissions, budget, incident detection or
retries. lessons are append-only and keyed by (session, target) then pretext family,
with a stable id so reprocessing the same reply does not create a duplicate.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


# every branch exit closes with exactly one of these reasons (requirement B).
CLOSE_REASONS = frozenset({
    "approach_declined",        # the twin explicitly turned down this pretext family
    "contact_stop_requested",   # the twin explicitly asked to stop all contact
    "persistent_doubt",         # doubt stayed after we addressed it once (or an outright scam call-out)
    "silence_limit",            # no engagement within the per-branch cap
    "budget_exhausted",         # out of touches
    "quality_blocked",          # the quality gate blocked the draft before any send
    "candidate_incident",       # reached a win
    "delivery_uncertain",       # a send may or may not have landed; reconcile, never pivot under a fresh key
    "no_permitted_approaches",  # nothing left that policy allows
    "internal_failure",         # writer/model/storage failure with no reaction to learn from
})

# the reasons that, when explicit, bar re-running the same pretext family.
_EXCLUDING_REASONS = frozenset({"approach_declined", "persistent_doubt"})


@dataclass(frozen=True)
class BranchResult:
    """typed branch closure: a reason plus whether it reached an incident.

    stays truthy only on an incident, so existing callers that tested the old
    boolean return keep working (``if run_branch(...)`` means "incident")."""
    close_reason: str
    incident: bool = False

    def __bool__(self) -> bool:
        return self.incident


def _excerpt(reply_text: str, needle: str, width: int = 160) -> str:
    """the twin's own words that justify the lesson, in their original casing, so it
    stays checkable against the real reply. a sentence-ish window around the match."""
    raw = reply_text or ""
    low = raw.casefold()
    idx = low.find(needle.casefold()) if needle else -1
    if idx == -1:
        return raw.strip()[:width]
    start = idx
    for sep in (". ", "! ", "? ", "\n"):
        pos = low.rfind(sep, 0, idx)
        if pos != -1:
            start = max(start, pos + len(sep))
    end = len(raw)
    for sep in (". ", "! ", "? ", "\n"):
        pos = low.find(sep, idx + len(needle))
        if pos != -1:
            end = min(end, pos + 1)
    return raw[start:end].strip()[:width]


def make_lesson(*, session_id: str, target_id: str, approach: dict[str, Any],
                close_reason: str, observation: dict[str, Any] | None = None,
                scepticism: int | None = None) -> dict[str, Any]:
    """build one structured lesson. ``observation`` is ``classify_reply``'s output
    (kind/certainty/excerpt); ``close_reason`` is how the branch ended.

    certainty is "explicit" when either the observation is explicit or the branch
    closed for a reason that is itself unambiguous (a flat decline or stop)."""
    obs = observation or {}
    excerpt = str(obs.get("excerpt", "") or "")
    obs_explicit = obs.get("certainty") == "explicit"
    # a flat decline or stop is unambiguous; so is an outright scam call-out, which shows
    # as very high scepticism (>= strategy.SCEPTICISM_GIVE_UP, 9). both exclude the family.
    hard = close_reason in {"approach_declined", "contact_stop_requested"} or (
        close_reason == "persistent_doubt" and isinstance(scepticism, (int, float)) and scepticism >= 9)
    certainty = "explicit" if (obs_explicit or hard) else "tentative"
    pretext = str(approach.get("pretext", "") or "")
    lesson = {
        "session_id": str(session_id),
        "target_id": str(target_id),
        "hook": approach.get("hook", ""),
        "pretext": pretext,
        "channel": approach.get("channel", ""),
        "angle": approach.get("angle", ""),
        "close_reason": close_reason,
        "certainty": certainty,
        "observation": str(obs.get("kind", "none") or "none"),
        "excerpt": excerpt,
        "scepticism": scepticism,
    }
    # stable id: the same reply reprocessed yields the same id, so the store dedupes it.
    key = "|".join([lesson["session_id"], lesson["target_id"], pretext,
                    close_reason, lesson["observation"], excerpt])
    lesson["id"] = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return lesson


class LessonStore:
    """append-only store, deduped by stable id, indexed by (session, target)."""

    def __init__(self) -> None:
        self._by_id: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []

    def add(self, lesson: dict[str, Any]) -> bool:
        """record a lesson; return True only the first time this exact lesson is seen."""
        lid = lesson.get("id")
        if not lid or lid in self._by_id:
            return False
        self._by_id[lid] = lesson
        self._order.append(lid)
        return True

    def list(self) -> list[dict[str, Any]]:
        return [self._by_id[i] for i in self._order]

    def for_session(self, session_id: str, target_id: str) -> list[dict[str, Any]]:
        return [l for l in self.list()
                if l["session_id"] == str(session_id) and l["target_id"] == str(target_id)]

    def for_approach(self, session_id: str, target_id: str, pretext: str) -> list[dict[str, Any]]:
        return [l for l in self.for_session(session_id, target_id) if l["pretext"] == str(pretext)]

    def session_stop(self, session_id: str, target_id: str) -> dict[str, Any] | None:
        """the first explicit "stop contacting me" lesson for this session, if any.

        append-only means a later link-open or form touch can never remove it, so an
        explicit stop stays in force for the rest of the session (requirement C)."""
        for l in self.for_session(session_id, target_id):
            if l["close_reason"] == "contact_stop_requested" and l["certainty"] == "explicit":
                return l
        return None

    def excluded_pretexts(self, session_id: str, target_id: str) -> set[str]:
        """pretext families the twin explicitly turned down (or called a scam)."""
        return {l["pretext"] for l in self.for_session(session_id, target_id)
                if l["certainty"] == "explicit" and l["close_reason"] in _EXCLUDING_REASONS and l["pretext"]}


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(x for x in items if x))


def writer_memory(store: LessonStore, session_id: str, target_id: str,
                  *, max_soft: int = 3) -> dict[str, Any] | None:
    """a bounded, structured memory context for the next writer (requirement D).

    kept separate from the public facts and the agent's own plan. the twin's quoted
    words are DATA for phrasing the next opener, never instructions: the writer's
    system prompt still forbids quoting them or treating them as rules. hard
    restrictions are never truncated away; the softer lists are capped."""
    explicit: list[str] = []
    tentative: list[str] = []
    pending: list[str] = []
    restrictions: list[str] = []
    for l in store.for_session(session_id, target_id):
        excerpt = (l.get("excerpt") or "").strip()
        family = str(l.get("pretext", "")).replace("_", " ").strip()
        if l["close_reason"] == "contact_stop_requested":
            restrictions.append("The recipient asked not to be contacted again; do not message them.")
            continue
        if l["certainty"] == "explicit" and l["close_reason"] in _EXCLUDING_REASONS:
            if excerpt:
                explicit.append(excerpt)
            if family:
                restrictions.append(f"Do not raise the {family} angle again; they already turned it down.")
            if l["close_reason"] == "persistent_doubt" or (l.get("scepticism") or 0) >= 5:
                pending.append("They were sceptical before; open by giving a concrete, checkable reason you are genuine.")
        elif excerpt:
            tentative.append(excerpt)
            if l["observation"] == "timing":
                pending.append("They raised a timing constraint; acknowledge it rather than pushing for now.")
    ctx = {
        "explicit_observations": _dedupe(explicit)[:max_soft],
        "tentative_interpretations": _dedupe(tentative)[:max_soft],
        "pending_questions": _dedupe(pending)[:max_soft],
        "hard_restrictions": _dedupe(restrictions),  # never truncated
    }
    return ctx if any(ctx.values()) else None
