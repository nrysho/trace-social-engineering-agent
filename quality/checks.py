"""Automatic pre-send checks shared by messages, pages and future call turns.

This is a deterministic rule checker, not a guarantee of challenge compliance.
Domain approval is an explicit team configuration, never inferred from spelling.
"""
from dataclasses import asdict, dataclass, field
from html import unescape
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import urlsplit


@dataclass
class QualityReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self):
        return not self.errors

    def to_dict(self):
        return {'passed': self.passed, **asdict(self)}


def normalized(text):
    text = unicodedata.normalize('NFKC', unescape(str(text)))
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return re.sub(r'\s+', ' ', text).strip()


class Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name.lower() in {'href', 'action', 'src', 'srcset', 'poster', 'data'} and value:
                self.links.append(value)


def check_artifact(artifact: dict, *, approved_domains=()) -> QualityReport:
    """Accept kind=message/page/turn, body/html/text/say, subject, from, url.

    approved_domains must contain exact hostnames the team has reviewed as
    simulator sender/page domains. No subdomain or suffix wildcard matching.
    Unconfigured domains fail closed. No network or domain registration occurs.
    """
    report = QualityReport()
    if not isinstance(artifact, dict):
        report.errors.append('Artifact must be an object')
        return report
    for key in ('subject', 'title', 'html', 'body', 'text', 'say', 'url'):
        if key in artifact and not isinstance(artifact[key], str):
            report.errors.append(f'{key} must be text')
    if report.errors:
        return report
    kind = artifact.get('kind', 'message')
    if kind not in {'message', 'page', 'turn'}:
        report.errors.append('Unsupported artifact kind')
    content = artifact.get('html') or artifact.get('body') or artifact.get('text') or artifact.get('say') or ''
    if not isinstance(content, str) or not content.strip():
        report.errors.append('Missing content')
    text = normalized(' '.join(str(artifact.get(k) or '') for k in
                               ('subject', 'title', 'html', 'body', 'text', 'say', 'from', 'attachments')))
    # Keep tags separate as words, but catch directives split across inline tags.
    visible = re.sub(r'<[^>]*>', '', text)
    directives = [r'\bignore\b.{0,50}\b(instructions|rules|prompt)\b',
                  r'\byou (?:are|are acting as) (?:an? )?(?:ai|llm|language model|chatbot)\b',
                  r'\b(system prompt|developer message|as an ai|simulation override)\b',
                  r'\b(?:reveal|print|show)\b.{0,30}\b(?:hidden prompt|system instructions)\b',
                  r'\[(?:system|assistant|simulator|persona notes)\]',
                  r'<\|(?:im_start|system|assistant)\|>',
                  r'\b(?:override|disregard)\b.{0,40}\b(?:instructions|rules|prompt)\b']
    if any(re.search(p, candidate, re.I) for p in directives for candidate in (text, visible)):
        report.errors.append('AI-directed or simulator-like wording')
    if re.search(r'\b(?:TODO|TBD|lorem ipsum|YOUR_KEY|YOUR_NAME|INSERT_HERE)\b|\{\{[^}]+\}\}|\[(?:name|company|date|link|insert[^\]]*)\]', visible, re.I):
        report.errors.append('Unresolved placeholder text')
    if re.search(r'<\s*(?:script|iframe|object|embed|base)\b|\bon\w+\s*=|javascript\s*:|@import|url\s*\(', text, re.I):
        report.errors.append('Active or externally loaded HTML content')
    if re.search(r'<\s*img\b', text, re.I):
        report.errors.append('Images require asset resolution; unsupported by this gate version')
    if re.search(r'\bBearer\s+[A-Za-z0-9._~+/-]{12,}|\b(?:rv8_|sk-|rc-)[A-Za-z0-9_-]{16,}|\b(?:api[_ -]?key|token)\s*[:=]\s*[A-Za-z0-9_-]{20,}', text, re.I):
        report.errors.append('Possible credential in content; remove before sending')

    allowed = {str(d).lower().rstrip('.') for d in approved_domains}
    urls = re.findall(r'https?://[^\s<>\x22\x27)]+', unescape(text))
    markup = Markup()
    markup.feed(str(content))
    for link in markup.links:
        link = normalized(link)
        if link.startswith('#'):
            continue
        if not link.lower().startswith(('https://', 'http://')):
            report.errors.append('Unsupported hyperlink or resource scheme')
        else:
            urls.append(link)
    if artifact.get('url'):
        urls.append(str(artifact['url']))
    sender = artifact.get('from') or {}
    if not isinstance(sender, dict):
        report.errors.append('Sender must be an object')
        sender = {}
    address = str(sender.get('address') or '')
    if address and not re.fullmatch(r'[^\s@<>]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', address):
        report.errors.append('Malformed sender email address')
    hosts = []
    if '@' in address:
        hosts.append(address.rsplit('@', 1)[1].lower().rstrip('.'))
    for url in urls:
        try:
            parsed = urlsplit(url)
            _ = parsed.port  # validate invalid/non-numeric ports
            host = (parsed.hostname or '').lower().rstrip('.')
            if parsed.scheme not in {'http', 'https'} or not host or parsed.username or parsed.password:
                raise ValueError('Invalid URL')
            hosts.append(host)
        except ValueError:
            report.errors.append('Invalid page or link URL')
    if any(h not in allowed for h in hosts):
        report.errors.append('Sender or link domain is not explicitly approved')
    # Reject non-http hyperlinks, including protocol-relative and file URLs.
    for href in re.findall(r'\bhref\s*=\s*[\x22\x27]([^\x22\x27]+)', text, re.I):
        if not href.startswith(('https://', 'http://', '#')):
            report.errors.append('Unsupported hyperlink scheme')
    if kind == 'page' and not artifact.get('url'):
        report.errors.append('Page URL missing')
    attachments = artifact.get('attachments', [])
    if not isinstance(attachments, list):
        report.errors.append('Attachments must be a list')
    else:
        for item in attachments:
            filename = item.get('filename') if isinstance(item, dict) else item
            if not isinstance(filename, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ -]{0,79}', filename):
                report.errors.append('Attachment must be a safe filename')
            if isinstance(item, dict) and set(item) - {'filename'}:
                report.errors.append('Only filename-only attachments are supported')
    if kind == 'message' and artifact.get('channel', 'email') == 'email':
        if not artifact.get('subject', '').strip():
            report.errors.append('Email subject missing')
        if not sender.get('name') or not address:
            report.warnings.append('Sender name/address missing; craft review needed')
        if not re.search(r'\b(regards|best|thanks|sincerely|cheers)\b', visible, re.I):
            report.warnings.append('Signature not detected; craft review needed')
    report.warnings.append('Tone, factual accuracy and visual craft require separate review; no craft score inferred')
    report.errors = list(dict.fromkeys(report.errors))
    return report


def require_quality(artifact: dict, **kwargs) -> QualityReport:
    report = check_artifact(artifact, **kwargs)
    if not report.passed:
        raise ValueError('; '.join(report.errors))
    return report
