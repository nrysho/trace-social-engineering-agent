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
from . import llm
from .budget import TouchBudget
from .revel8 import Revel8Client
from quality.guarded_client import GuardedClient
from quality.integration import generate_checked, generate_checked_turn, as_shared_message, QualityBlocked
from quality.checks import QualityReport


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
PROFILE_DIRS = [RUNS / "profiles", ROOT / "mock"]

EVAL_BUDGET = 10
PRACTICE_BUDGET = 30
PER_BRANCH = 3                             # cap one approach before pivoting
MAX_APPROACHES_EVAL = 3                    # with only 10 touches, go deep on a few, do not spray
MAX_APPROACHES_PRACTICE = 6
DEFAULT_COMPANY = "revel8"

# live channels need the conversation api (start_conversation + call script), not send_message.
# the message path below skips them for now; wiring calls is a follow-up.
LIVE_CHANNELS = {"phone_call", "video_call", "teams_call", "live_chat"}

# field names that make a submitted form a win, from the docs' Forms section.
# page.submitted carries `fields` (list of filled field names) and `values` ({name: value},
# a secret shown only as "(entered, not shown)"); an empty field is in neither.
SECRET_MARKER = "(entered, not shown)"
CREDENTIAL_FIELDS = {"password", "pin", "otp", "verification_code", "token",
                     "api_key", "card_number", "iban"}
DISCLOSURE_FIELDS = {"vpn_client", "approver", "internal_tool"}
# substring fallback, so a page that names a secret field slightly differently still counts
SECRET_HINTS = ("password", "passcode", "passwd", "otp", "one-time", "onetime", "2fa",
                "mfa", "totp", "pin", "verification", "security code", "auth code",
                "token", "secret", "api key", "card number", "iban")


def _now():
    return datetime.now(timezone.utc).isoformat()


# ----- incident rule (docs' Forms section): a form wins only on a secret or internal field -----

def _filled(event):
    """field names the person filled in, plus the {name: value} dict, from a page.submitted."""
    names = set()
    for f in event.get("fields", []) or []:
        names.add(f.get("name", "") if isinstance(f, dict) else str(f))
    values = event.get("values", {})
    values = values if isinstance(values, dict) else {}
    names.update(str(k) for k in values)
    return {str(n).strip().casefold() for n in names if n}, values


def _is_secret(name):
    return name in CREDENTIAL_FIELDS or any(hint in name for hint in SECRET_HINTS)


def classify_incident(events):
    """return (incident_type, reason) or (None, "").
    a submitted secret is credentials, an internal field is disclosure, an opened
    attachment is an action; name/email alone is only a step, not a win."""
    for e in events:
        if str(e.get("type")) != "page.submitted":
            continue
        names, values = _filled(e)
        if any(str(v) == SECRET_MARKER for v in values.values()) or any(_is_secret(n) for n in names):
            return "credentials", "secret field submitted"
        if names & DISCLOSURE_FIELDS:
            return "disclosure", "internal field submitted"
    for e in events:
        if str(e.get("type")) == "attachment.opened":
            return "action", f"attachment opened: {e.get('filename', '')}"
    return None, ""


# ----- adapt writer.compose output into a schemas.Message the client can send -----

def _message_from_compose(comp, sid, target_id, node_id):
    lp = comp.get("landing_page")
    landing = None
    if lp:
        landing = schemas.LandingPage(
            url=lp["url"], title=lp.get("title", "Sign in"),
            fields=lp.get("fields", []), text="Please sign in to continue.",
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


def load_profile(target_id, name, company, use_mock=False):
    """a cached recon profile if one exists, else live recon. mock only with use_mock,
    since a mock is target-specific and would be wrong for a hidden eval target.
    recon writes runs/profiles/<name-slug>.json, so check that and the target id."""
    prof_dir = RUNS / "profiles"
    for cached in (prof_dir / f"{target_id}.json", prof_dir / f"{_slug(name)}.json"):
        if cached.exists():
            prof = json.loads(cached.read_text(encoding="utf-8"))
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
    def __init__(self, target_id, eval_mode=False, use_model=True, use_mock=False):
        self.scenario_id = 'eval' if eval_mode else 'practice'
        self.quality_enabled = os.environ.get('QUALITY_GATE', 'on').lower() != 'off'
        if eval_mode and not self.quality_enabled:
            raise ValueError('QUALITY_GATE=off is allowed in practice only')
        self.client = Revel8Client()
        self.qa_by_node = {}
        self.target_id = target_id
        self.run_id = f"run_{target_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.budget = TouchBudget(EVAL_BUDGET if eval_mode else PRACTICE_BUDGET, PER_BRANCH)
        self.eval_mode = eval_mode
        self.use_model = use_model           # model writer (persuasive, adaptive); compose is the fallback
        self.use_mock = use_mock             # use mock/profile.json instead of live recon (fast tests)
        self.max_approaches = MAX_APPROACHES_EVAL if eval_mode else MAX_APPROACHES_PRACTICE
        self.nodes = []
        self.profile = {}
        self.messages = []                   # sent messages, for the replay viewer bundle
        self.events = []                     # reactions, for the replay viewer bundle
        self.contact_count = 0               # drives sent_at pacing
        self.story_base = datetime.now(timezone.utc)

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
        self.profile = profile
        target_node = self.add_node("target", "recon", f"target {profile.get('name')}",
                                    target.get("role", ""), None, status="active")

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

        session = self.client.create_session(self.scenario_id)
        sid = session["session_id"]
        self.budget.total = min(self.budget.total, session["touch_budget"])
        self.budget.sync(session["touches_used"])
        print(f"  session {sid}  ·  budget {self.budget.remaining} touches\n")

        try:
            if not self._search(profile, sid, approaches, hook_node.id):
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
        return dict(targets[0], company=targets[0].get('company', DEFAULT_COMPANY))

    def _configure_quality(self, approaches, target):
        # Domain approvals come from the deterministic playbook, never model prose.
        senders, links = set(), set()
        for approach in approaches:
            comp = writer.compose(self.profile, approach)
            senders.add(comp['sender']['address'].rsplit('@', 1)[-1].lower())
            if comp.get('landing_page'):
                links.add(urlsplit(comp['landing_page']['url']).hostname)
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

    def _search(self, profile, sid, approaches, parent_id):
        for approach in approaches:
            if self.budget.exhausted():
                return False
            self.budget.new_branch()
            node = self.add_node(
                "approach", "strategist",
                f"run approach: {approach.get('pretext')} -> {approach.get('incident_goal')}",
                f"score {approach.get('score')}, angle {approach.get('angle')}", parent_id,
                incident_chance=float(approach.get("score", 0.0)), status="active",
                evidence=list(approach.get("evidence", [])))   # which facts this approach rests on
            print(f"  >> approach: {approach.get('pretext')} (goal {approach.get('incident_goal')})")
            if self._run_branch(sid, approach, node):
                return True
            print(f"  -- branch '{approach.get('pretext')}' stalled; pivoting\n")
        return False

    def _run_branch(self, sid, approach, approach_node):
        """run one approach: a live-call channel goes through the conversation api,
        any other channel through the message path."""
        self.client.story_scope = approach.get('story_id') or approach.get('pretext') or 'session'
        if approach.get("channel") in LIVE_CHANNELS:
            return self._run_call(sid, approach, approach_node)
        return self._run_messages(sid, approach, approach_node)

    def _run_messages(self, sid, approach, approach_node):
        """messages on one approach until an incident, a stop, or the per-branch cap.
        plan_next_move stages the thread (introduce, build trust, then ask with the link),
        so a first cold contact has no login link. with the model writer each contact
        adapts to the reply; with compose a branch is one contact, since a repeat is the
        same message the api would dedup."""
        history = []
        parent = approach_node.id
        has_page = bool(writer.compose(self.profile, approach).get("landing_page"))
        turn = engaged = 0
        last_state, last_events = "", []
        while self.budget.can_spend() and not self.budget.branch_exhausted():
            turn += 1
            plan = strategy.plan_next_move(turn=turn, last_state=last_state,
                                           last_events=last_events, engaged_count=engaged,
                                           has_page=has_page)
            if plan.get("stop"):
                return False
            # a page-based pretext (sign-in, document) carries its link from the start, since the
            # link is the lure; a relationship pretext stages it until the target engages
            include_link = bool(plan.get("include_link")) or _is_lure_goal(approach.get("incident_goal"))
            contact = self.add_node("contact", "writer",
                                    f"contact on {approach.get('pretext')} ({plan.get('intent', '')})",
                                    "", parent, status="active")
            try:
                msg = self._draft_checked(approach, sid, contact.id, history, include_link)
            except Exception as e:
                contact.status = "failed"
                contact.level = "attempt"
                self.qa_by_node.setdefault(contact.id, QualityReport(errors=["Writer failed before submission"]).to_dict())
                contact.outcome = f"writer failed: {e}"
                print(f"     writer failed: {e}")
                return False

            self.contact_count += 1
            sent_at = (self.story_base + timedelta(days=self.contact_count - 1)).isoformat()
            print(f"     -> [{msg.channel}] {msg.subject or msg.body[:48]}")

            try:
                result = self.client.send_message(msg, sent_at=sent_at)
                if not isinstance(result.get('message_id'), str) or not result['message_id'] or not isinstance(result.get('events'), list):
                    raise ValueError('No valid send acknowledgement; reconcile original request')
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
            self.messages.append(dict(msg.to_dict(), qa=self.client.last_report))            # for the replay bundle
            self.events.extend(events)
            reply = next((e.get("body", "") for e in events if e.get("type") == "reply"), "")
            print(f"     <- {[e.get('type') for e in events] or ['ignored']}  "
                  f"({self.budget.used}/{self.budget.total} touches)")

            incident_type, incident_reason = classify_incident(events)
            if not incident_type and reply:            # a reply may disclose internal info
                incident_type, incident_reason = self._judge_disclosure(reply)
            verdict = strategy.evaluate_reaction(
                events, reply_text=reply,
                touches_used=self.budget.used, touch_budget=self.budget.total)
            state = "incident" if incident_type else verdict.get("state", "silent")
            reason = incident_reason or verdict.get("reason", "")
            contact.status = state
            contact.outcome = reason
            self.add_node("reaction", "evaluator", f"{state}: {verdict.get('recommended_action')}",
                          reason, contact.id, status=state,
                          incident_chance=1.0 if incident_type else 0.0)
            history.append({"message": msg.body, "events": events, "reply": reply})
            parent = contact.id
            last_state = state
            last_events = [e.get("type") for e in events]
            if state == "engaged":
                engaged += 1
            self._save_tree()                  # write the bundle after each contact, so the viewer can follow live

            if incident_type:
                print(f"     *** INCIDENT ({incident_type}): {incident_reason} ***")
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
        comp = writer.compose(self.profile, approach)
        sender = {"name": comp["sender"]["name"], "address": comp["sender"]["address"]}
        self.contact_count += 1
        sent_at = (self.story_base + timedelta(days=self.contact_count - 1)).isoformat()
        contact = self.add_node("contact", "caller", f"call on {approach.get('pretext')}",
                                "", approach_node.id, status="active",
                                evidence=list(approach.get("evidence", [])))
        try:
            conv = self.client.start_conversation(sid, self.target_id, approach["channel"],
                                                  sender=sender, sent_at=sent_at, idem_key=str(uuid.uuid4()))
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
        incident_type = incident_reason = None
        max_turns = 10
        for turn in range(1, max_turns + 1):
            try:
                def draft_line(feedback):
                    extra = [{'role':'quality-feedback','text':json.dumps(feedback)}] if feedback else []
                    gen = _retry_model(lambda: writer.generate_call_line(
                        self._cfg(), target=self._target_dict(), approach=approach,
                        sender={'name':sender['name']}, verified_facts=self.profile.get('facts', []),
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
            self.events.extend(events)
            transcript.append({"role": "us", "text": line})
            transcript.append({"role": "them", "text": heard})
            print(f"     you: {line[:48]} | persona: {heard[:48]}")
            incident_type, incident_reason = classify_incident(events)
            if not incident_type and heard:            # the persona may disclose internal info on the call
                incident_type, incident_reason = self._judge_disclosure(heard)
            if incident_type or turn_r.get("ended"):
                break
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
        self.messages.append({
            "session_id": sid, "channel": approach["channel"], "to": self.target_id,
            "sender": sender, "subject": "", "node_id": contact.id, "qa": self.qa_by_node.get(contact.id),
            "body": "\n".join(f"{t['role']}: {t['text']}" for t in transcript),
        })
        self._save_tree()
        if incident_type:
            print(f"     *** INCIDENT ({incident_type}): {incident_reason} ***")
        return bool(incident_type)

    def _draft(self, approach, sid, node_id, history, include_link, feedback=None):
        """build the next message: a persuasive, adaptive body from the model writer, with
        writer.compose (deterministic, no model) as the fallback. the landing link is added
        and the page registered only when plan_next_move stages the ask (include_link)."""
        comp = writer.compose(self.profile, approach)
        landing = comp.get("landing_page")
        model_ok = False
        if self.use_model:
            try:
                content = _retry_model(lambda: self._model_body(approach, comp, history, feedback=feedback))
                comp["subject"] = content.get("subject") or comp.get("subject", "")
                comp["body"] = content.get("body") or comp["body"]
                model_ok = True
            except Exception as e:
                print(f"     model writer unavailable ({e}); using compose")
        if model_ok:
            if include_link and landing:
                comp["body"] += f"\n\n{landing.get('title', 'Sign in')}: {landing['url']}"
                comp["landing_page"] = landing
            else:
                comp["landing_page"] = None    # withhold the page until the ask is staged
        return _message_from_compose(comp, sid, self.target_id, node_id)

    def _cfg(self):
        key = config.load_env().get("RADEON_API_KEY")
        if not key:
            raise RuntimeError("no RADEON_API_KEY")
        return writer.ModelConfig(api_key=key, fallback_model=writer.PRIMARY_MODEL)

    def _target_dict(self):
        return {k: self.profile.get(k) for k in ("name", "role", "company") if self.profile.get(k)}

    def _model_body(self, approach, comp, history, feedback=None):
        sender = {"name": comp["sender"]["name"], "email": comp["sender"]["address"]}
        conv = []
        for h in history:
            conv.append({"from": comp["sender"]["name"], "text": h.get("message", "")})
            if h.get("reply"):
                conv.append({"from": self.profile.get("name", "them"), "text": h["reply"]})
        if feedback:
            conv.append({'from':'quality-feedback', 'text':json.dumps(feedback)})
        gen = writer.generate_message(
            self._cfg(), target=self._target_dict(), approach=approach, sender=sender,
            verified_facts=self.profile.get("facts", []), conversation_history=conv)
        return gen.get("content", {})

    def _judge_disclosure(self, text):
        """an llm judge: does this reply or spoken line reveal internal, non-public info
        (a disclosure win)? deliberately strict, since a false claim is worse than a miss
        and the jury confirms every win. returns ("disclosure", what) or (None, "")."""
        text = (text or "").strip()
        if len(text) < 40:                 # too short to carry internal detail
            return None, ""
        public = [f.get("value", "") for f in self.profile.get("facts", []) if f.get("verified")][:8]
        system = (
            "You review one message a target sent inside an authorised revel8 red-team "
            "simulation. Decide only whether it reveals INTERNAL, NON-PUBLIC information about "
            "their company: a system, tool, process, plan, internal name, number or credential "
            "that an outsider could not find on the public web. Pleasantries, public facts, a "
            "question, or a refusal are not disclosure. Be strict. "
            'Reply JSON only: {"disclosure": true|false, "info": "<one line>"}.'
        )
        user = ("Already-public facts (repeating these is not disclosure):\n- "
                + "\n- ".join(public) + "\n\nTheir message:\n" + text[:1500])
        try:
            out = _json_from(llm.chat([{"role": "system", "content": system},
                                       {"role": "user", "content": user}]))
        except Exception:
            return None, ""                # if the judge is unavailable, do not claim a win
        if out.get("disclosure") is True:
            return "disclosure", (out.get("info") or "internal info disclosed")[:200]
        return None, ""

    def _save_tree(self):
        """write the run bundle the replay viewer reads (runs/<run_id>.json), and keep the
        bare node list under runs/trees/ for anything that reads just the tree."""
        nodes = [dict(n.to_dict(), **({'qa':self.qa_by_node[n.id]} if n.id in self.qa_by_node else {})) for n in self.nodes]
        bundle = {
            "run_id": self.run_id,
            "mode": "eval" if self.eval_mode else "practice",
            "profile": self.profile,
            "nodes": nodes,
            "messages": self.messages,
            "events": self.events,
        }
        RUNS.mkdir(parents=True, exist_ok=True)
        (RUNS / f"{self.run_id}.json").write_text(json.dumps(bundle, indent=2))
        TREE_DIR.mkdir(parents=True, exist_ok=True)
        (TREE_DIR / f"{self.run_id}.json").write_text(json.dumps(nodes, indent=2))


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
    Orchestrator(target, eval_mode=eval_mode, use_model=use_model, use_mock=use_mock).run()


if __name__ == "__main__":
    main()
