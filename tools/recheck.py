#!/usr/bin/env python3
"""Sift vault recheck — report cards near or past expiration.

Usage:
    recheck.py [vault-path] [--within-days N] [--include-scripts] [--json]

Default: scan skills/{research,debug,decisions}/*.md (scripts cards have no
required `expires` field per Sift schema, so they're skipped by default).
Reports cards expiring within 30 days.

Exit code 0 if all scanned cards are healthy, 1 if any are expired or near.

This is a report-only tool. It does not auto-dispatch a recheck agent —
that's a future feature. Today it tells you which cards need attention so
you (or a downstream agent) can run the actual investigation.
"""
import sys
import os
import re
import glob
import json
import argparse
from datetime import date, datetime


def parse_frontmatter(path):
    try:
        import yaml
    except ImportError:
        print("ERROR: pyyaml not installed. Run: pip install pyyaml",
              file=sys.stderr)
        sys.exit(2)

    class StringDateLoader(yaml.SafeLoader):
        pass
    StringDateLoader.add_constructor(
        'tag:yaml.org,2002:timestamp',
        lambda loader, node: loader.construct_scalar(node)
    )

    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None

    m = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not m:
        return None
    try:
        return yaml.load(m.group(1), Loader=StringDateLoader)
    except yaml.YAMLError:
        return None


def find_cards(vault, include_scripts):
    dirs = ['research', 'debug', 'decisions']
    if include_scripts:
        dirs.append('scripts')

    for d in dirs:
        for path in sorted(glob.glob(os.path.join(vault, 'skills', d, '*.md'))):
            if path.endswith('.template.md'):
                continue
            fm = parse_frontmatter(path)
            if fm is None or 'expires' not in fm:
                continue
            try:
                exp_str = str(fm['expires']).strip().strip("'\"")
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
            except (ValueError, AttributeError):
                continue
            days = (exp_date - date.today()).days
            yield path, fm, days


def make_entry(rel_path, fm, days):
    triggers = fm.get('recheck-trigger', [])
    if isinstance(triggers, str):
        triggers = [triggers]
    return {
        'path': rel_path,
        'type': str(fm.get('type', 'unknown')),
        'expires': str(fm.get('expires')),
        'days_to_expire': days,
        'recheck_trigger': triggers,
        'problem': str(fm.get('problem', '') or fm.get('context', '') or '')[:120],
    }


def print_card_block(entries, indent='    '):
    for e in entries:
        print(f"{indent}{e['path']}")
        if e['days_to_expire'] < 0:
            print(f"{indent}  expires: {e['expires']}  ({-e['days_to_expire']} days ago)")
        else:
            print(f"{indent}  expires: {e['expires']}  (in {e['days_to_expire']} days)")
        if e['problem']:
            print(f"{indent}  about:   {e['problem']}")
        if e['recheck_trigger']:
            print(f"{indent}  recheck if: {e['recheck_trigger'][0]}")
            for t in e['recheck_trigger'][1:]:
                print(f"{indent}           or: {t}")


def main():
    parser = argparse.ArgumentParser(
        description="Sift recheck — report cards near or past expiration"
    )
    parser.add_argument('vault', nargs='?', default='.',
                        help='Vault path (default: cwd)')
    parser.add_argument('--within-days', type=int, default=30,
                        help='Report cards expiring within N days (default: 30)')
    parser.add_argument('--include-scripts', action='store_true',
                        help='Also scan scripts/ cards (not required by sift schema)')
    parser.add_argument('--json', action='store_true',
                        help='Output JSON (for dashboards / further processing)')
    args = parser.parse_args()

    vault = os.path.abspath(args.vault)
    expired = []
    nearing = []
    healthy = []

    for path, fm, days in find_cards(vault, args.include_scripts):
        rel = os.path.relpath(path, vault)
        entry = make_entry(rel, fm, days)
        if days < 0:
            expired.append(entry)
        elif days <= args.within_days:
            nearing.append(entry)
        else:
            healthy.append(entry)

    expired.sort(key=lambda x: x['days_to_expire'])
    nearing.sort(key=lambda x: x['days_to_expire'])
    healthy.sort(key=lambda x: x['days_to_expire'])

    if args.json:
        result = {
            'vault': vault,
            'scanned_at': datetime.now().isoformat(),
            'within_days': args.within_days,
            'include_scripts': args.include_scripts,
            'summary': {
                'expired': len(expired),
                'nearing': len(nearing),
                'healthy': len(healthy),
                'total': len(expired) + len(nearing) + len(healthy),
            },
            'expired': expired,
            'nearing': nearing,
            'healthy': healthy,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1 if (expired or nearing) else 0)

    total = len(expired) + len(nearing) + len(healthy)
    scope = "research / debug / decisions"
    if args.include_scripts:
        scope += " / scripts"
    print()
    print(f"  Sift recheck — vault: {vault}")
    print(f"  scanned {total} cards with `expires` ({scope})")
    print()

    if expired:
        print(f"  🔴 {len(expired)} EXPIRED — re-verify before citing")
        print_card_block(expired)
        print()

    if nearing:
        print(f"  🟡 {len(nearing)} expiring within {args.within_days} days")
        print_card_block(nearing)
        print()

    if healthy:
        next_expire = healthy[0]
        print(f"  🟢 {len(healthy)} healthy")
        print(f"     next expiration: {next_expire['expires']} "
              f"({next_expire['days_to_expire']} days) "
              f"— {next_expire['path']}")

    if total == 0:
        print("  no cards with `expires` field found")
        print("  (research/debug/decisions cards require expires per sift schema;")
        print("   scripts cards do not — use --include-scripts to scan them too)")

    print()
    sys.exit(1 if (expired or nearing) else 0)


if __name__ == '__main__':
    main()
