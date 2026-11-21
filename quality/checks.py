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
        self.anchors = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            self.anchor = [dict(attrs).get('href', ''), '']
        for name, value in attrs:
            if name.lower() in {'href', 'action', 'src', 'srcset', 'poster', 'data'} and value:
                self.links.append(value)

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor[1] += data

    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self.anchor is not None:
            self.anchors.append(self.anchor)
            self.anchor = None

    def close(self):
        super().close()
        if self.anchor is not None:
            self.anchors.append(self.anchor)
            self.anchor = None


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
    for key in ('kind', 'channel', 'subject', 'title', 'html', 'body', 'text', 'say', 'url'):
        if key in artifact and not isinstance(artifact[key], str):
            report.errors.append(f'{key} must be text')
    if report.errors:
        return report
    if sum(len(artifact.get(key, '').encode('utf-8')) for key in ('subject', 'title', 'html', 'body', 'text', 'say')) > 2 * 1024 * 1024:
        report.errors.append('Content exceeds 2 MB input limit')
        return report
    if any(c in artifact.get('subject', '') for c in '\r\n'):
        report.errors.append('Email subject must be a single line')
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
                  r'\b(system prompt|developer message|simulation override)\b',
                  r'\bas an ai(?:\s*[,;:]|\s+(?:you|assistant|model|must|should)\b)',
                  r'\b(?:reveal|print|show)\b.{0,30}\b(?:hidden prompt|system instructions)\b',
                  r'\[(?:system|assistant|simulator|persona notes)\]',
                  r'<\|(?:im_start|system|assistant)\|>',
                  r'\b(?:override|disregard)\b.{0,40}\b(?:instructions|rules|prompt)\b']
    if any(re.search(p, candidate, re.I) for p in directives for candidate in (text, visible)):
        report.errors.append('AI-directed or simulator-like wording')
    if (re.search(r'\b(?:TODO|TBD|lorem ipsum|YOUR_KEY|YOUR_NAME|INSERT_HERE)\b|\{\{[^}]+\}\}|\[(?:name|company|date|link|insert[^\]]*)\]', visible, re.I)
            or re.search(r'<(?:name|first_name|company|date|link)>', text, re.I)):
        report.errors.append('Unresolved placeholder text')
    if re.search(r'<\s*(?:script|iframe|object|embed|base)\b|\bon\w+\s*=|javascript\s*:|@import|url\s*\(', text, re.I):
        report.errors.append('Active or externally loaded HTML content')
    if re.search(r'<\s*img\b', text, re.I):
        report.warnings.append('Inspect image assets in offline craft rendering')
    if re.search(r'\bBearer\s+[A-Za-z0-9._~+/-]{12,}|\b(?:rv8_|sk-|rc-)[A-Za-z0-9_-]{16,}|\b(?:api[_ -]?key|token)\s*[:=]\s*[A-Za-z0-9_-]{20,}', text, re.I):
        report.errors.append('Possible credential in content; remove before sending')

    allowed = {str(d).lower().rstrip('.') for d in approved_domains}
    urls = re.findall(r'https?://[^\s<>\x22\x27)]+', unescape(text), re.I)
    markup = Markup()
    markup.feed(str(content))
    markup.close()
    for target, label in markup.anchors:
        if not isinstance(target, str) or not target.strip() or target.strip() == '#':
            report.errors.append('Link target missing or placeholder')
            continue
        label = normalized(label)
        if re.fullmatch(r'(?:https?://)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?::\d+)?(?:[/?#]\S*)?', label):
            try:
                shown = urlsplit(label if '://' in label else 'https://' + label)
                actual = urlsplit(target)
                if (shown.hostname != actual.hostname or
                    ('://' in label and shown.scheme != actual.scheme) or
                    (shown.port is not None and shown.port != actual.port) or
                    (shown.query and shown.query != actual.query) or
                    (shown.path.rstrip('/') and shown.path.rstrip('/') != actual.path.rstrip('/'))):
                    report.warnings.append('Visible link address does not match destination')
            except ValueError:
                report.warnings.append('Malformed visible link address')
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
        if not href.lower().startswith(('https://', 'http://', '#')):
            report.errors.append('Unsupported hyperlink scheme')
    if kind == 'page' and not artifact.get('url'):
        report.errors.append('Page URL missing')
    attachments = artifact.get('attachments', [])
    if not isinstance(attachments, list):
        report.errors.append('Attachments must be a list')
    else:
        if len(attachments) > 10:
            report.errors.append('At most 10 attachments are supported per message')
        for item in attachments:
            filename = item.get('filename') if isinstance(item, dict) else item
            if not isinstance(filename, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ -]{0,79}', filename):
                report.errors.append('Attachment must be a safe filename')
            if isinstance(filename, str) and re.search(r'\.(?:exe|dll|msi|bat|cmd|ps1|vbs|js|scr|lnk|hta|jar|docm|xlsm|pptm)$', filename, re.I):
                report.errors.append('Executable or macro attachment forbidden')
            if isinstance(item, dict) and set(item) - {'filename'}:
                report.errors.append('Only filename-only attachments are supported')
    if kind == 'message' and artifact.get('channel', 'email') == 'email':
        if not artifact.get('subject', '').strip():
            report.warnings.append('Email subject missing')
        if not sender.get('name') or not address:
            report.warnings.append('Sender name/address missing; craft review needed')
        if not re.search(r'\b(regards|best|thanks|sincerely|cheers)\b', visible, re.I):
            report.warnings.append('Signature not detected; craft review needed')
    channel = artifact.get('channel', 'email')
    if kind == 'message':
        if channel not in {'email','calendar_invite','shared_document'} and artifact.get('subject','').strip():
            report.warnings.append('This channel normally has no subject')
        if channel in {'sms','whatsapp','signal','telegram','imessage','slack','teams_chat','live_chat'} and len(visible) > 320:
            report.warnings.append('Message is long for SMS/chat')
        if channel == 'calendar_invite' and not artifact.get('subject','').strip():
            report.warnings.append('Calendar invite title missing')
        asks = len(re.findall(r'\b(?:please\s+(?:open|reply|confirm|send|sign)|sign in|could you|can you)\b', visible, re.I))
        if asks != 1:
            report.warnings.append('Inspect whether there is one clear ask')
        if channel == 'email' and not re.search(r'\b(?:unsubscribe|privacy|registered|address|company)\b', visible, re.I):
            report.warnings.append('Company footer not detected; inspect whether appropriate for this sender')
    report.errors = list(dict.fromkeys(report.errors))
    return report


def require_quality(artifact: dict, **kwargs) -> QualityReport:
    report = check_artifact(artifact, **kwargs)
    if not report.passed:
        raise ValueError('; '.join(report.errors))
    return report
