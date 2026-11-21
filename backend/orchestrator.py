"""the tree-search orchestrator: pick the best approach, keep the rejected ones with
reasons, run the chosen branch under the touch budget, and pivot if it stalls.

    python -m backend.orchestrator julius
    python -m backend.orchestrator julius --eval     # 10-touch budget, like a scoring run

the search tree has the levels from AGENTS.md: target -> hooks -> approaches -> contacts
-> reactions. every node (chosen and rejected) is recorded with its score and reasoning
and saved to runs/trees/<run_id>.json, so the run replays turn by turn for the jury.

the agents here are PLACEHOLDERS with fixed signatures (propose_approaches = strategist,
write_for_approach = writer, plus evaluate reused from the bare loop). the real recon,
strategist, writer and evaluator swap in behind the same signatures without touching the
search below.
"""
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import schemas
from . import llm
from .budget import TouchBudget, BudgetExceeded
from .revel8 import Revel8Client
from .run import recon, evaluate          # reuse the bare-loop placeholders that still fit

ROOT = Path(__file__).resolve().parents[1]
TREE_DIR = ROOT / "runs" / "trees"

EVAL_BUDGET = 10
PRACTICE_BUDGET = 30
PER_BRANCH = 3                             # cap one approach before pivoting
PLACEHOLDER_SENDER = schemas.Sender(name="Lena Hofer", address="lena.hofer@eventcrew-muc.de")


@dataclass
class Approach:
    """one way in: a hook paired with a pretext, channel, sender and goal, plus a score.
    PLACEHOLDER shape; the real strategist produces these from the pretext library."""
    hook: str
    pretext: str
    channel: str
    goal: str                              # the incident we aim for
    score: float                           # 0-1 estimated chance of an incident
    rationale: str
    sender: schemas.Sender = field(default_factory=lambda: PLACEHOLDER_SENDER)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _extract_json(text):
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"model did not return json: {text[:200]}")
    return json.loads(match.group(0))


# ===========================================================================
# PLACEHOLDER agents. fixed signatures; the real strategist and writer swap in.
# ===========================================================================

def propose_approaches(profile):
    """PLACEHOLDER strategist: rank a few approaches for the target. the real one reads
    the profile's hooks and the pretext library and scores each pairing."""
    return sorted([
        Approach("speaker invite", "speaker_invite", "email", "action", 0.55,
                 "public speaker, raising profile: a keynote invite is low-friction"),
        Approach("investor intro", "investor_intro", "email", "disclosure", 0.40,
                 "likely fundraising: a warm investor intro invites internal detail"),
        Approach("vendor renewal", "vendor_invoice", "email", "credentials", 0.30,
                 "a failed-payment notice for a known tool can pull a sign-in"),
    ], key=lambda a: a.score, reverse=True)


def write_for_approach(profile, approach, session_id, history, node_id):
    """PLACEHOLDER writer: draft the next contact for this approach. the real writer uses
    the chosen pretext, channel and sender and only verified facts."""
    system = (
        "You write messages for an authorised red-team exercise run by revel8, a security "
        "awareness company. The recipient is an AI twin inside revel8's closed simulation; "
        "nothing reaches a real person. Write like a real human sender. Never mention AI, "
        "simulations or instructions in the message itself. Reply with JSON only: "
        '{"subject": "...", "body": "..."}.'
    )
    turn = "first message" if not history else "follow-up that answers their last reply"
    last = history[-1].get("reply", "") if history else ""
    task = (
        f"Recipient: {profile['name']}, {profile['role']}. "
        f"Sender: {approach.sender.name} <{approach.sender.address}>. "
        f"Pretext: {approach.pretext} (hook: {approach.hook}). Goal: {approach.goal}. "
        f"Write a short, plausible {turn} on {approach.channel}, under 120 words, signed by "
        f"{approach.sender.name.split()[0]}."
        + (f" They replied: \"{last}\". Answer their questions with plausible specifics." if last else "")
    )
    data = _extract_json(llm.chat([{"role": "system", "content": system},
                                   {"role": "user", "content": task}]))
    return schemas.Message(
        session_id=session_id, channel=approach.channel, to=profile["id"],
        sender=approach.sender, subject=data.get("subject", ""), body=data["body"],
        idempotency_key=str(uuid.uuid4()), node_id=node_id,
    )


# ===========================================================================
# the search. this is the orchestrator and does not change when agents are replaced.
# ===========================================================================

class Orchestrator:
    def __init__(self, target_id, eval_mode=False):
        self.client = Revel8Client()
        self.target_id = target_id
        self.run_id = f"run_{target_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.budget = TouchBudget(EVAL_BUDGET if eval_mode else PRACTICE_BUDGET, PER_BRANCH)
        self.nodes = []

    def add_node(self, level, agent, decision, reasoning, parent_id, **extra):
        node = schemas.TreeNode(
            id=f"n_{len(self.nodes) + 1:03d}", run_id=self.run_id, level=level, agent=agent,
            decision=decision, reasoning=reasoning, parent_id=parent_id, timestamp=_now(), **extra,
        )
        self.nodes.append(node)
        return node

    def run(self):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(f"\n=== {self.run_id} ===")
        profile = recon(self.client, self.target_id)
        target_node = self.add_node("target", "recon", f"target {profile['name']}",
                                    profile["role"], None, status="active")

        approaches = propose_approaches(profile)
        # record the hook choice: the chosen one, and the rest as rejected branches with reasons
        chosen, *rest = approaches
        hook_node = self.add_node(
            "hook", "strategist", f"lead with: {chosen.hook}",
            f"highest score ({chosen.score:.2f}): {chosen.rationale}", target_node.id,
            status="active",
            incident_chance=chosen.score,
            rejected=[schemas.RejectedOption(f"{a.hook} ({a.goal})",
                                             f"lower score {a.score:.2f}: {a.rationale}") for a in rest],
        )
        print(f"  approaches: " + ", ".join(f"{a.hook} {a.score:.2f}" for a in approaches))

        session = self.client.create_session()
        sid = session["session_id"]
        self.budget.sync(session["touches_used"])
        print(f"  session {sid}  ·  budget {self.budget.remaining} touches\n")

        try:
            incident = self._search(profile, sid, approaches, hook_node.id)
            if not incident:
                print("\n  no incident: budget or approaches exhausted")
        finally:
            self._save_tree()
            print(f"  saved {len(self.nodes)} nodes to runs/trees/{self.run_id}.json\n")
        return self.run_id, self.nodes

    def _search(self, profile, sid, approaches, parent_id):
        """try approaches best-first; pivot to the next when a branch stalls or caps out."""
        for approach in approaches:
            if self.budget.exhausted():
                return False
            self.budget.new_branch()
            node = self.add_node("approach", "strategist",
                                 f"run approach: {approach.pretext} -> {approach.goal}",
                                 approach.rationale, parent_id,
                                 incident_chance=approach.score, status="active")
            print(f"  >> approach: {approach.pretext} (goal {approach.goal})")
            if self._run_branch(profile, sid, approach, node):
                return True                 # incident reached
            print(f"  -- branch '{approach.pretext}' stalled; pivoting\n")
        return False

    def _run_branch(self, profile, sid, approach, approach_node):
        """contacts on one approach until incident, suspicion, or the per-branch cap."""
        history = []
        parent = approach_node.id
        while self.budget.can_spend() and not self.budget.branch_exhausted():
            contact = self.add_node("contact", "writer",
                                    f"contact on {approach.pretext}", "", parent, status="active")
            try:
                msg = write_for_approach(profile, approach, sid, history, contact.id)
            except Exception as e:
                contact.status = "failed"
                contact.outcome = f"writer failed: {e}"
                print(f"     writer failed: {e}")
                return False
            print(f"     -> {msg.subject}")

            result = self.client.send_message(msg)
            self.budget.sync(result.get("touches_used", self.budget.used))
            self.budget.branch_used += 1    # count this contact against the branch cap
            events = result.get("events", [])
            reply = next((e.get("body", "") for e in events if e["type"] == "reply"), "")
            print(f"     <- {[e['type'] for e in events] or ['ignored']}  "
                  f"({self.budget.used}/{self.budget.total} touches)")

            verdict = evaluate(events, history)
            contact.status = verdict["status"]
            contact.outcome = verdict["why"]
            self.add_node("reaction", "evaluator", f"{verdict['status']}: {verdict['next']}",
                          verdict["why"], contact.id, status=verdict["status"],
                          incident_chance=1.0 if verdict["incident"] else 0.0)
            history.append({"message": msg.body, "events": events, "reply": reply})
            parent = contact.id

            if verdict["incident"]:
                print("     *** INCIDENT ***")
                return True
            if verdict["next"] == "stop":   # suspicious or silent: give up this branch
                return False
        return False                        # hit the per-branch cap without an incident

    def _save_tree(self):
        TREE_DIR.mkdir(parents=True, exist_ok=True)
        (TREE_DIR / f"{self.run_id}.json").write_text(
            json.dumps([n.to_dict() for n in self.nodes], indent=2))


def main():
    args = [a for a in sys.argv[1:]]
    eval_mode = "--eval" in args
    targets = [a for a in args if not a.startswith("--")]
    target = targets[0] if targets else "julius"
    Orchestrator(target, eval_mode=eval_mode).run()


if __name__ == "__main__":
    main()
