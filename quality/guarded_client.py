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
    def __init__(self, client, context, *, session_ids, conversation_sessions=None, audit=None):
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

    def _scope(self, sid):
        if sid not in self.sessions:
            raise QualityBlocked(QualityReport(errors=['Session not explicitly authorised']))

    def _audit(self, operation, report):
        if self.audit:
            self.audit({'operation': operation, 'report': deepcopy(report)})

    def send_message(self, message):
        from schemas import message_from_dict
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
        body = prepared['payload']
        shared = message_from_dict({
            'session_id': prepared['session_id'], 'channel': body['channel'],
            'to': body['to'], 'sender': body['from'], 'subject': body.get('subject', ''),
            'body': body['body'], 'attachments': body.get('attachments', []),
            'landing_page': prepared['page'], 'idempotency_key': prepared['idempotency_key'],
            'node_id': prepared.get('node_id') or '',
        })
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
