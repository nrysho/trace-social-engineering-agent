"""Opt-in evidence + consistency boundary on top of existing permission checks.

No automatic fetching, sending, fact extraction, or mutation of team schemas.
Optional SQLite state preserves reservations and declarations across restarts.
"""
from copy import deepcopy
from threading import RLock

from .checks import QualityReport, normalized
from .guarded_client import GuardedClient, LIVE_CHANNELS
from .integration import plain, QualityBlocked
from .session_consistency import SessionLedger, content_digest, message_content


class ReviewedClient(GuardedClient):
    def __init__(self, client, context, *, evidence_catalog, identity_reviewer=None, critic=None, state_store=None, **kwargs):
        super().__init__(client, context, **kwargs)
        if not self.enabled:
            raise ValueError('ReviewedClient requires hard checks; practice bypass belongs to GuardedClient')
        self._use_heuristic_story = False  # Explicit scoped declarations are authoritative here.
        self.catalog = evidence_catalog
        self.ledger = SessionLedger()
        self._pending = {}
        self._lock = RLock()
        self._live_metadata = {}
        self._completed = {}
        if identity_reviewer is not None and identity_reviewer.scenario_id != self.scenario_id:
            raise ValueError('Identity reviewer scenario differs from the client scope')
        self.identity_reviewer = identity_reviewer
        self.critic = critic
        self.state_store = state_store
        self._delivered = {}
        self._revision = 0
        self._storage_failed = False
        self._context_tag = content_digest({'scenario_id':self.scenario_id, 'permissions':{key: self.context.get(key, []) for key in (
            'authorized_targets', 'approved_sender_domains', 'approved_link_hosts',
            'known_organisation_domains', 'approved_sender_addresses')}})
        self._refresh()

    def _refresh(self):
        if self._storage_failed:
            raise RuntimeError('State storage failed; stop and inspect durable state before creating a new controller')
        if self.state_store is None:
            return
        revision, state = self.state_store.load()
        if not state:
            self._revision = revision
            return
        if type(state.get('schema_version')) is not int or state['schema_version'] != 1 or state.get('context_tag') != self._context_tag:
            raise ValueError('State version or permission context differs; do not silently reset it')
        ledger = SessionLedger.from_snapshot(state.get('ledger'))
        pending, delivered = state.get('pending'), state.get('delivered')
        if not isinstance(pending, dict) or not isinstance(delivered, list):
            raise ValueError('Invalid stored requests')
        for sid, item in pending.items():
            if (not isinstance(sid, str) or not isinstance(item, dict)
                    or not isinstance(item.get('key'), str) or not item['key']
                    or not isinstance(item.get('digest'), str) or len(item['digest']) != 64
                    or type(item.get('is_turn')) is not bool):
                raise ValueError('Invalid stored reservation')
            SessionLedger().apply_session(sid, item.get('after'))
        seen = {}
        for item in delivered:
            if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k] for k in ('session_id', 'key', 'digest')):
                raise ValueError('Invalid delivered request record')
            key = item['session_id'], item['key']
            if key in seen:
                raise ValueError('Duplicate delivered key')
            seen[key] = item['digest']
        self.ledger, self._pending, self._delivered = ledger, pending, seen
        self._revision = revision

    def _persist(self):
        if self.state_store is None:
            return
        state = dict(schema_version=1, context_tag=self._context_tag, ledger=self.ledger.snapshot(),
                     pending=self._pending,
                     delivered=[dict(session_id=sid, key=key, digest=digest)
                                for (sid, key), digest in self._delivered.items()])
        try:
            self._revision = self.state_store.save(self._revision, state)
        except Exception:
            self._storage_failed = True
            raise

    def _audit_review(self, snapshot, report, operation='evidence.consistency'):
        record = dict(operation=operation, session_id=snapshot.get('session_id'),
                      node_id=snapshot.get('node_id'), conversation_id=snapshot.get('conversation_id'),
                      idempotency_key=snapshot.get('idempotency_key'), target_id=snapshot.get('to'),
                      channel=snapshot.get('channel'), content_sha256=content_digest(snapshot), report=deepcopy(report))
        if self.state_store is not None:
            self.state_store.append_audit(record)
        if self.audit:
            self.audit(deepcopy(record))

    def inspect_review(self, message, review):
        report = QualityReport()
        if not isinstance(review, dict):
            report.errors.append('Evidence/consistency review sidecar required')
            return report
        if review.get('content_sha256') != content_digest(message):
            report.errors.append('Review content digest differs from the complete message snapshot')
        if type(review.get('schema_version')) is not int or review['schema_version'] != 1 or review.get('claims_declared') is not True:
            report.errors.append('Version 1 explicit claim declaration required')
        claims = self.catalog.review(message.get('to'), message_content(message), review.get('claim_ids'))
        report.errors.extend(claims.errors)
        report.warnings.extend(claims.warnings)
        consistency = self.ledger.review(message, review)
        report.errors.extend(consistency.errors)
        for assertion in review.get('assertions', []) if isinstance(review.get('assertions'), list) else []:
            if not isinstance(assertion, dict) or assertion.get('kind') != 'target_fact':
                continue
            cid = assertion.get('claim_id')
            claim = self.catalog.claims.get(cid) if isinstance(cid, str) else None
            if (claim is None or not isinstance(review.get('claim_ids'), list) or cid not in review['claim_ids']
                    or claim.get('fact_key') != assertion.get('key')
                    or normalized(claim.get('fact_value', '')) != normalized(assertion.get('value', ''))):
                report.errors.append('Target-fact assertion needs matching approved claim reference/key/value')
        report.errors = list(dict.fromkeys(report.errors))
        if self.identity_reviewer is not None:
            identity = self.identity_reviewer.assess(message.get('to'))
            if identity.get('passed') is not True:
                report.errors.append('Public identity evidence is ' + identity['status'])
            report.warnings.append(identity['warning'])
        if self.critic is not None and not report.errors:
            from .claim_coverage import critic_input, check_coverage
            try:
                result = self.critic(critic_input(message, self.catalog))
                coverage = check_coverage(message, review, result, self.catalog)
                report.errors.extend(coverage.errors)
                report.warnings.extend(coverage.warnings)
            except Exception:
                report.errors.append('Independent critic failed; no automatic bypass permitted')
        return report

    @staticmethod
    def _ack(response, *, is_turn=False):
        if (not isinstance(response, dict) or not isinstance(response.get('events'), list)
                or any(not isinstance(e, dict) or not isinstance(e.get('type'), str) for e in response['events'])):
            raise ValueError('Delivery uncertain: explicit valid events array required')
        if is_turn:
            if (type(response.get('turns_used')) is not int or response['turns_used'] < 1
                    or not isinstance(response.get('persona_says'), str) or type(response.get('ended')) is not bool):
                raise ValueError('Turn acknowledgement needs turns_used, persona_says and ended')
        elif not isinstance(response.get('message_id'), str) or not response['message_id'].strip():
            raise ValueError('Message acknowledgement needs message_id')

    def _submit(self, snapshot, review, send, request_metadata=None):
        with self._lock:
            self._refresh()
            metadata = deepcopy(request_metadata or {})
            request_digest = content_digest({'message':snapshot,'transport':metadata}) if metadata else content_digest(snapshot)
            sid = snapshot.get('session_id')
            self._scope(sid)
            key = snapshot.get('idempotency_key')
            if not isinstance(key, str) or not key.strip():
                raise QualityBlocked(QualityReport(errors=['Stable request key required']))
            completed = self._completed.get((sid, key))
            if completed:
                digest, response = completed
                if digest != request_digest:
                    raise QualityBlocked(QualityReport(errors=['Request key reused with different content']))
                return deepcopy(response)
            if (sid, key) in self._delivered:
                raise QualityBlocked(QualityReport(errors=[
                    'Request already acknowledged before restart; recover original response from API history, do not resend']))
            if sid in self._pending:
                raise QualityBlocked(QualityReport(errors=[
                    'Session has an unresolved delivery; reconcile original request before another send']))
            # Reject hard-rule violations before any optional model-critic call.
            from .integration import checked_message, checked_turn
            try:
                if 'say' in snapshot:
                    checked_turn({'say': snapshot['say']}, self.context)
                else:
                    checked_message(snapshot, self.context)
            except QualityBlocked as exc:
                self._audit_review(snapshot, exc.report.to_dict(), operation='hard_rule.blocked')
                raise
            sidecar = deepcopy(review)
            if metadata and (not isinstance(sidecar,dict) or sidecar.get('transport') != metadata):
                raise QualityBlocked(QualityReport(errors=['Review must bind the exact sent_at transport metadata']))
            report = self.inspect_review(snapshot, sidecar)
            self._audit_review(snapshot, report.to_dict())
            if not report.passed:
                raise QualityBlocked(report)
            # Reserve before transport. Failed sends retain the snapshot rather
            # than silently discarding a potentially delivered declaration.
            self._pending[sid] = dict(key=key, digest=request_digest, is_turn='say' in snapshot,
                                      after=self.ledger.after_session(snapshot, sidecar))
            self._persist()  # Reservation must reach disk before transport.
            try:
                response = send()
            except QualityBlocked:
                del self._pending[sid]  # Existing local hard gate made zero submissions.
                self._persist()
                raise
            self._ack(response, is_turn='say' in snapshot)  # Exceptions preserve pending state.
            self.ledger.commit(snapshot, sidecar)
            self._completed[(sid, key)] = (request_digest, deepcopy(response))
            self._delivered[(sid, key)] = request_digest
            del self._pending[sid]
            self._persist()  # Failure leaves durable pending state for reconciliation.
            self._audit_review(snapshot, dict(passed=True, errors=[], warnings=['Acknowledged delivery; not an official outcome']),
                               operation='delivery.acknowledged')
            return response

    def send_message(self, message, sent_at=None, *, review=None):
        snapshot = plain(message)
        return self._submit(snapshot, review, lambda: super(ReviewedClient, self).send_message(snapshot,sent_at=sent_at),
                            {'sent_at':sent_at} if sent_at is not None else None)

    def register_page(self, sid, page, **kwargs):
        raise QualityBlocked(QualityReport(errors=[
            'Supply landing_page on the reviewed message; standalone page registration has no evidence sidecar']))

    def start_conversation(self, sid, to, channel, sender=None, *, idem_key=None, sent_at=None):
        with self._lock:
            self._refresh()
            self._scope(sid)
            if sid in self._pending:
                raise QualityBlocked(QualityReport(errors=['Reconcile unresolved delivery before opening a conversation']))
            sender_snapshot = plain(sender)
            from .integration import inspect_artifact
            report = inspect_artifact(dict(kind='turn', say='Conversation start', channel=channel), self.context, sender=sender_snapshot)
            if to not in self.context.get('authorized_targets', []) or channel not in LIVE_CHANNELS:
                report.errors.append('Conversation target/channel not authorised')
            if not isinstance(idem_key, str) or not idem_key.strip():
                report.errors.append('Stable conversation key required')
            if self.identity_reviewer is not None and not self.identity_reviewer.assess(to)['passed']:
                report.errors.append('Identity evidence does not support this target')
            if not report.passed:
                raise QualityBlocked(report)
            meta = dict(to=to, channel=channel, sender=sender_snapshot)
            digest = content_digest(dict(meta, session_id=sid, operation='conversation_start', idempotency_key=idem_key, sent_at=sent_at))
            cached = self._completed.get((sid, idem_key))
            if cached:
                if cached[0] != digest:
                    raise QualityBlocked(QualityReport(errors=['Conversation key reused with different metadata']))
                return deepcopy(cached[1])
            if (sid, idem_key) in self._delivered:
                raise QualityBlocked(QualityReport(errors=['Conversation already opened before restart; recover its ID, do not reopen']))
            after = {key: [row for row in rows if row['session_id'] == sid]
                     for key, rows in self.ledger.snapshot().items()}
            self._pending[sid] = dict(key=idem_key, digest=digest, is_turn=False,
                                      operation='conversation_start', metadata=meta, after=after)
            self._persist()
            try:
                response = super().start_conversation(sid, to, channel, sender_snapshot, idem_key=idem_key, sent_at=sent_at)
            except QualityBlocked:
                del self._pending[sid]
                self._persist()
                raise
            self._live_metadata[response['conversation_id']] = dict(to=to, channel=channel, sender=sender_snapshot)
            self._completed[(sid, idem_key)] = digest, deepcopy(response)
            self._delivered[(sid, idem_key)] = digest
            del self._pending[sid]
            self._persist()
            return response

    def say(self, cid, line, *, sid, idem_key, review=None, sent_at=None):
        meta = self._live_metadata.get(cid)
        if meta is None:
            raise QualityBlocked(QualityReport(errors=['Conversation lacks reviewed target/sender metadata; resumed turns unsupported']))
        snapshot = dict(meta, session_id=sid, conversation_id=cid, say=line, idempotency_key=idem_key)
        return self._submit(snapshot, review,
                            lambda: super(ReviewedClient, self).say(cid, line, sid=sid, idem_key=idem_key,sent_at=sent_at),
                            {'sent_at':sent_at} if sent_at is not None else None)

    def reconcile_acknowledgement(self, sid, idempotency_key, response):
        """Caller supplies authoritative response for original key after history check.

        This method cannot authenticate arbitrary JSON or discover deliveries.
        No automatic retry, known-rejection override, or new contact is performed.
        """
        with self._lock:
            self._refresh()
            self._scope(sid)
            reservation = self._pending[sid]
            if reservation['key'] != idempotency_key:
                raise ValueError('Reconciliation key does not match original request')
            if reservation.get('operation') == 'conversation_start':
                cid = response.get('conversation_id') if isinstance(response, dict) else None
                if not isinstance(cid, str) or not cid:
                    raise ValueError('Conversation reconciliation needs original conversation ID')
                self.conversations[cid] = sid
                self._live_metadata[cid] = deepcopy(reservation['metadata'])
            else:
                self._ack(response, is_turn=reservation['is_turn'])
            self.ledger.apply_session(sid, reservation['after'])
            self._completed[(sid, idempotency_key)] = (reservation['digest'], deepcopy(response))
            self._delivered[(sid, idempotency_key)] = reservation['digest']
            del self._pending[sid]
            self._persist()

    def review_snapshot(self):
        with self._lock:
            self._refresh()
            return deepcopy(dict(ledger=self.ledger.snapshot(), unresolved_sessions=list(self._pending),
                                 pending_requests=[dict(session_id=sid, idempotency_key=r['key'], content_sha256=r['digest'])
                                                   for sid, r in self._pending.items()]))
