"""Local Person 5 checks. No model or simulator requests."""
import argparse
from html import escape
import json
from pathlib import Path
from .integration import prepare_message, prepare_page, checked_turn, QualityBlocked
from .results import summarize_run, decision_records, report_html
from .presentation import issue_sections


def load(path):
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() == '.jsonl':
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def preview(message, report):
    """Inspector escapes body source, including rejected HTML. Not a craft render."""
    sender = message.get('sender', message.get('from', {}))
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            '<title>Person 5 local QA preview</title><style>body{max-width:900px;margin:32px auto;padding:20px;'
            'font:16px/1.6 Arial;color:#182633}pre{white-space:pre-wrap;overflow-wrap:anywhere;'
            'background:#f0f3f6;padding:20px}</style><h1>Local QA: ' +
            ('PASS' if report['passed'] else 'BLOCK') + '</h1><p>Offline inspector, not a send or official rating. '
            'HTML source is escaped here; use render for craft screenshots.</p><h2>Sender</h2><pre>' +
            escape(json.dumps(sender, indent=2)) + '</pre><h2>Subject</h2><p>' +
            escape(str(message.get('subject', ''))) + '</p><h2>Body</h2><pre>' +
            escape(str(message.get('body', ''))) + '</pre>' + issue_sections(report) + '<h2>Machine-readable report</h2><pre>' +
            escape(json.dumps(report, indent=2)) + '</pre></html>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('validate', 'page', 'turn', 'render'):
        p = sub.add_parser(command)
        p.add_argument('file', type=Path)
        p.add_argument('--context', type=Path, required=True)
        p.add_argument('--output', type=Path)
    p = sub.add_parser('report')
    p.add_argument('file', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('profile')
    p.add_argument('file', type=Path)
    p.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        data = load(args.file)
        if args.command == 'report':
            summary, decisions = summarize_run(data), decision_records(data)
            args.output.mkdir(parents=True, exist_ok=True)
            for name, value in [('summary', summary), ('decisions', decisions)]:
                (args.output / (name + '.json')).write_text(json.dumps(value, indent=2), encoding='utf-8')
            (args.output / 'report.html').write_text(report_html(summary, decisions), encoding='utf-8')
            print(json.dumps(summary, indent=2))
            return 0
        if args.command == 'profile':
            from .profile_review import review_profile
            report = review_profile(data).to_dict()
            if args.output:
                args.output.mkdir(parents=True, exist_ok=True)
                (args.output/'profile-quality.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report, indent=2))
            return 0 if report['passed'] else 2
        context = load(args.context)
        if args.command in {'validate', 'render'}:
            prepared = prepare_message(data, context)
            report = prepared['report']
        elif args.command == 'page':
            _, quality = prepare_page(data, context)
            report = quality.to_dict()
        else:
            try:
                checked_turn(data, context)
                report = {'passed': True, 'errors': [], 'warnings': []}
            except QualityBlocked as exc:
                report = exc.report.to_dict()
        if args.output:
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / 'quality.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            if args.command == 'validate':
                (args.output / 'preview.html').write_text(preview(data, report), encoding='utf-8')
        if args.command == 'render' and report['passed']:
            if not args.output:
                parser.error('render requires --output')
            from .render import render_review
            artifacts = [{'kind': 'message', **prepared['payload']}]
            if prepared['page']:
                artifacts.append({'kind': 'page', **prepared['page']})
            manifest = render_review(artifacts, args.output, approved_domains=
                                     context.get('approved_sender_domains', []) + context.get('approved_link_hosts', []))
            if any(not item['quality']['passed'] or not item.get('visual_checks_passed', False) for item in manifest['items']):
                print(json.dumps({'passed': False, 'stage': 'render',
                                  'manifest': str(args.output/'manifest.json'),
                                  'note': 'Quality or layout checks failed; inspect manifest and screenshots.'}, indent=2))
                return 2
        print(json.dumps(report, indent=2))
        return 0 if report['passed'] else 2
    except (OSError, ValueError, TypeError, ImportError) as exc:
        # Do not echo malformed input or provider/secret material in exception strings.
        if isinstance(exc, QualityBlocked):
            print(json.dumps(exc.report.to_dict(), indent=2))
            return 2
        parser.exit(1, f'Local QA error ({type(exc).__name__}); check input shape, paths and optional renderer installation.\n')


if __name__ == '__main__':
    raise SystemExit(main())
