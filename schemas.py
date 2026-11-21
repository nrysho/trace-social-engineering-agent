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
