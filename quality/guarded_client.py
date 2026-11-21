"""Opt-in quality boundary around Mavis's client; does not change her code.

Only explicitly authorised sessions/conversations can be used. This wrapper is
not automatically installed in existing scripts. The caller owns session setup.
"""
from copy import deepcopy
from .checks import QualityReport
from .integration import (checked_message, checked_turn, inspect_artifact,
                          prepare_page, QualityBlocked, validate_context)

LIVE_CHANNELS = {'phone_call', 'video_call', 'teams_call', 'live_chat'}


class GuardedClient:
    def __init__(self, client, context, *, session_ids=(), conversation_sessions=None, audit=None):
        validate_context(context)
        self.client = client
        self.context = deepcopy(context)
        if not isinstance(session_ids, (list, tuple, set)) or any(not isinstance(x, str) or not x for x in session_ids):
            raise ValueError('session_ids must contain authorised nonempty session IDs')
        self.sessions = frozenset(session_ids)
        self.conversations = dict(conversation_sessions or {})
        if any(not isinstance(cid, str) or not cid or sid not in self.sessions
               for cid, sid in self.conversations.items()):
            raise ValueError('Resumed conversations must map to an authorised session')
        self.audit = audit

    def scenarios(self):
        return self.client.scenarios()

    def channels(self):
        return self.client.channels()

    def create_session(self, scenario_id='practice'):
        if scenario_id != 'practice':
            raise QualityBlocked(QualityReport(errors=['Only practice session creation is supported by this wrapper']))
        response = self.client.create_session(scenario_id)
        sid = response.get('session_id')
        if not isinstance(sid, str) or not sid or response.get('scenario_id', 'practice') != 'practice':
            raise ValueError('Unexpected practice session response; session not authorised')
        self.sessions = self.sessions | {sid}
        return response

    def get_session(self, sid):
        self._scope(sid)
        return self.client.get_session(sid)

    def get_events(self, sid):
        self._scope(sid)
        return self.client.get_events(sid)

    def end_session(self, sid):
        self._scope(sid)
        response = self.client.end_session(sid)
        self.sessions = self.sessions - {sid}
        self.conversations = {cid: owner for cid, owner in self.conversations.items() if owner != sid}
        return response

    def end_conversation(self, cid):
        if cid not in self.conversations:
            raise QualityBlocked(QualityReport(errors=['Conversation not authorised']))
        response = self.client.end_conversation(cid)
        del self.conversations[cid]
        return response

    def _scope(self, sid):
        if sid not in self.sessions:
            raise QualityBlocked(QualityReport(errors=['Session not explicitly authorised']))

    def _audit(self, operation, report):
        if self.audit:
            self.audit({'operation': operation, 'report': deepcopy(report)})

    def send_message(self, message):
        # Snapshot before validation; never send a caller-mutated or audit-mutated draft.
        from .integration import plain
        snapshot = plain(message)
        self._scope(snapshot.get('session_id'))
        try:
            prepared = checked_message(snapshot, self.context)
        except QualityBlocked as exc:
            self._audit('message', exc.report.to_dict())
            raise
        self._audit('message', prepared['report'])
        # Convert API-ready representation back to current shared Message for Mavis.
        from .integration import as_shared_message
        shared = as_shared_message(prepared)
        # Mavis registers the already-validated page before sending the message.
        return self.client.send_message(shared)

    def register_page(self, sid, page):
        self._scope(sid)
        payload, report = prepare_page(page, self.context)
        self._audit('page', report.to_dict())
        if not report.passed:
            raise QualityBlocked(report)
        return self.client.register_page(sid, payload)

    def start_conversation(self, sid, to, channel, sender, *, idem_key):
        from .integration import plain
        self._scope(sid)
        snapshot = plain(sender)
        report = inspect_artifact({'kind': 'turn', 'say': 'Conversation start', 'channel': channel},
                                  self.context, sender=snapshot)
        if to not in self.context.get('authorized_targets', []) or channel not in LIVE_CHANNELS:
            report.errors.append('Conversation target or channel not authorised')
        if not isinstance(idem_key, str) or not idem_key.strip():
            report.errors.append('Stable idempotency key required')
        self._audit('conversation.start', report.to_dict())
        if not report.passed:
            raise QualityBlocked(report)
        response = self.client.start_conversation(sid, to, channel, snapshot, idem_key=idem_key)
        cid = response.get('conversation_id')
        if not isinstance(cid, str) or not cid:
            raise ValueError('Client returned no conversation ID; cannot authorise turns')
        self.conversations[cid] = sid
        return response

    def say(self, cid, line, *, sid, idem_key):
        self._scope(sid)
        if self.conversations.get(cid) != sid:
            raise QualityBlocked(QualityReport(errors=['Conversation not authorised for this session']))
        if not isinstance(idem_key, str) or not idem_key.strip():
            raise QualityBlocked(QualityReport(errors=['Stable idempotency key required']))
        try:
            turn = checked_turn({'say': line}, self.context)
        except QualityBlocked as exc:
            self._audit('conversation.turn', exc.report.to_dict())
            raise
        self._audit('conversation.turn', {'passed': True, 'errors': [], 'warnings': []})
        return self.client.say(cid, turn['say'], sid=sid, idem_key=idem_key)
