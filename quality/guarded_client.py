"""Actual pre-send boundary; QA stays out of simulator payloads."""
from copy import deepcopy
import re
from html import unescape
from urllib.parse import urlsplit
from uuid import uuid4
from pathlib import Path
import json
from .checks import QualityReport, Markup
from .story import StoryLedger, profile_claim_checks
from .integration import (checked_message, checked_turn, prepare_page,
                          inspect_artifact, QualityBlocked, validate_context, plain, as_shared_message)

LIVE_CHANNELS = {'phone_call', 'video_call', 'teams_call', 'live_chat'}


def linked_urls(text):
    parser = Markup(); parser.feed(text); parser.close()
    return set(unescape(url) for url in re.findall(r'https?://[^\s<>"\x27)]+', text) + parser.links
               if not url.startswith('#') and not re.fullmatch(r'asset://a_[A-Za-z0-9_-]+', url))  # uploaded images are not links


class GuardedClient:
    @classmethod
    def from_current_practice(cls, client, context, **kwargs):
        from .identity import context_from_practice
        return cls(client, context_from_practice(client.scenarios(),context), **kwargs)

    def __init__(self, client, context, *, session_ids=(), audit=None, enabled=True, conversation_sessions=None):
        validate_context(context)
        self.scenario_id = context.get('scenario_id', 'practice')
        if self.scenario_id not in {'practice', 'eval'} or (self.scenario_id == 'eval' and not enabled):
            raise ValueError('Eval requires the quality gate enabled')
        self.client, self.context = client, deepcopy(context)
        self.sessions, self.conversations, self.registered = set(session_ids), {}, {}
        self.conversations = dict(conversation_sessions or {})
        if any(not isinstance(cid,str) or not cid or sid not in self.sessions for cid,sid in self.conversations.items()):
            raise ValueError('Resumed conversations require explicitly authorised sessions')
        self.audit, self.enabled, self.last_report = audit, enabled, None
        self.story = StoryLedger()
        self._use_heuristic_story = True
        self.story_scope = "session"
        self.session_stop_check = None  # trusted runner policy; not supplied by a draft

    def scenarios(self): return self.client.scenarios()
    def channels(self): return self.client.channels()

    def list_sessions(self):
        return self.client.list_sessions()

    def restore_session(self, sid):
        """Resume only a provably unused session; never reset a remembered story.

        Used sessions require restoring writer, story and pending-request state
        together. The basic guard cannot establish that from legacy JSONL logs.
        Leave those sessions intact for explicit reconciliation instead.
        """
        if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', sid):
            raise QualityBlocked(QualityReport(errors=['Malformed session ID']))
        # A pre-send audit may outlive a timed-out request whose touch count has
        # not become visible yet. Zero touches alone must not clear that intent.
        log_dir = getattr(self.client, 'log_dir', None)
        if isinstance(log_dir, (str, Path)):
            path = Path(log_dir) / f'{sid}.jsonl'
            try:
                entries = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []
            except (OSError, ValueError):
                raise QualityBlocked(QualityReport(errors=['Unreadable resume audit; reconciliation required']))
            if any(entry.get('kind') in {'quality', 'sent', 'call.start', 'turn', 'page'} for entry in entries):
                raise QualityBlocked(QualityReport(errors=['Prior submission audit requires explicit reconciliation before resume']))
        response = self.client.get_session(sid)
        if (response.get('session_id') != sid or
                response.get('scenario_id') != self.scenario_id or
                response.get('status') != 'active' or
                type(response.get('touches_used')) is not int or
                response['touches_used'] != 0 or
                type(response.get('touch_budget')) is not int or
                response['touch_budget'] <= 0):
            raise QualityBlocked(QualityReport(errors=[
                'Cannot safely resume: require an active unused session in the selected scenario; '
                'used or uncertain sessions need explicit history/request reconciliation. No new session created.']))
        events = self.client.get_events(sid)
        observed = events if isinstance(events, list) else events.get('events') if isinstance(events, dict) else None
        if observed != []:
            raise QualityBlocked(QualityReport(errors=['Cannot resume a session with missing or nonempty event history']))
        self.sessions.add(sid)
        return response

    def create_session(self, scenario_id=None):
        scenario_id = scenario_id or self.scenario_id
        if scenario_id != self.scenario_id:
            raise QualityBlocked(QualityReport(errors=['Session scenario differs from explicit run scope']))
        response = self.client.create_session(scenario_id)
        sid = response.get('session_id')
        if not isinstance(sid, str) or not sid or response.get('scenario_id', scenario_id) != scenario_id:
            raise ValueError('Unexpected session response')
        self.sessions.add(sid)
        return response

    def _scope(self, sid):
        if self.scenario_id == 'eval' and not self.enabled:
            raise QualityBlocked(QualityReport(errors=['Eval requires quality checks enabled']))
        if sid not in self.sessions:
            raise QualityBlocked(QualityReport(errors=['Session not authorised']))

    def _contact_scope(self, sid):
        self._scope(sid)
        if self.session_stop_check and self.session_stop_check(sid):
            raise QualityBlocked(QualityReport(errors=['Recipient requested no further contact in this session']))

    def _emit(self, sid, operation, report, node_id=None):
        self.last_report = deepcopy(report)
        entry = dict(kind='quality', operation=operation, node_id=node_id, qa=deepcopy(report), report=deepcopy(report))
        if self.audit: self.audit(dict(entry, session_id=sid))
        if hasattr(self.client,'_log'): self.client._log(sid, entry)

    def _bypass(self):
        return dict(passed=True, errors=[], warnings=['QUALITY_GATE=off: practice-only checks bypassed'], bypassed=True)

    def _links(self, sid, text, attached=None):
        known = self.registered.get(sid, set()) | ({attached} if attached else set())
        if linked_urls(text) - known:
            raise QualityBlocked(QualityReport(errors=['Every linked URL must have an exact registered page']))

    def check_message(self, message):
        prepared = checked_message(message, self.context)
        self._links(message['session_id'], message.get('body', ''), (prepared.get('page') or {}).get('url'))
        report = self.story.review(message['session_id'], self.story_scope, message.get('body','')) if self._use_heuristic_story else QualityReport()
        prepared['report']['warnings'].extend(report.warnings)
        if not report.passed: raise QualityBlocked(report)
        return prepared

    def send_message(self, message, sent_at=None):
        snapshot = plain(message); sid = snapshot.get('session_id'); self._contact_scope(sid)
        try:
            prepared = self.check_message(snapshot) if self.enabled else None
            report = prepared['report'] if prepared else self._bypass()
        except QualityBlocked as exc:
            self._emit(sid, 'message', exc.report.to_dict(), snapshot.get('node_id')); raise
        self._emit(sid, 'message', report, snapshot.get('node_id'))
        if prepared:
            shared = as_shared_message(prepared)
        else:
            from core.schemas import message_from_dict
            shared = message_from_dict(snapshot)
        result = self.client.send_message(shared, sent_at=sent_at, qa=deepcopy(report))
        if not isinstance(result.get('message_id'), str) or not result['message_id'] or not isinstance(result.get('events'), list):
            raise ValueError('Message delivery uncertain: missing API receipt; reconcile before another send')
        if self.enabled and self._use_heuristic_story and isinstance(result.get('message_id'), str) and isinstance(result.get('events'), list):
            self.story.commit(sid,self.story_scope,shared.body)
        if shared.landing_page is not None:
            self.registered.setdefault(sid,set()).add(shared.landing_page.url)
        return result

    def register_page(self, sid, page):
        self._contact_scope(sid)
        payload, report = prepare_page(page, self.context)
        verdict = report.to_dict() if self.enabled else self._bypass()
        self._emit(sid, 'page', verdict)
        if not verdict['passed']: raise QualityBlocked(report)
        response = self.client.register_page(sid, payload)
        self.registered.setdefault(sid,set()).add(payload['url'])
        return response

    def start_conversation(self, sid, to, channel, sender=None, *, idem_key=None, sent_at=None):
        self._contact_scope(sid)
        if to not in self.context['authorized_targets'] or channel not in LIVE_CHANNELS:
            raise QualityBlocked(QualityReport(errors=['Conversation target/channel outside run scope']))
        snapshot = plain(sender)
        report = inspect_artifact(dict(kind='turn', say='Conversation start',channel=channel),self.context,sender=snapshot)
        verdict = report.to_dict() if self.enabled else self._bypass()
        self._emit(sid,'conversation.start',verdict)
        if not verdict['passed']: raise QualityBlocked(report)
        response = self.client.start_conversation(sid,to,channel,snapshot,idem_key=idem_key or str(uuid4()),sent_at=sent_at,qa=verdict)
        cid = response.get('conversation_id')
        if not isinstance(cid,str) or not cid: raise ValueError('No conversation ID')
        self.conversations[cid] = sid
        return response

    def check_turn(self, cid, line, *, sid):
        self._scope(sid)
        if self.conversations.get(cid) != sid: raise QualityBlocked(QualityReport(errors=['Conversation outside session scope']))
        checked_turn({'say':line},self.context); self._links(sid,line)
        report = self.story.review(sid,self.story_scope,line) if self._use_heuristic_story else QualityReport()
        claims = profile_claim_checks(line,self.context.get('profile_facts',[]))
        report.errors.extend(claims.errors);report.warnings.extend(claims.warnings)
        if not report.passed: raise QualityBlocked(report)
        return report.to_dict()

    def say(self,cid,line,*,sid,idem_key=None,sent_at=None):
        self._contact_scope(sid)
        if self.conversations.get(cid) != sid: raise QualityBlocked(QualityReport(errors=['Conversation outside session scope']))
        try:
            if self.enabled:
                report = self.check_turn(cid,line,sid=sid)
            else:
                report = self._bypass()
        except QualityBlocked as exc:
            self._emit(sid,'conversation.turn',exc.report.to_dict()); raise
        self._emit(sid,'conversation.turn',report)
        response = self.client.say(cid,line,sid=sid,idem_key=idem_key or str(uuid4()),sent_at=sent_at,qa=report)
        if self.enabled and self._use_heuristic_story and isinstance(response.get('events'),list): self.story.commit(sid,self.story_scope,line)
        return response

    def get_session(self,sid): self._scope(sid); return self.client.get_session(sid)
    def get_events(self,sid): self._scope(sid); return self.client.get_events(sid)
    def end_conversation(self,cid):
        if cid not in self.conversations: raise QualityBlocked(QualityReport(errors=['Conversation not authorised']))
        response=self.client.end_conversation(cid); del self.conversations[cid]; return response
    def end_session(self,sid):
        self._scope(sid); response=self.client.end_session(sid); self.sessions.remove(sid)
        self.conversations={cid:owner for cid,owner in self.conversations.items() if owner!=sid}
        return response
