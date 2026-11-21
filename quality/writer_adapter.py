"""Map Izen's writer result to shared QA contracts. No generation or sending."""
from copy import deepcopy
from .checks import QualityReport
from .integration import checked_message, checked_turn, plain, QualityBlocked


def _content(result):
    if not isinstance(result, dict) or not isinstance(result.get('content'), dict):
        raise QualityBlocked(QualityReport(errors=['Writer result must contain a content object']))
    content = deepcopy(result['content'])
    if set(content) - {'subject', 'body'}:
        raise QualityBlocked(QualityReport(errors=['Unsupported writer content fields; supply page separately']))
    for flag in ('fallback_used', 'refusal_logged'):
        if flag in result and type(result[flag]) is not bool:
            raise QualityBlocked(QualityReport(errors=[f'{flag} must be a boolean when supplied']))
    if 'model' in result and not isinstance(result['model'], str):
        raise QualityBlocked(QualityReport(errors=['Writer model provenance must be text when supplied']))
    provenance = {key: result.get(key) for key in ('model', 'fallback_used', 'refusal_logged')}
    return content, provenance


def checked_writer_message(result, context, *, sender, target_id, channel,
                           session_id, node_id, idempotency_key, landing_page=None, page_url=None):
    content, provenance = _content(result)
    sender = plain(sender)
    if sender.get('email') and sender.get('address') and sender['email'] != sender['address']:
        raise QualityBlocked(QualityReport(errors=['Sender email and address disagree']))
    shared_sender = {'name': sender.get('name'), 'address': sender.get('address') or sender.get('email')}
    page = plain(landing_page) if landing_page is not None else None
    if page is not None:
        if page_url and page.get('url') and page_url != page['url']:
            raise QualityBlocked(QualityReport(errors=['Supplied page URL disagrees with page content metadata']))
        if page_url:
            page['url'] = page_url
        if not page.get('url'):
            raise QualityBlocked(QualityReport(errors=['Writer page needs an explicitly supplied registered URL']))
    prepared = checked_message({
        'session_id': session_id, 'node_id': node_id, 'idempotency_key': idempotency_key,
        'to': target_id, 'channel': channel, 'sender': shared_sender,
        'subject': content.get('subject', ''), 'body': content.get('body'),
        'landing_page': page, 'attachments': [],
    }, context)
    prepared['generation'] = provenance  # metadata, never inserted in API payload
    return prepared


def checked_writer_turn(result, context):
    content, provenance = _content(result)
    return {'payload': checked_turn({'say': content.get('body')}, context), 'generation': provenance}
