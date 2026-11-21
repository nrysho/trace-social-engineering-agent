"""Offline rendering evidence. Never sends a message or makes an API request.

python -m quality.cli render quality/samples/valid_message.json --context quality/samples/context.json --output output/quality/render
"""
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import re
from .checks import check_artifact


def document(artifact):
    """Wrap an email or landing page with visible sender/URL context."""
    kind = artifact.get('kind', 'message')
    if kind == 'page':
        heading = 'URL: ' + str(artifact.get('url', ''))
        title = str(artifact.get('title', 'Landing page'))
    else:
        sender = artifact.get('from') or {}
        heading = f"From: {sender.get('name', 'Not recorded')} <{sender.get('address', 'Not recorded')}>"
        title = str(artifact.get('subject', ''))
    content = str(artifact.get('html') or artifact.get('body') or artifact.get('text') or artifact.get('say') or '')
    is_html = 'html' in artifact or bool(re.search(r'<[a-zA-Z][^>]*>', content))
    if not is_html:
        content = '<div style="white-space:pre-wrap">' + escape(content) + '</div>'
    if kind == 'page':
        for name in artifact.get('fields', []):
            content += '<p><label>' + escape(str(name)) + '<br><input disabled aria-label="' + escape(str(name), quote=True) + '"></label></p>'
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src \'none\'; form-action \'none\'">'
            '<title>TRACE craft evidence</title></head>'
            '<body style="margin:0;background:#eef1f4;color:#17212b;font:16px Arial,sans-serif">'
            '<header style="padding:20px;border-bottom:1px solid #bcc4cc;background:white">'
            '<div style="font-size:13px">Offline practice render - no official craft rating</div>'
            f'<p style="overflow-wrap:anywhere">{escape(heading)}</p><h1 style="font-size:21px">{escape(title)}</h1></header>'
            f'<main style="padding:24px;background:white;overflow-wrap:anywhere">{content}</main></body></html>')


def render_review(artifacts, output, *, approved_domains=(), browser_channel='chrome'):
    from playwright.sync_api import sync_playwright
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'official_craft_score': None, 'network': 'blocked', 'javascript': False,
                'limitations': ['Images/assets are not supported; image artifacts are blocked.',
                                'Checks are heuristic. Sender authenticity, facts, tone and layout require visual review.',
                                'This tool records evidence; it is not yet a pre-send screenshot stage.'],
                'items': []}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=browser_channel, headless=True)
        try:
            for index, artifact in enumerate(artifacts, 1):
                report = check_artifact(artifact, approved_domains=approved_domains)
                width = 1200 if artifact.get('kind') == 'page' else 700
                record = {'index': index, 'width_px': width, 'quality': report.to_dict(),
                          'sha256': hashlib.sha256(json.dumps(artifact, sort_keys=True).encode()).hexdigest()}
                manifest['items'].append(record)
                if not report.passed:
                    record['render_status'] = 'blocked'
                    continue
                context = browser.new_context(viewport={'width': width, 'height': 800},
                                              device_scale_factor=1, java_script_enabled=False,
                                              service_workers='block')
                try:
                    context.route('**/*', lambda route: route.abort())
                    page = context.new_page()
                    page.set_content(document(artifact), wait_until='load')
                    record['horizontal_overflow'] = page.locator('body').evaluate(
                        '(el) => el.scrollWidth > window.innerWidth')
                    record['screenshot'] = f'item-{index:03d}.png'
                    page.screenshot(path=str(output / record['screenshot']), full_page=True, animations='disabled')
                    record['render_status'] = 'saved'
                finally:
                    context.close()
        finally:
            browser.close()
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest
