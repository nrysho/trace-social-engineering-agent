"""Escaped reviewer explanations; does not alter validation or invent decisions."""
from html import escape
import json


def remedy(error):
    low = error.lower()
    for needle, action in [
        ('placeholder', 'Replace template tokens with supported facts, or remove the unfinished text.'),
        ('ai-directed', 'Write to the person; remove instructions addressed to the simulator or model.'),
        ('sender', 'Provide a complete sender and use independently reviewed sender configuration.'),
        ('domain', 'Check sender and link permissions separately; do not approve a real organisation domain.'),
        ('link', 'Set a complete approved destination and make any displayed URL agree with it.'),
        ('credential', 'Remove possible key/token material before any send or screen share.'),
        ('subject', 'Provide a nonempty, single-line subject.'),
        ('page', 'Check the page URL, content and field-name list against the shared LandingPage contract.'),
        ('attachments', 'Use the supported count of filename-only attachment declarations.'),
    ]:
        if needle in low:
            return action
    return 'Check this field against the shared schema and integration guide; do not bypass the gate.'


def issue_sections(report):
    errors, warnings = report.get('errors', []), report.get('warnings', [])
    html = '<h2>What needs fixing</h2>' if errors else '<h2>Blocking checks</h2><p>No blocking issues detected.</p>'
    if errors:
        html += '<ol>' + ''.join('<li><b>' + escape(str(e)) + '</b><br>' + escape(remedy(str(e))) + '</li>' for e in errors) + '</ol>'
    if warnings:
        html += '<h2>Review warnings</h2><ul>' + ''.join('<li>' + escape(str(w)) + '</li>' for w in warnings) + '</ul>'
    return html


def revision_preview(before, after, initial_report, final_report, *, attempts):
    changed = [field for field in sorted(set(before) | set(after)) if before.get(field) != after.get(field)]
    def draft(title, data):
        return '<section><h2>' + title + '</h2><p><b>Subject:</b> ' + escape(str(data.get('subject', ''))) + '</p><pre>' + escape(str(data.get('body', ''))) + '</pre></section>'
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            '<title>Person 5 correction evidence</title><style>body{max-width:1000px;margin:32px auto;padding:20px;'
            'font:17px/1.6 Arial;color:#182633}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f3f6;'
            'padding:20px}section{border-top:1px solid #ccd2d8;padding:12px 0}li{margin-bottom:12px}</style>'
            '<h1>Automatic correction: attempt ' + str(attempts) + ' passed</h1>'
            '<p>SYNTHETIC OFFLINE EXAMPLE. A fake writer received feedback; no model or simulator was called.</p>'
            '<p>Changed fields: ' + escape(', '.join(changed) or 'None') + '</p>' +
            issue_sections(initial_report) + draft('Original rejected draft', before) +
            draft('Accepted revision', after) + '<h2>Final checks</h2><pre>' +
            escape(json.dumps(final_report, indent=2)) + '</pre></html>')
