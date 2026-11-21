"""Adapters for main's shared Message/LandingPage dataclasses, without schema edits."""
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from urllib.parse import urlsplit
import re
from .checks import check_artifact, QualityReport, Markup, normalized

MESSAGE_CHANNELS = {
    'email', 'calendar_invite', 'shared_document', 'voicemail', 'sms', 'whatsapp',
    'signal', 'telegram', 'imessage', 'slack', 'teams_chat', 'discord',
    'linkedin_message', 'linkedin_connection_request', 'x_dm', 'instagram_dm',
    'facebook_messenger', 'mfa_push',
}


class QualityBlocked(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__('Quality gate blocked: ' + '; '.join(report.errors))


def plain(value):
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return deepcopy(value)
    raise QualityBlocked(QualityReport(errors=['Expected a shared dataclass instance or JSON object']))


def validate_context(context):
    if not isinstance(context, dict) or context.get('simulation_only') is not True:
        raise QualityBlocked(QualityReport(errors=['Explicit simulation-only context required']))
    for key in ('authorized_targets', 'approved_sender_domains', 'approved_link_hosts',
                'known_organisation_domains', 'approved_sender_addresses'):
        values = context.get(key, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
            raise QualityBlocked(QualityReport(errors=[f'{key} must be a list of nonempty strings']))


def inspect_artifact(artifact, context, *, sender=None):
    validate_context(context)
    approved = context.get('approved_link_hosts', [])
    report = check_artifact(artifact, approved_domains=approved)
    hosts = []
    text = normalized(' '.join(str(artifact.get(k, '')) for k in ('body', 'html', 'text', 'url', 'say')))
    markup = Markup()
    markup.feed(text)
    for url in re.findall(r'https?://[^\s<>\x22\x27)]+', text, re.I) + markup.links:
        try:
            hosts.append((urlsplit(url).hostname or '').lower().rstrip('.'))
        except ValueError:
            report.errors.append('Malformed URL')
    if sender is not None:
        if not isinstance(sender, dict) or not all(isinstance(sender.get(k), str) and sender[k].strip() for k in ('name', 'address')):
            report.errors.append('Sender name and address required')
        else:
            address = sender['address']
            if artifact.get('channel', 'email') == 'email':
                tail = re.sub(r'<[^>]*>', '', normalized(artifact.get('body', '')))[-240:].lower()
                if normalized(sender['name']).lower() not in tail:
                    report.warnings.append('Sender name not found near end of email; inspect signature')
            # Check sender wording as well as body; domain approval is separate.
            report.errors.extend(check_artifact({'kind': 'turn', 'say': sender['name'] + ' ' + address}).errors)
            if '@' in address:
                if not re.fullmatch(r'[^\s@<>]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', address):
                    report.errors.append('Malformed sender email')
                host = address.rsplit('@', 1)[-1].lower().rstrip('.')
                hosts.append(host)
                if host not in {v.lower().rstrip('.') for v in context.get('approved_sender_domains', [])}:
                    report.errors.append('Sender domain not explicitly approved')
            elif artifact.get('channel') == 'email' or address not in context.get('approved_sender_addresses', []):
                report.errors.append('Non-email sender address/handle not explicitly approved')
        report.warnings = [w for w in report.warnings if not w.startswith('Sender name/address missing')]
    forbidden = {v.lower().rstrip('.') for v in context.get('known_organisation_domains', [])}
    if any(h == d or h.endswith('.' + d) for h in hosts for d in forbidden):
        report.errors.append('Known real organisation domain prohibited, including subdomains')
    report.errors = list(dict.fromkeys(report.errors))
    return report


def prepare_page(page, context):
    data = plain(page)
    report = inspect_artifact({'kind': 'page', **data}, context)
    if set(data) - {'url', 'title', 'fields', 'html', 'text'}:
        report.errors.append('Unknown landing-page fields')
    if not isinstance(data.get('fields', []), list) or any(not isinstance(f, str) for f in data.get('fields', [])):
        report.errors.append('Page field names must be a list of strings')
    elif len(data.get('fields', [])) > 20 or any(not f.strip() for f in data.get('fields', [])):
        report.errors.append('Use at most 20 nonempty page field names')
    return data, report


def prepare_message(message, context):
    """Return API-ready payload plus separate page registration and QA report.

    Does not send, register, or invent idempotency/session metadata.
    """
    data = plain(message)
    sender = data.get('sender', data.get('from'))
    payload = {k: data[k] for k in ('to', 'channel', 'subject', 'body', 'attachments') if k in data}
    payload['from'] = sender
    artifact = {k: v for k, v in payload.items() if k != 'from'}
    report = inspect_artifact(artifact, context, sender=sender or {})
    if data.get('to') not in context.get('authorized_targets', []):
        report.errors.append('Unauthorized simulator target')
    if not isinstance(data.get('channel'), str) or data.get('channel') not in MESSAGE_CHANNELS:
        report.errors.append('Unsupported message channel; use call-turn adapter for live conversations')
    if not isinstance(data.get('session_id'), str) or not data['session_id'].strip():
        report.errors.append('Session ID required')
    if not isinstance(data.get('idempotency_key'), str) or not data['idempotency_key'].strip():
        report.errors.append('Stable idempotency key required')
    if set(data) - {'session_id', 'channel', 'to', 'sender', 'from', 'body', 'subject',
                    'landing_page', 'attachments', 'idempotency_key', 'node_id'}:
        report.errors.append('Unknown Message fields')
    if 'sender' in data and 'from' in data:
        report.errors.append('Ambiguous sender fields; use shared sender or API from, not both')
    page = None
    if data.get('landing_page'):
        try:
            page, page_report = prepare_page(data['landing_page'], context)
            report.errors.extend('Page: ' + e for e in page_report.errors)
            report.warnings.extend('Page: ' + w for w in page_report.warnings)
        except QualityBlocked as exc:
            report.errors.extend('Page: ' + e for e in exc.report.errors)
    report.errors = list(dict.fromkeys(report.errors))
    return {'session_id': data.get('session_id'), 'idempotency_key': data.get('idempotency_key'),
            'node_id': data.get('node_id'), 'payload': payload, 'page': page, 'report': report.to_dict()}


def checked_message(message, context):
    prepared = prepare_message(message, context)
    if not prepared['report']['passed']:
        raise QualityBlocked(QualityReport(errors=prepared['report']['errors'], warnings=prepared['report']['warnings']))
    return prepared


def checked_turn(turn, context):
    data = plain(turn)
    report = inspect_artifact({'kind': 'turn', 'say': data.get('say'),
                               'attachments': data.get('attachments', [])}, context)
    if isinstance(data.get('say'), str) and len(data['say']) > 4000:
        report.errors.append('Call turn exceeds 4000 characters')
    if set(data) - {'say', 'attachments'}:
        report.errors.append('Unknown call-turn fields')
    if not report.passed:
        raise QualityBlocked(report)
    return data


def generate_checked(generate, context, *, max_attempts=3, audit=None):
    """Writer callback: generate(previous_report_or_None) -> shared Message.

    Bounded automatic corrections. No human approval, network, or send callback.
    Exhaustion raises; caller must never fall through to send after an exception.
    """
    if type(max_attempts) is not int or not 1 <= max_attempts <= 5:
        raise ValueError('max_attempts must be between 1 and 5')
    previous = None
    for attempt in range(1, max_attempts + 1):
        prepared = prepare_message(generate(deepcopy(previous)), context)
        previous = prepared['report']
        if audit:
            audit({'attempt': attempt, 'report': deepcopy(previous)})
        if previous['passed']:
            return prepared
    raise QualityBlocked(QualityReport(errors=previous['errors'], warnings=previous['warnings']))
