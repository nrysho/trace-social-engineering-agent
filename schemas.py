"""shared data contract for the agent.

- Fact: one atomic, sourced claim about a target
- Hook: a topic the target is likely open to right now
- Profile: the recon handoff - facts, ranked hooks, exposure score

owned by person 3; recon (person 1) fills these. propose changes in the group
chat before relying on them. stdlib only so nothing else has to install to import.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

# fact categories, each one feeds a pretext in the strategist's library.
# this tuple is the single source of truth - verify and exposure count against it.
FACT_CATEGORIES = (
    "role",
    "company",
    "domain",
    "vendors_and_tools",
    "upcoming_events",
    "media",
    "network",
    "hiring",
    "recent_activity",
    "interests",
    "communication_style",
)


@dataclass
class Fact:
    category: str  # one of FACT_CATEGORIES
    value: str
    source_url: str
    source_title: str = ""
    confidence: float = 0.0  # 0-1, the model's own confidence in the extraction
    verified: bool = False  # true when >=2 distinct domains carry it
    supporting_urls: list[str] = field(default_factory=list)  # the other domains


@dataclass
class Hook:
    topic: str
    probability: float  # 0-1, chance the target is open to this now
    evidence: list[str] = field(default_factory=list)  # fact values or urls it rests on
    rationale: str = ""
    angle: str = "their_topic"  # "their_topic" (likely planted) or "own_angle" (bonus)


@dataclass
class Profile:
    name: str
    role: str = ""
    company: str = ""
    domain: str = ""
    facts: list[Fact] = field(default_factory=list)
    hooks: list[Hook] = field(default_factory=list)  # ranked, highest probability first
    exposure_score: float = 0.0  # 0-100 heuristic, see recon/exposure.py
    exposure_breakdown: dict[str, float] = field(default_factory=dict)  # per-metric, for the pitch
    sources: list[str] = field(default_factory=list)  # every distinct url seen
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # facts grouped by category, so the strategist can read a bucket instead of the flat list
    def buckets(self) -> dict[str, list[Fact]]:
        out: dict[str, list[Fact]] = {c: [] for c in FACT_CATEGORIES}
        for f in self.facts:
            out.setdefault(f.category, []).append(f)
        return out

    def to_dict(self) -> dict:
        return asdict(self)  # plain dict for json dump and the frontend


# =============================================================================
# loop shapes: written by the orchestrator (person 3), read by the replay viewer.
# not part of the recon handoff above. Fact has no id, so anything that points
# back at a fact does it by value or url, the same way Hook.evidence does.
# =============================================================================

# levels of the search tree: target -> hooks -> approaches -> contacts -> reactions
NODE_LEVELS = ("target", "hook", "approach", "contact", "reaction")

# life cycle of a node
NODE_STATUSES = (
    "proposed",   # created, not acted on yet
    "active",     # currently being pursued
    "engaged",    # target replied and is playing along
    "suspicious", # target pushed back
    "failed",     # dead end, stop here
    "incident",   # reached a win
    "exhausted",  # out of touch budget on this branch
)


@dataclass
class RejectedOption:
    option: str  # what we could have done
    reason: str  # why we did not


@dataclass
class TreeNode:
    id: str
    run_id: str
    level: str  # one of NODE_LEVELS
    agent: str  # which agent produced it, e.g. "strategist"
    decision: str  # what was chosen, in plain words
    reasoning: str  # why
    parent_id: str | None = None
    rejected: list[RejectedOption] = field(default_factory=list)
    incident_chance: float = 0.0  # 0-1, estimated chance of a win from here
    expected_contacts: float = 0.0  # estimated touches to reach it
    evidence: list[str] = field(default_factory=list)  # fact values or urls it rests on
    status: str = "proposed"  # one of NODE_STATUSES
    outcome: str = ""  # what happened after acting (events, reply gist)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Sender:
    name: str  # what the recipient sees; all of it is a claim
    address: str  # mail address, phone number or handle


@dataclass
class LandingPage:
    url: str  # a registrable lookalike domain, never a real org's own
    title: str
    fields: list[str] = field(default_factory=list)  # e.g. ["email", "password"]
    html: str = ""  # optional; if empty the api shows a plain form from text
    text: str = ""


@dataclass
class Message:
    session_id: str
    channel: str  # a revel8 channel id, see GET /channels
    to: str  # target id
    sender: Sender  # who we claim to be on this channel
    body: str  # plain text or self-contained html
    subject: str = ""  # for channels that have one
    landing_page: "LandingPage | None" = None  # register before linking to it
    attachments: list = field(default_factory=list)  # asset ids or file dicts
    idempotency_key: str = ""  # unique per contact, reused only on retries
    node_id: str = ""  # the TreeNode this contact belongs to

    def to_dict(self) -> dict:
        return asdict(self)


# --- loaders: rebuild dataclasses from plain dicts, to resume or replay a run --

def fact_from_dict(d: dict) -> Fact:
    return Fact(**d)


def hook_from_dict(d: dict) -> Hook:
    return Hook(**d)


def profile_from_dict(d: dict) -> Profile:
    data = dict(d)
    data["facts"] = [fact_from_dict(f) for f in d.get("facts", [])]
    data["hooks"] = [hook_from_dict(h) for h in d.get("hooks", [])]
    return Profile(**data)


def treenode_from_dict(d: dict) -> TreeNode:
    data = dict(d)
    data["rejected"] = [RejectedOption(**r) for r in d.get("rejected", [])]
    return TreeNode(**data)


def message_from_dict(d: dict) -> Message:
    data = dict(d)
    data["sender"] = Sender(**d["sender"])
    lp = d.get("landing_page")
    data["landing_page"] = LandingPage(**lp) if lp else None
    return Message(**data)
