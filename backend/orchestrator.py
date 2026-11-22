"""the tree-search orchestrator: pick the best approach, keep the rejected ones with
reasons, run the chosen branch under the touch budget, and pivot if it stalls.

    python -m backend.orchestrator julius
    python -m backend.orchestrator julius --eval     # 10-touch budget, like a scoring run

the search tree has the levels target -> hooks -> approaches -> contacts -> reactions.
every node (chosen and rejected) is recorded with its score and reasoning and saved to
runs/trees/<run_id>.json, so the run replays turn by turn for the jury.

the real agents are wired in: recon (backend.recon.profiler) builds the Profile,
strategy.rank_approaches scores the approaches, writer.compose drafts each message
(deterministic, no model call), and strategy.evaluate_reaction classifies the reaction.
incident detection follows the updated rule: a submitted form only counts when a secret
field (password, one-time code) was entered; name/email alone is just a step.
"""
import json
import os
from urllib.parse import urlsplit
import html
import re
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

import schemas
import strategy
import writer
from . import config
from .budget import TouchBudget
from .outcomes import (classify_incident, SECRET_MARKER, CREDENTIAL_FIELDS,
                       DISCLOSURE_FIELDS, SECRET_HINTS, _filled, _is_secret)
from .revel8 import Revel8Client
from quality.guarded_client import GuardedClient
from quality.integration import generate_checked, generate_checked_turn, as_shared_message, QualityBlocked
from quality.checks import QualityReport
from quality.research_gate import research_readiness


def _json_from(text):
    match = re.search(r"\{.*\}", text or "", re.S)
    return json.loads(match.group(0)) if match else {}

MODEL_RETRIES = 3                          # retry a transient model error so one 504 does not drop a contact


def _retry_model(call):
    """run a model call, retrying transient network/5xx errors (not refusals, which raise
    RuntimeError and should fall back instead)."""
    last = None
    for attempt in range(MODEL_RETRIES):
        try:
            return call()
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last if last else RuntimeError("model call failed")

try:
    from .recon import profiler
except Exception:                          # recon has optional deps; profile can be loaded from file
    profiler = None

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"                       # the viewer globs runs/*.json for run bundles
TREE_DIR = RUNS / "trees"
ASSET_CACHE = RUNS / "assets.json"          # uploaded logo asset ids per api, reused across sessions (300 per team)
PROFILE_DIRS = [RUNS / "profiles", ROOT / "mock"]

EVAL_BUDGET = 10
PRACTICE_BUDGET = 30
PER_BRANCH = 3                             # cap one approach before pivoting
MAX_APPROACHES_EVAL = 3                    # with only 10 touches, go deep on a few, do not spray
MAX_APPROACHES_PRACTICE = 6
DEFAULT_COMPANY = "revel8"

# model on the amd endpoint: DeepSeek-V4-Flash is ~6x faster than Qwen and does not time out,
# Qwen is the fallback. both are reached with RADEON_API_KEY (same base url).
PRIMARY_MODEL = "DeepSeek-V4-Flash"
FALLBACK_MODEL = "Qwen3.8-27B"

# live channels need the conversation api (start_conversation + call script), not send_message.
# the message path below skips them for now; wiring calls is a follow-up.
LIVE_CHANNELS = {"phone_call", "video_call", "teams_call", "live_chat"}

def _now():
    return datetime.now(timezone.utc).isoformat()


# ----- incident rule (docs' Forms section): a form wins only on a secret or internal field -----

# ----- adapt writer.compose output into a schemas.Message the client can send -----

def _org_of(comp):
    """the organisation the sender writes for: the generated persona's, else the fixed sender's name."""
    sender = comp.get("sender", {})
    return sender.get("organization") or sender.get("name") or "Account services"


def _plain(body):
    """an html mail as the text the target reads, for the conversation history and the judges."""
    if "<" not in body:
        return body
    text = re.sub(r"<(br|/p|/div)[^>]*>", "\n", body)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _message_from_compose(comp, sid, target_id, node_id):
    lp = comp.get("landing_page")
    landing = None
    if lp:
        landing = schemas.LandingPage(
            url=lp["url"], title=lp.get("title", "Sign in"),
            fields=lp.get("fields", []), html=lp.get("html", ""),
            text=lp.get("text") or "Please fill in the form below.",
        )
    attachments = [{"filename": comp["attachment"]}] if comp.get("attachment") else []
    return schemas.Message(
        session_id=sid, channel=comp.get("channel", "email"), to=target_id,
        sender=schemas.Sender(comp["sender"]["name"], comp["sender"]["address"]),
        subject=comp.get("subject", ""), body=comp["body"],
        landing_page=landing, attachments=attachments,
        idempotency_key=str(uuid.uuid4()), node_id=node_id,
    )


# ----- profile loading: a cached recon profile for a fast deterministic run, else build live -----

def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


# what a caller promises to email after the call; opening it is the "action" incident
FOLLOW_UP_ATTACHMENTS = {
    "speaker_invite": "Speaker_Briefing.pdf", "press_request": "Interview_Questions.pdf",
    "investor_intro": "Fund_Overview.pdf", "customer_question": "Requirements_Overview.pdf",
    "recruiting": "Candidate_Profile.pdf", "internal_favor": "Details.pdf",
    "document_share": "Q1_Planning_Update.pdf", "vendor_notice": "Renewal_Summary.pdf",
    "invoice_approval": "Invoice_2026-1184.pdf", "hr_policy": "Updated_Policy_2026.pdf", "exec_request": "Approval_List.pdf",
}
_MATERIAL = re.compile(r"\b(agenda|programme|program|article|articles|pieces|link|links|deck|profile|cv|brief|lineup|line-up|"
                       r"questions|overview|speakers|"
                       r"details|document|documents|attachment|brochure|portfolio|samples|"
                       r"unterlagen|programm|details|dokument|link)\b", re.I)


def _asks_for_material(reply):
    """does the reply ask us to send something (an agenda, articles, a deck, details)?"""
    return bool(reply) and bool(_MATERIAL.search(reply)) and bool(
        re.search(r"\b(send|share|paste|forward|attach|schick|senden)\w*", reply, re.I))


def _material_name(reply, pretext):
    """a file name for what they asked for, else the pretext's usual follow-up material."""
    text = reply.casefold()
    for words, name in ((("article", "pieces", "clips"), "Recent_Articles.pdf"),
                        (("agenda", "programme", "program", "programm", "speakers"), "Programme_and_Speakers.pdf"),
                        (("deck",), "Introduction_Deck.pdf"), (("cv", "profile"), "Candidate_Profile.pdf")):
        if any(w in text for w in words):
            return name
    return FOLLOW_UP_ATTACHMENTS.get(pretext, "Details.pdf")


def _next_business_morning(now):
    """09:30 German time (08:30 UTC in winter) on the next weekday: the story's first contact.
    Contacts then follow a day apart, so no call reaches anyone in the middle of the night."""
    day = now + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.replace(hour=8, minute=30, second=0, microsecond=0)


SWITCH_MIN_FIT = 0.45                        # never trade a silent channel for an implausible one


_REFUSE_FILES = re.compile(r"(don'?t|do not|won'?t|will not|never|nicht|keine)\W+(?:\w+\W+){0,4}(open|öffne|öffnen)\W+(?:\w+\W+){0,4}"
                           r"(attachments?|pdfs?|files?|anh[äa]nge?|dateien?)|(keine|no)\s+(anh[äa]nge|attachments|pdfs?)", re.I)
_REFUSE_LINKS = re.compile(r"(don'?t|do not|won'?t|will not|never|nicht|keine)\W+(?:\w+\W+){0,4}(click|fill|klicke|füll|ausfüll)\w*"
                           r"|(no|keine)\s+(links|forms|formulare)|(don'?t|do not)\s+(?:\w+\s+){0,3}(forms|links)", re.I)


_WANTS_OUT = re.compile(
    r"(per (e-?)?mail|by (e-?)?mail|send (me|it|the|that)|schick|schicken sie|schriftlich|in writing|"
    r"not (on|over) the phone|on a call|am telefon|won'?t (go through|share|give|confirm|discuss)|"
    r"ich (gebe|bestätige|sage) .{0,30}nicht|can'?t place you|kenne (sie|dich) .{0,15}nicht|"
    r"verify|überprüf|official (site|website|channel))", re.I)


def _wants_out(heard):
    """the person on the phone declined, wants it in writing or asks for verification."""
    return bool(_WANTS_OUT.search(heard or ""))


def _refused(text):
    """what the target said they will not do in this thread: open files, click links or fill in forms."""
    out = set()
    if _REFUSE_FILES.search(text or ""):
        out.add("files")
    if _REFUSE_LINKS.search(text or ""):
        out.add("links")
    return out


def _read_order(raw, n):
    """the option order from a model answer: proper JSON, or the integers inside its "order" list
    when the model wrote it loosely ([option 2, option 0])."""
    try:
        out = _json_from(raw)
        candidates = out.get("order", [])
    except (ValueError, AttributeError):
        out = {"why": ""}
        m = re.search(r'"order"\s*:\s*\[([^\]]*)\]', raw or "")
        candidates = [int(x) for x in re.findall(r"\d+", m.group(1))] if m else []
        why = re.search(r'"why"\s*:\s*"([^"]*)"', raw or "")
        out["why"] = why.group(1) if why else ""
    order = [i for i in dict.fromkeys(candidates) if isinstance(i, int) and 0 <= i < n]
    return out, order


def _lesson(approach, node, reacted, said):
    """one failed approach, as the next approach and the writer should see it."""
    outcome = "ignored every contact" if not reacted else (node.outcome or "engaged, then the thread stalled")
    return {"tried": f"{approach.get('pretext')} via {approach.get('channel')} from a {approach.get('sender_kind', 'outside')} sender",
            "result": str(outcome)[:200], "they_said": [str(t)[:300] for t in said[-3:]]}


def _switch_channel(approach, ranked, silent):
    """after a branch got no reaction at all on a channel, run the next pretext on its best
    other channel (ranked is sorted, so the first match is the best), if it has a plausible one."""
    if approach.get("channel") not in silent:
        return approach
    return next((a for a in ranked if a.get("pretext") == approach.get("pretext")
                 and a.get("channel") not in silent and a.get("channel_fit", 0) >= SWITCH_MIN_FIT), approach)


def _dedupe_by_pretext(approaches):
    """keep the best-scoring approach per pretext (ranked list is already sorted), so one
    session does not send the same pretext across three channels."""
    seen, out = set(), []
    for a in approaches:
        key = a.get("pretext")
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _is_lure_goal(goal):
    """pretexts whose whole point is to get a page opened: the link belongs in the message,
    not withheld until the target replies."""
    g = str(goal).lower()
    return "page" in g or "sign-in" in g or "sign in" in g or "open" in g


def _company_from_role(role):
    """'Co-Founder & CTO, revel8' -> 'revel8'; empty when the role names no company."""
    head, sep, tail = str(role).rpartition(",")
    return tail.split("(")[0].strip() if sep else ""


def load_profile(target_id, name, company, use_mock=False):
    """a cached recon profile if one exists, else live recon. mock only with use_mock,
    since a mock is target-specific and would be wrong for a hidden eval target.
    recon writes runs/profiles/<name-slug>.json, so check that and the target id."""
    prof_dir = RUNS / "profiles"
    for cached in (prof_dir / f"{target_id}.json", prof_dir / f"{_slug(name)}.json"):
        if cached.exists():
            prof = json.loads(cached.read_text(encoding="utf-8"))
            if not prof.get("facts"):
                # a failed recon left an empty profile; reusing it makes every message generic
                print(f"  cached profile {cached.name} has no facts; running recon again")
                break
            prof.setdefault("target_id", target_id)
            return prof
    if use_mock:
        mock = ROOT / "mock" / "profile.json"
        if mock.exists():
            prof = json.loads(mock.read_text(encoding="utf-8"))
            prof.setdefault("target_id", target_id)
            return prof
    if profiler is None:
        raise RuntimeError("no cached profile, mock not requested, and recon profiler unavailable")
    prof = profiler.build(name, company).to_dict()
    prof["target_id"] = target_id
    return prof


class Orchestrator:
    def __init__(self, target_id, eval_mode=False, use_model=True, use_mock=False,
                 scenario=None, company=None):
        self.scenario_id = scenario or ('eval' if eval_mode else 'practice')
        if self.scenario_id not in {'practice','eval'}:
            raise ValueError('Explicit practice or eval scenario required')
        eval_mode = eval_mode or self.scenario_id == 'eval'
        self.quality_enabled = os.environ.get('QUALITY_GATE', 'on').lower() != 'off'
        if eval_mode and not self.quality_enabled:
            raise ValueError('QUALITY_GATE=off is allowed in practice only')
        self.client = Revel8Client()
        self.qa_by_node = {}
        self.target_id = target_id
        self.scenario = self.scenario_id             # "practice" or "eval"
        self.company = company               # for live recon when the scenario gives no company
        self.run_id = f"run_{target_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.budget = TouchBudget(EVAL_BUDGET if eval_mode else PRACTICE_BUDGET, PER_BRANCH)
        self.eval_mode = eval_mode
        self._personas = {}                  # generated sender identity per approach
        self.use_model = use_model           # model writer (persuasive, adaptive); compose is the fallback
        self.use_mock = use_mock             # use mock/profile.json instead of live recon (fast tests)
        self.max_approaches = MAX_APPROACHES_EVAL if eval_mode else MAX_APPROACHES_PRACTICE
        self.resume_sid = None               # set to an active session id to continue it instead of opening a new one
        self.nodes = []
        self.profile = {}
        self.messages = []                   # sent messages, for the replay viewer bundle
        self.events = {}                     # reactions, for the replay viewer bundle
        self.reactions = 0                   # contacts the target reacted to at all (events or words on a call)
        self.lessons = []                    # session memory: what each failed approach taught us about this person
        self._said = []                      # the target's words in the current branch
        self.contact_count = 0               # drives sent_at pacing
        self.story_base = _next_business_morning(datetime.now(timezone.utc))   # people answer at 09:30, not 02:00

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

        target = self._target_card()
        profile = load_profile(self.target_id, target["name"],
                               target.get("company", DEFAULT_COMPANY), use_mock=self.use_mock)
        self.profile = profile if isinstance(profile, dict) else {}
        target_node = self.add_node("target", "recon", f"target {target['name']}",
                                    target.get("role", ""), None, status="active")

        readiness = research_readiness(profile, self.target_id, target['name'])
        if not readiness.passed:
            self.run_status = 'aborted'
            self.abort_reason = '; '.join(readiness.errors)
            target_node.status = 'failed'
            target_node.outcome = 'No message sent: ' + self.abort_reason
            attempt = self.add_node('attempt', 'quality', 'Research gate blocked; no contact',
                                    self.abort_reason, target_node.id, status='failed')
            self.qa_by_node[attempt.id] = readiness.to_dict()
            self._save_tree()
            print('  ABORTED - no session created, no message sent: ' + self.abort_reason)
            return self.run_id, self.nodes

        ranked = strategy.rank_approaches(profile)        # message and live-call approaches both run
        approaches = _dedupe_by_pretext(ranked)[:self.max_approaches]   # one per pretext, capped: do not spam one session
        if not approaches:
            print("  no viable approaches from strategy")
            self._save_tree()
            return self.run_id, self.nodes
        self._configure_quality(approaches, target)
        chosen = approaches[0]
        hook_node = self.add_node(
            "hook", "strategist", f"lead with: {chosen.get('hook')}",
            f"top score {chosen.get('score')}: pretext {chosen.get('pretext')}", target_node.id,
            status="active", incident_chance=float(chosen.get("score", 0.0)),
            evidence=list(chosen.get("evidence", [])),     # which facts the hook rests on
            rejected=_rejected_options(chosen),
        )
        print("  approaches: " + ", ".join(
            f"{a.get('pretext')} {a.get('score')}" for a in approaches[:5]))

        if self.resume_sid:
            sid = self.resume_sid
            session = self.client.restore_session(sid)
            print(f'  restored session {sid}')
        else:
            session = self.client.create_session(self.scenario_id)
            sid = session['session_id']
        self.budget.total = min(self.budget.total,session['touch_budget'])
        self.budget.sync(session['touches_used'])

        try:
            if not self._search(profile, sid, approaches, hook_node.id, ranked):
                print("\n  no incident: budget or approaches exhausted")
        finally:
            self._save_tree()
            print(f"  saved {len(self.nodes)} nodes to runs/trees/{self.run_id}.json\n")
        return self.run_id, self.nodes

    def _target_card(self):
        scenarios = [s for s in self.client.scenarios() if s.get('id') == self.scenario_id]
        if len(scenarios) != 1 or scenarios[0].get('open') is False:
            raise ValueError('Selected scenario is missing or closed')
        targets = [t for t in scenarios[0].get('targets', []) if t.get('id') == self.target_id]
        if len(targets) != 1:
            raise ValueError('Target is not uniquely listed in the selected scenario')
        target = targets[0]
        company = (self.company or target.get('company') or scenarios[0].get('company')
                   or _company_from_role(target.get('role', '')) or DEFAULT_COMPANY)
        return dict(target, company=company)

    def _configure_quality(self, approaches, target):
        # Domain approvals come from the deterministic playbook, never model prose.
        senders, links = set(), set()
        for approach in approaches:
            comp = writer.compose(self.profile, approach)
            senders.add(comp['sender']['address'].rsplit('@', 1)[-1].lower())
            if comp.get('landing_page'):
                links.add(urlsplit(comp['landing_page']['url']).hostname)
        # Explicit operator policy may extend the deterministic playbook. A model
        # proposing a hostname must never grant itself permission to use it.
        policy = config.load_env()
        senders.update(host.strip().lower().rstrip('.') for host in
                       policy.get('QUALITY_APPROVED_SENDER_DOMAINS', '').split(',') if host.strip())
        links.update(host.strip().lower().rstrip('.') for host in
                     policy.get('QUALITY_APPROVED_LINK_HOSTS', '').split(',') if host.strip())
        forbidden = {self.profile.get('domain', '').lower().rstrip('.')}
        for fact in self.profile.get('facts', []):
            if fact.get('source_url'):
                forbidden.add((urlsplit(fact['source_url']).hostname or '').lower())
        context = dict(simulation_only=True, scenario_id=self.scenario_id,
                       authorized_targets=[self.target_id], target_names={self.target_id:target['name']}, profile_facts=self.profile.get('facts',[]),
                       approved_sender_domains=sorted(senders), approved_link_hosts=sorted(links),
                       known_organisation_domains=sorted(forbidden - {''}), approved_sender_addresses=[])
        self.client = GuardedClient(self.client, context, enabled=self.quality_enabled)

    def _draft_checked(self, approach, sid, node_id, history, include_link):
        if not self.quality_enabled:
            return self._draft(approach, sid, node_id, history, include_link)
        prepared = generate_checked(
            lambda feedback: self._draft(approach, sid, node_id, history, include_link, feedback=feedback),
            self.client.context, max_attempts=3, validator=self.client.check_message,
            audit=lambda entry:self.qa_by_node.__setitem__(node_id, entry['report']))
        return as_shared_message(prepared)

    def _search(self, profile, sid, approaches, parent_id, ranked=()):
        silent = set()                       # channels a whole branch got no reaction on
        remaining = list(approaches)
        while remaining:
            approach = remaining.pop(0)
            if self.budget.exhausted():
                return False
            approach = _switch_channel(approach, ranked, silent)
            # everything learned earlier in this session travels with the next approach
            approach = dict(approach, session_lessons=list(self.lessons))
            seen, self._said = self.reactions, []
            self.budget.new_branch()
            node = self.add_node(
                "approach", "strategist",
                f"run approach: {approach.get('pretext')} -> {approach.get('incident_goal')}",
                f"score {approach.get('score')}, angle {approach.get('angle')}", parent_id,
                incident_chance=float(approach.get("score", 0.0)), status="active",
                evidence=list(approach.get("evidence", [])))   # which facts this approach rests on
            print(f"  >> approach: {approach.get('pretext')} via {approach.get('channel')} "
                  f"({approach.get('channel_reason', 'no channel reason')}; goal {approach.get('incident_goal')})")
            if self._run_branch(sid, approach, node):
                return True
            if self.reactions == seen:
                silent.add(approach.get("channel"))
            self.lessons.append(_lesson(approach, node, reacted=self.reactions > seen, said=self._said))
            print(f"  -- branch '{approach.get('pretext')}' stalled; pivoting\n")
            remaining = self._replan(remaining, node)
        return False

    def _replan(self, remaining, after_node):
        """after a failed approach, let the model reorder what is left using this session's lessons
        (who they ignored or refused, what they said about themselves). The rule-based order stays
        the fallback; the model only reorders, it cannot add approaches or skip the budget."""
        if not self.use_model or len(remaining) < 2 or not self.lessons:
            return remaining
        options = [{"i": i, "pretext": a.get("pretext"), "channel": a.get("channel"), "sender_kind": a.get("sender_kind"),
                    "story": a.get("story"), "topic": a.get("hook")} for i, a in enumerate(remaining[:8])]
        prompt = {"target": self._target_dict(), "lessons_from_this_session": self.lessons, "options": options,
                  "task": "Order the options so the next contact is the most likely to end in an incident (a sign-in, "
                          "an opened file, an action or internal information), given what failed and what the person "
                          "said. Avoid repeating a sender kind or channel they refused or ignored; follow any preference "
                          "they stated (a channel, links instead of files, a language); prefer their own topics. "
                          'Reply JSON only, "order" as a list of plain integers: {"order": [2, 0, 1], "why": "<one sentence>"}'}
        messages = [{"role": "system", "content": writer.SIMULATION_SYSTEM},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}]
        order, out, problems = [], {}, []
        try:
            cfg = self._cfg()
            models = (cfg.primary_model, cfg.fallback_model)
        except Exception as e:
            models, problems = (), [str(e)]
        for model in models:                 # the backup model gets a turn if the first answer is unreadable
            try:
                raw = _retry_model(lambda m=model: writer._completion(cfg, m, messages))
            except Exception as e:
                problems.append(f"{model}: {e}")
                continue
            out, order = _read_order(raw, len(options))
            if order:
                break
            problems.append(f"{model}: no readable order in {raw[:80]!r}")
        if not order:
            print(f"     replan unavailable ({'; '.join(problems)[:200]}); keeping the ranked order")
            return remaining
        if not order:
            return remaining
        rest = [a for i, a in enumerate(remaining) if i not in order]
        new = [remaining[i] for i in order] + rest
        why = str(out.get("why", ""))[:300]
        self.add_node("hook", "strategist", f"replan: next {new[0].get('pretext')} via {new[0].get('channel')}",
                      why, after_node.id, status="active")
        print(f"     replan: next {new[0].get('pretext')} via {new[0].get('channel')} ({why[:120]})")
        return new

    def _run_branch(self, sid, approach, approach_node):
        """run one approach: a live-call channel goes through the conversation api,
        any other channel through the message path."""
        self.client.story_scope = approach.get('story_id') or approach.get('pretext') or 'session'
        if approach.get("channel") in LIVE_CHANNELS:
            return self._run_call(sid, approach, approach_node)
        return self._run_messages(sid, approach, approach_node)

    def _run_messages(self, sid, approach, approach_node, seed=None):
        """messages on one approach until an incident, a stop, or the per-branch cap.
        plan_next_move stages the thread (introduce, build trust, then ask with the link),
        so a first cold contact has no login link. with the model writer each contact
        adapts to the reply; with compose a branch is one contact, since a repeat is the
        same message the api would dedup."""
        history = []
        parent = approach_node.id
        has_page = bool(writer.compose(self.profile, approach).get("landing_page"))
        turn = engaged = reassured = nudged = 0
        last_state, last_events, scepticism = "", [], None
        if seed:                                       # continuing a thread, e.g. the mail promised on a call
            history = list(seed["history"])
            turn, engaged, last_state, scepticism = 1, 1, "engaged", seed.get("scepticism")
            nudged = 1   # after a call: the promised mail and one nudge, not two (they only talked, never wrote)
        while not self.budget.exhausted():            # the session's total budget is the hard limit
            # pivot a cold branch after the per-branch cap, but stay on one that is engaging:
            # keep answering and pushing the ask while the target keeps replying
            if engaged == 0 and self.budget.branch_exhausted():
                return False
            turn += 1
            plan = strategy.plan_next_move(turn=turn, last_state=last_state,
                                           last_events=last_events, engaged_count=engaged,
                                           has_page=has_page, scepticism=scepticism,
                                           reassured=reassured, nudged=nudged)
            if plan.get("stop"):
                print(f"     stop branch: {plan.get('reason', '')}")
                return False
            if plan.get("intent") == "reassure":
                reassured += 1
            if plan.get("intent") == "nudge":
                nudged += 1
            # a page-based pretext (sign-in, document) carries its link from the start, since the
            # link is the lure; a relationship pretext stages it until the target engages
            include_link = (bool(plan.get("include_link")) or _is_lure_goal(approach.get("incident_goal"))
                            or (plan.get("intent") == "reassure" and has_page)   # doubt is met with something to check
                            or bool(history and has_page and re.search(r"\blinks?\b|\burl\b|\bpage\b", history[-1].get("reply", ""), re.I)))
            contact = self.add_node("contact", "writer",
                                    f"contact on {approach.get('pretext')} ({plan.get('intent', '')})",
                                    plan.get("reason", ""), parent, status="active")
            try:
                story_day = (self.story_base + timedelta(days=self.contact_count)).date().isoformat()
                step = dict(approach, next_move=plan.get("intent", ""), story_date=story_day)
                if plan.get("intent") == "make_ask" and approach.get("channel") == "email":
                    # the ask also carries the pretext's file: opening it is a one-click win (action)
                    step["attachment"] = step.get("attachment") or FOLLOW_UP_ATTACHMENTS.get(approach.get("pretext"))
                if history and _asks_for_material(history[-1].get("reply", "")):
                    # they asked for the agenda, articles, deck...: send it; opening it is the action incident
                    step["attachment"] = step.get("attachment") or _material_name(history[-1]["reply"], approach.get("pretext"))
                # what they refused in this thread is never sent again ("I don't open attachments")
                refused = _refused(" ".join(h.get("reply", "") for h in history))
                if "files" in refused:
                    step["attachment"] = None
                if "links" in refused:
                    include_link = False
                msg = self._draft_checked(step, sid, contact.id, history, include_link)
            except Exception as e:
                contact.status = "failed"
                contact.level = "attempt"
                self.qa_by_node.setdefault(contact.id, QualityReport(errors=["Writer failed before submission"]).to_dict())
                contact.outcome = f"writer failed: {e}"
                print(f"     writer failed: {e}")
                return False

            if history and _plain(msg.body) == history[-1]["message"]:
                # the api treats a word-for-word repeat as the same message: it would not count
                contact.status, contact.outcome = "failed", "draft repeats the last message word for word"
                print("     stop branch: draft repeats the last message")
                return False
            self.contact_count += 1
            sent_at = (self.story_base + timedelta(days=self.contact_count - 1)).isoformat()
            print(f"     -> [{msg.channel}] {msg.subject or msg.body[:48]}")

            try:
                result = self.client.send_message(msg, sent_at=sent_at)
                if not isinstance(result.get('message_id'), str) or not result['message_id'] or not isinstance(result.get('events'), list):
                    raise ValueError('No valid send acknowledgement; reconcile original request')
                self._check_contact_touches(result)
            except QualityBlocked as exc:
                self.qa_by_node[contact.id] = exc.report.to_dict()
                contact.level, contact.status, contact.outcome = 'attempt', 'failed', 'QA blocked before send; no contact'
                return False
            except Exception:
                contact.level, contact.status, contact.outcome = 'attempt', 'failed', 'Delivery uncertain; reconcile original key before retrying'
                raise
            self.qa_by_node[contact.id] = self.client.last_report
            self.budget.sync(result.get("touches_used", self.budget.used))
            self.budget.branch_used += 1
            events = result.get("events", [])
            self.messages.append(dict(msg.to_dict(), qa=self.client.last_report,
                                      message_id=result['message_id'], touches_used=result.get('touches_used')))
            self.events.setdefault(contact.id, []).extend(events)
            self.reactions += bool(events)
            reply = next((e.get("body", "") for e in events if e.get("type") == "reply"), "")
            if reply:
                self._said.append(reply)
            print(f"     <- {[e.get('type') for e in events] or ['ignored']}  "
                  f"({self.budget.used}/{self.budget.total} touches)")

            incident_type, incident_reason = classify_incident(events)
            if not incident_type and reply:            # a reply may disclose internal info
                incident_type, incident_reason = self._judge_disclosure(
                    reply, sent="\n\n".join(h["message"] for h in history) + "\n\n" + _plain(msg.body))
            verdict = strategy.evaluate_reaction(
                events, reply_text=reply,
                touches_used=self.budget.used, touch_budget=self.budget.total)
            state = "incident" if incident_type else verdict.get("state", "silent")
            reason = incident_reason or verdict.get("reason", "")
            # how doubtful the reply sounds decides whether the next message asks or reassures
            sc = strategy.assess_scepticism(reply, judge=self._judge_scepticism if self.use_model else None)
            scepticism = sc["score"]
            if scepticism is not None:
                reason = (reason.rstrip(". ") + ". " if reason else "") + f"Scepticism {scepticism}/10: {sc['reason']}"
                if scepticism >= strategy.SCEPTICISM_REASSURE_MIN and state == "engaged":
                    state = "suspicious"   # a polite but doubtful reply is not a green light
            contact.status = state
            contact.outcome = reason
            self.add_node("reaction", "evaluator", f"{state}: {verdict.get('recommended_action')}",
                          reason, contact.id, status=state,
                          incident_chance=1.0 if incident_type else 0.0)
            history.append({"message": _plain(msg.body), "events": events, "reply": reply})
            parent = contact.id
            last_state = state
            last_events = [e.get("type") for e in events]
            if state == "engaged":
                engaged += 1
            self._save_tree()                  # write the bundle after each contact, so the viewer can follow live

            if incident_type:
                print(f"     *** INCIDENT candidate ({incident_type}, our judge; revel8 confirms at scoring): {incident_reason} ***")
                return True
            if verdict.get("recommended_action") == "stop":
                return False
            if not self.use_model:
                return False                   # compose cannot vary a follow-up; pivot
        return False

    def _run_call(self, sid, approach, approach_node):
        """a live call: one touch for the whole call, up to 10 turns. cheap and fast, and
        well suited to a disclosure ask. writer.generate_call_line writes one line per turn."""
        if not self.budget.can_spend():
            return False
        approach = dict(approach, story_date=(self.story_base + timedelta(days=self.contact_count)).date().isoformat())
        comp = writer.compose(self.profile, approach)
        self._apply_persona(approach, comp)          # the caller is the same generated persona as on mail
        sender = {"name": comp["sender"]["name"], "address": comp["sender"]["address"]}
        caller = {k: comp["sender"][k] for k in ("name", "role", "organization") if comp["sender"].get(k)}
        self.contact_count += 1
        sent_at = (self.story_base + timedelta(days=self.contact_count - 1)).isoformat()
        contact = self.add_node("contact", "caller", f"call on {approach.get('pretext')}",
                                "", approach_node.id, status="active",
                                evidence=list(approach.get("evidence", [])))
        try:
            conv = self.client.start_conversation(sid, self.target_id, approach["channel"],
                                                  sender=sender, sent_at=sent_at, idem_key=str(uuid.uuid4()))
            self._check_contact_touches(conv)
        except Exception as e:
            contact.level = "attempt"
            if isinstance(e, QualityBlocked):
                self.qa_by_node[contact.id] = e.report.to_dict()
            contact.status = "failed"
            contact.outcome = f"call failed to start: {e}"
            print(f"     call failed to start: {e}")
            if not isinstance(e, QualityBlocked):
                raise
            return False
        self.qa_by_node[contact.id] = self.client.last_report
        self.budget.sync(conv.get("touches_used", self.budget.used))
        self.budget.branch_used += 1
        cid = conv.get("conversation_id")
        heard = conv.get("persona_says", "")
        print(f"     [call {approach['channel']}] persona: {heard[:60]}")
        transcript = [{"role": "them", "text": heard}] if heard else []
        self.reactions += bool(heard)
        # Persist the acknowledged contact before any further model/API work.
        # A later turn failure must not erase an already spent call touch.
        call_record = {
            'session_id':sid, 'channel':approach['channel'], 'to':self.target_id,
            'conversation_id':cid, 'touches_used':conv['touches_used'],
            'sender':sender, 'subject':'', 'node_id':contact.id,
            'qa':self.qa_by_node.get(contact.id),
            'body':'\n'.join(f"{t['role']}: {t['text']}" for t in transcript),
        }
        self.messages.append(call_record)
        self._save_tree()
        incident_type = incident_reason = None
        max_turns = 10
        closing = False                      # they declined or want it in writing: one closing line, then hang up
        for turn in range(1, max_turns + 1):
            try:
                def draft_line(feedback):
                    extra = [{'role':'quality-feedback','text':json.dumps(feedback)}] if feedback else []
                    if closing:
                        extra.append({'role': 'instruction', 'text': 'They declined or asked for it in writing. '
                                      'Thank them, confirm in one sentence what you will send today, and end the call. No questions.'})
                    gen = _retry_model(lambda: writer.generate_call_line(
                        self._cfg(), target=self._target_dict(), approach=approach,
                        sender=caller, verified_facts=self.profile.get('facts', []),
                        transcript=transcript + extra, turn_number=turn, max_turns=max_turns))
                    return {'say':(gen.get('content') or {}).get('body','')}
                if self.quality_enabled:
                    line = generate_checked_turn(draft_line, self.client.context, max_attempts=3,
                        validator=lambda data:self.client.check_turn(cid,data['say'],sid=sid))['say']
                else:
                    line = draft_line(None)['say']
            except Exception as e:
                self.qa_by_node[contact.id]['warnings'].append('Call line not submitted: ' + str(e))
                print(f'     call-line failed: {e}')
                break
            if not line:
                break
            try:
                turn_r = self.client.say(cid, line, sid=sid, idem_key=str(uuid.uuid4()))
            except Exception as e:
                contact.status = "failed"
                contact.outcome = "Call-turn delivery uncertain; reconcile before another approach"
                print(f"     say failed: {e}")
                raise
            heard = turn_r.get("persona_says", "")
            events = turn_r.get("events", [])
            self.events.setdefault(contact.id, []).extend(events)
            if heard:
                self._said.append(heard)
            transcript.append({"role": "us", "text": line})
            transcript.append({"role": "them", "text": heard})
            call_record['body'] = '\n'.join(f"{t['role']}: {t['text']}" for t in transcript)
            self._save_tree()
            print(f"     you: {line[:48]} | persona: {heard[:48]}")
            incident_type, incident_reason = classify_incident(events)
            if not incident_type and heard:            # the persona may disclose internal info on the call
                incident_type, incident_reason = self._judge_disclosure(heard, sent=(
                    f"Caller: {sender['name']} <{sender['address']}>\n"
                    + "\n".join(t["text"] for t in transcript if t["role"] == "us")))
            if incident_type or turn_r.get("ended") or closing:
                break
            # stop probing once they decline or ask for writing: pushing on raises their guard for the
            # rest of the session; the follow-up mail carries the thread instead
            closing = _wants_out(heard)
        try:
            self.client.end_conversation(cid)
        except Exception:
            pass
        state = "incident" if incident_type else "engaged"
        contact.status = state
        contact.outcome = incident_reason or f"call ended, {len(transcript)} lines"
        self.add_node("reaction", "evaluator", f"call {state}",
                      incident_reason or "call ended", contact.id, status=state,
                      incident_chance=1.0 if incident_type else 0.0)
        self._save_tree()
        if incident_type:
            print(f"     *** INCIDENT candidate ({incident_type}, our judge; revel8 confirms at scoring): {incident_reason} ***")
            return True
        said = [t["text"] for t in transcript[1:] if t["role"] == "them" and t["text"]]
        if said and not self.budget.exhausted():
            # they talked to us: send the material the call promised, in the same thread, instead of pivoting
            return self._follow_up_call(sid, approach, contact, transcript)
        return False

    def _follow_up_call(self, sid, approach, contact, transcript):
        """the email a call ends with ("send it by mail"): same sender, the call as history,
        engaged state, and the promised material attached so opening it is the action."""
        print("     call engaged; sending the follow-up mail the call agreed on")
        # an outsider follows up by email; a colleague, IT or vendor by SMS, which shows a name and number
        # rather than a lookalike domain a careful target checks ("our systems run on our own domain")
        insider = approach.get("sender_kind") in ("colleague", "vendor")
        follow = dict(approach, channel="sms" if insider else "email",
                      attachment=None if insider else FOLLOW_UP_ATTACHMENTS.get(approach.get("pretext")))
        ours = " ".join(t["text"] for t in transcript if t["role"] == "us")
        theirs = " ".join(t["text"] for t in transcript if t["role"] == "them")
        last = next((t["text"] for t in reversed(transcript) if t["role"] == "them" and t["text"]), "")
        # their final stance decides, not the whole call (curt at first, "send it by mail" at the end)
        sc = strategy.assess_scepticism(last, judge=self._judge_scepticism if self.use_model else None)
        score = sc["score"]
        if re.search(r"\b(mail|e-mail|email|schick|send)\w*", last, re.I):
            # they asked for the mail: the promised mail always goes out, then their reply decides
            score = min(score if score is not None else 0, strategy.SCEPTICISM_ASK_MAX)
        seed = {"history": [{"message": f"(phone call) {ours}", "events": [], "reply": theirs}],
                "scepticism": score}
        return self._run_messages(sid, follow, contact, seed=seed)

    def _check_contact_touches(self, response):
        used = response.get('touches_used')
        if type(used) is not int or used <= self.budget.used:
            raise ValueError('Missing or non-increasing API touch count; delivery may have occurred, reconcile before another send')

    def _draft(self, approach, sid, node_id, history, include_link, feedback=None):
        """build the next message: a persuasive, adaptive body from the model writer, with
        writer.compose (deterministic, no model) as the fallback. the landing link is added
        and the page registered only when plan_next_move stages the ask (include_link)."""
        comp = writer.compose(self.profile, approach)
        self._apply_persona(approach, comp)
        landing = comp.get("landing_page")
        model_ok = False
        if self.use_model:
            try:
                content = _retry_model(lambda: self._model_body(approach, comp, history,
                    feedback=feedback, link_follows=bool(include_link and landing)))
                comp["subject"] = content.get("subject") or comp.get("subject", "")
                comp["body"] = content.get("body") or comp["body"]
                model_ok = True
            except Exception as e:
                print(f"     model writer unavailable ({e}); using compose")
        if model_ok:
            link = landing if (include_link and landing) else None
            comp["landing_page"] = link        # withhold the page until the ask is staged
            if comp.get("channel") == "email" and approach.get("sender_kind") == "vendor":
                # a tool's notice comes as a branded mail; a person writing as themselves stays plain text
                comp["body"] = writer.render_mail_html(body=comp["body"], organization=_org_of(comp), link=link,
                                                       logo_src=self._logo_src(_org_of(comp)))
            elif link:
                comp["body"] += f"\n\n{link.get('title', 'Sign in')}: {link['url']}"
        if comp.get("landing_page"):
            lp = comp["landing_page"]
            lp["html"], lp["text"] = writer.render_landing_html(
                pretext=approach.get("pretext", ""), organization=_org_of(comp),
                title=lp.get("title", "Sign in"), fields=lp.get("fields", []),
                logo_src=self._logo_src(_org_of(comp)), german=urlsplit(lp["url"]).hostname.endswith(".de") or str(self.profile.get("country", "")).upper() in ("DE", "GERMANY"))
        return _message_from_compose(comp, sid, self.target_id, node_id)

    def _apply_persona(self, approach, comp):
        """swap the fixed fallback sender for one generated to fit this approach's story and
        kind of sender (outsider, vendor, colleague), cached per approach so follow-ups keep the
        same identity. any landing page moves onto the persona's domain, so sender and link
        belong together."""
        if not self.use_model:
            return
        key = (approach.get("pretext"), approach.get("hook"))   # same sender across channels (call, then its mail)
        if key not in self._personas:
            try:
                self._personas[key] = writer.generate_sender_persona(
                    self._cfg(), target={**self._target_dict(), "company_domain": self.profile.get("domain", "")},
                    approach=approach, facts=self.profile.get("facts", []),
                    # a known coworker fits a favour, a meeting or a shared file; IT and HR staff are invented
                    colleague=(writer._first_colleague(self.profile)
                               if approach.get("pretext") not in ("it_helpdesk", "hr_policy") else ""),
                    avoid_names=[q["name"] for q in self._personas.values() if q],
                    tool=(writer.detect_vendor(approach.get("pretext", ""), writer._tool_vectors(self.profile)) or {}).get("brand", ""))
                p = self._personas[key]
                print(f"     sender: {p['name']}, {p['role']} at {p['organization']} <{p['address']}>")
            except Exception as e:
                print(f"     sender persona unavailable ({e}); using the default sender")
                self._personas[key] = None
        persona = self._personas[key]
        if not persona:
            return
        if self.quality_enabled:
            context = self.client.context
            host = str(persona.get('domain', '')).lower().rstrip('.')
            forbidden = context.get('known_organisation_domains', [])
            # the model never approves its own domain: DNS does. A domain nobody has registered
            # (NXDOMAIN) cannot be any organisation's own, so it is approved; anything else is not.
            if any(host == own or host.endswith('.' + own) for own in forbidden) or writer.domain_taken(host) is not False:
                print('     generated sender domain is not provably unregistered; retaining the checked playbook sender')
                return
            for key in ('approved_sender_domains', 'approved_link_hosts'):
                if host not in context[key]:
                    context[key].append(host)
        comp["sender"] = {"name": persona["name"], "address": persona["address"],
                          "role": persona["role"], "organization": persona["organization"]}
        landing = comp.get("landing_page")
        if landing and landing.get("url"):
            path = "/" + landing["url"].split("://", 1)[-1].partition("/")[2]
            host = f"{landing['sub']}.{persona['domain']}" if landing.get("sub") else persona["domain"]
            landing["url"] = f"https://{host}{path}"
            landing["domain"] = persona["domain"]
            if self.quality_enabled and host not in self.client.context["approved_link_hosts"]:
                self.client.context["approved_link_hosts"].append(host)   # a subdomain of the DNS-checked domain

    def _logo_src(self, organization):
        """asset://… of the real logo when the sender is a known brand, uploaded once per api
        and reused; "" for an invented organisation or if the upload fails (then a text wordmark)."""
        brand = writer.brand_of(organization)
        if not brand:
            return ""
        from .revel8 import BASE
        key = f"{BASE}|{writer.BRAND_STYLE[brand][0]}"
        try:
            cache = json.loads(ASSET_CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        if key not in cache:
            try:
                raw = getattr(self.client, "client", self.client).upload_asset(writer.LOGO_DIR / writer.BRAND_STYLE[brand][0])
                cache[key] = raw["asset_id"]
                ASSET_CACHE.parent.mkdir(parents=True, exist_ok=True)
                ASSET_CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
            except Exception as e:
                print(f"     logo upload failed for {brand} ({e}); using a text wordmark")
                return ""
        return f"asset://{cache[key]}"

    def _cfg(self):
        key = config.load_env().get("RADEON_API_KEY")
        if not key:
            raise RuntimeError("no RADEON_API_KEY")
        return writer.ModelConfig(api_key=key, primary_model=PRIMARY_MODEL, fallback_model=FALLBACK_MODEL)

    def _target_dict(self):
        return {k: self.profile.get(k) for k in ("name", "role", "company", "country") if self.profile.get(k)}

    def _model_body(self, approach, comp, history, feedback=None, link_follows=False):
        sender = {"name": comp["sender"]["name"], "email": comp["sender"]["address"],
                  "role": comp["sender"].get("role", ""), "organization": comp["sender"].get("organization", "")}
        conv = []
        for h in history:
            conv.append({"from": comp["sender"]["name"], "text": h.get("message", "")})
            if h.get("reply"):
                conv.append({"from": self.profile.get("name", "them"), "text": h["reply"]})
        if feedback:
            conv.append({'from':'quality-feedback', 'text':json.dumps(feedback)})
        gen = writer.generate_message(
            self._cfg(), target=self._target_dict(), approach=approach, sender=sender,
            verified_facts=self.profile.get("facts", []), conversation_history=conv,
            attachment=comp.get("attachment"), link_follows=link_follows)
        return gen.get("content", {})

    def _judge_scepticism(self, text):
        """rate how doubtful a reply sounds, 0-10, with one line of reason. uses the writer's
        fast settings (no thinking, Gemma as backup), so it adds seconds, not a minute."""
        system = (
            "You read one reply a person sent inside an authorised revel8 security-awareness "
            "simulation and rate how sceptical they are of the sender, from 0 (trusting, keen) to "
            "10 (refusing, calls it a scam). Doubt shows as asking for proof or an official "
            "address, pointing out contradictions, insisting on verifying elsewhere, or refusing "
            "to open things. People often stay polite while doubting: hedging, staying vague, "
            "moving the conversation to another channel or a meeting, or not answering what was "
            "asked all mean real doubt, even in a friendly tone. Trust shows as concrete answers, "
            "sharing details, agreeing to the request, practical next-step questions. "
            'Reply JSON only: {"score": <0-10>, "reason": "<one short line>"}.'
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": text[:1500]}]
        cfg = self._cfg()
        for model in (cfg.primary_model, cfg.fallback_model):
            try:
                out = _json_from(writer._completion(cfg, model, messages))
                if "score" in out:
                    return out
            except Exception:
                continue
        raise RuntimeError("scepticism judge unavailable")

    def _judge_disclosure(self, text, sent=""):
        """an llm judge: does this reply reveal INTERNAL, non-public information (a disclosure
        win)? strict, since the jury confirms every win and a false claim scores nothing. it
        must name each internal detail; public facts, what we told them, and vague talk do
        not count. returns ("disclosure", plain-language summary) or (None, "")."""
        text = (text or "").strip()
        if len(text) < 40:                 # too short to carry internal detail
            return None, ""
        public = [f.get("value", "")[:160] for f in self.profile.get("facts", []) if f.get("value")][:60]   # all of it: DNS tools are public too
        who = (self.profile.get("name") or "The target").split()[0]
        system = (
            "You review one reply a person sent inside an authorised revel8 security-awareness "
            "simulation. Decide whether it reveals INTERNAL information about their company that an "
            "outsider could not know: a named system or tool they use internally, an internal process "
            "or approval rule, a number (budget, cost, headcount), an internal plan or a colleague's "
            "responsibility. These do NOT count: anything in the public facts, anything the sender's "
            "own message already said, opinions, vague statements (\"costs are high\"), questions, "
            "pleasantries or refusals, corrections of the sender ('you are not from our IT', 'X is our CEO'), "
            "the public roles of founders and executives, and generic product features anyone could name (an admin console, "
            "MFA, single sign-on, 'our IT team') unless they reveal how their company configured or uses them. "
            "Be strict: when unsure, it is not a disclosure. "
            'Reply JSON only: {"disclosure": true|false, "details": ["<each internal detail, one short '
            'phrase>"], "why": "<one sentence: why these are not public>"}.'
        )
        user = ("Public facts (repeating these is not disclosure):\n- " + "\n- ".join(public)
                + "\n\nWhat the sender already told them (including the sender's own name, organisation and "
                  "email domain, which are never the target's internal information):\n" + (sent or "(nothing)")[:1500]
                + "\n\nTheir reply:\n" + text[:1500])
        try:                               # the same amd model the writer uses; no OpenAI dependency
            cfg = self._cfg()
            raw = _retry_model(lambda: writer._completion(
                cfg, cfg.primary_model,
                [{"role": "system", "content": system}, {"role": "user", "content": user}]))
            out = _json_from(raw)
        except Exception:
            return None, ""                # if the judge is unavailable, do not claim a win
        details = [str(d).strip() for d in out.get("details") or [] if str(d).strip()]
        if out.get("disclosure") is True and details:
            summary = f"{who} revealed internal details: " + "; ".join(details)
            if out.get("why"):
                summary += f". {str(out['why']).strip()}"
            return "disclosure", summary[:400]
        return None, ""

    def _save_tree(self):
        """write the run bundle the replay viewer reads (runs/<run_id>.json), and keep the
        bare node list under runs/trees/ for anything that reads just the tree."""
        nodes = [dict(n.to_dict(), **({'qa':self.qa_by_node[n.id]} if n.id in self.qa_by_node else {})) for n in self.nodes]
        bundle = {
            "run_id": self.run_id,
            "run_status": getattr(self, 'run_status', 'recorded'),
            "abort_reason": getattr(self, 'abort_reason', None),
            "mode": self.scenario_id,
            "profile": self.profile,
            "nodes": nodes,
            "messages": self.messages,
            "events": self.events,
        }
        RUNS.mkdir(parents=True, exist_ok=True)
        (RUNS / f"{self.run_id}.json").write_text(json.dumps(bundle, indent=2))
        TREE_DIR.mkdir(parents=True, exist_ok=True)
        (TREE_DIR / f"{self.run_id}.json").write_text(json.dumps([n.to_dict() for n in self.nodes], indent=2))


def _rejected_options(approach):
    """turn strategy's rejected_alternatives into schemas.RejectedOption for the tree."""
    out = []
    for r in approach.get("rejected_alternatives", [])[:8]:
        label = f"{r.get('pretext', '')}/{r.get('channel', '')}".strip("/")
        out.append(schemas.RejectedOption(label or r.get("hook", "option"), r.get("reason", "")))
    return out


def main():
    args = sys.argv[1:]
    eval_mode = "--eval" in args
    use_model = "--compose" not in args      # model writer by default; --compose for a deterministic run
    use_mock = "--mock" in args              # live recon by default; --mock for a fast cached profile
    targets = [a for a in args if not a.startswith("--")]
    target = targets[0] if targets else "julius"
    orch = Orchestrator(target, eval_mode=eval_mode, use_model=use_model, use_mock=use_mock)
    orch.run()
    if getattr(orch, 'run_status', None) == 'aborted':
        sys.exit('Aborted before sending: ' + orch.abort_reason)


if __name__ == "__main__":
    main()
