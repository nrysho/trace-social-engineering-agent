"""Declared session facts and persona identities across channels. No inference."""
from copy import deepcopy
from hashlib import sha256
from html.parser import HTMLParser
import json

from .checks import QualityReport, normalized


def content_digest(message):
    return sha256(json.dumps(message, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def message_content(message):
    page = message.get('landing_page') or {}
    sender = message.get('sender') or {}
    raw = '\n'.join(str(x) for x in [message.get('subject', ''), message.get('body', ''),
                    message.get('say', ''), sender.get('name', ''), sender.get('address', ''),
                    page.get('html', ''), page.get('text', ''), page.get('url', '')])
    class Text(HTMLParser):
        def handle_data(self, data):
            parts.append(data)
    parts = []
    parser = Text(convert_charrefs=True)
    parser.feed(raw)
    parser.close()
    return raw + '\n' + ''.join(parts)


class SessionLedger:
    def __init__(self):
        self._values = {}
        self._personas = {}

    @classmethod
    def from_snapshot(cls, snapshot):
        if not isinstance(snapshot, dict) or set(snapshot) != {'declarations', 'personas'}:
            raise ValueError('Invalid ledger snapshot')
        result = cls()
        for name in ('declarations', 'personas'):
            if not isinstance(snapshot[name], list):
                raise ValueError('Ledger entries must be lists')
        for row in snapshot['personas']:
            if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k] for k in ('session_id', 'persona', 'name', 'address')):
                raise ValueError('Invalid stored persona')
            key = row['session_id'], row['persona']
            if key in result._personas:
                raise ValueError('Duplicate stored persona')
            result._personas[key] = row['name'], row['address']
        for row in snapshot['declarations']:
            if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k] for k in ('session_id', 'persona', 'key', 'value', 'kind')):
                raise ValueError('Invalid stored declaration')
            if row['kind'] not in {'target_fact', 'scenario_story'}:
                raise ValueError('Unsupported stored declaration kind')
            key = row['session_id'], row['persona'], row['key']
            if key in result._values or (row['persona'] != '*' and key[:2] not in result._personas):
                raise ValueError('Duplicate declaration or missing stored persona')
            result._values[key] = row['value'], row['kind']
        return result

    def after_session(self, message, review):
        preview = self.from_snapshot(self.snapshot())
        preview.commit(message, review)
        sid = message['session_id']
        return {key: [row for row in rows if row['session_id'] == sid]
                for key, rows in preview.snapshot().items()}

    def apply_session(self, sid, snapshot):
        parsed = self.from_snapshot(snapshot)
        if any(row['session_id'] != sid for rows in snapshot.values() for row in rows):
            raise ValueError('Reservation includes a different session')
        self._values = {key: value for key, value in self._values.items() if key[0] != sid}
        self._personas = {key: value for key, value in self._personas.items() if key[0] != sid}
        self._values.update(parsed._values)
        self._personas.update(parsed._personas)

    def review(self, message, review):
        report = QualityReport()
        sid, persona = message.get('session_id'), review.get('persona_id')
        if not isinstance(persona, str) or not persona.strip():
            report.errors.append('Explicit persona_id required')
            return report
        sender = message.get('sender') or {}
        identity = (sender.get('name'), sender.get('address'))
        old = self._personas.get((sid, persona))
        if old is not None and old != identity:
            report.errors.append('Sender identity changed under the same persona_id')
        assertions = review.get('assertions')
        if not isinstance(assertions, list):
            report.errors.append('Explicit assertions list required (empty if none declared)')
            return report
        text = normalized(message_content(message))
        pending = dict(self._values)
        for item in assertions:
            if not isinstance(item, dict) or item.get('scope') not in {'session', 'persona'}:
                report.errors.append('Each assertion needs session or persona scope')
                continue
            key, value = item.get('key'), item.get('value')
            if not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip():
                report.errors.append('Assertion key/value must be nonempty text')
                continue
            if item.get('kind') not in {'target_fact', 'scenario_story', 'observed_reply', 'hypothesis'}:
                report.errors.append(f'{key}: assertion kind missing/invalid')
            if item.get('kind') in {'hypothesis', 'observed_reply'}:
                report.errors.append(f'{key}: hypotheses/reply claims require evidence review before asserting as facts')
            if normalized(value) not in text:
                report.errors.append(f'{key}: declared value absent from message/page')
            slot = (sid, persona if item['scope'] == 'persona' else '*', key)
            record = (normalized(value), item.get('kind'))
            if slot in pending and pending[slot] != record:
                report.errors.append(f'{key}: contradicts earlier declaration in this scope')
            pending[slot] = record
        return report

    def commit(self, message, review):
        """Called only following acknowledged delivery by ReviewedClient."""
        report = self.review(message, review)
        if not report.passed:
            raise ValueError('Cannot commit contradictory declarations')
        sid, persona = message['session_id'], review['persona_id']
        sender = message.get('sender') or {}
        self._personas[(sid, persona)] = (sender.get('name'), sender.get('address'))
        for item in review['assertions']:
            slot = (sid, persona if item['scope'] == 'persona' else '*', item['key'])
            self._values[slot] = (normalized(item['value']), item['kind'])

    def snapshot(self):
        return deepcopy({'declarations': [dict(session_id=s, persona=p, key=k, value=v, kind=t)
                                          for (s, p, k), (v, t) in self._values.items()],
                         'personas': [dict(session_id=s, persona=p, name=n, address=a)
                                      for (s, p), (n, a) in self._personas.items()]})
