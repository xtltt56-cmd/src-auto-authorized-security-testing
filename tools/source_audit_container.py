"""Trusted container driver. Never import/run target modules or project hooks.

Only pinned wheels and local rules are used, within a network=none container.
Raw analyzer output remains in tmpfs; stdout contains allowlisted metadata only.
"""
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path


def tool(args, name):
    path = Path('/out/' + name + '.json')
    env = dict(os.environ, PYTHONPATH='/tools', SEMGREP_SEND_METRICS='off', SEMGREP_ENABLE_VERSION_CHECK='0',
               SEMGREP_SETTINGS_FILE='/out/semgrep-settings.yml', HOME='/out', NO_COLOR='1')
    env.pop('SEMGREP_APP_TOKEN', None)
    with path.open('wb') as output, Path('/out/driver.err').open('wb') as errors:
        result = subprocess.run(args, cwd='/out', env=env, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=errors, timeout=180)
    if result.returncode not in (0, 1) or path.stat().st_size > 1048576:
        raise RuntimeError('source_tool_failed')
    raw = json.loads(path.read_text())
    rows = []
    for row in raw.get('results', []):
        if name == 'bandit':
            rows.append({k: row.get(k) for k in ('filename', 'test_id', 'line_number', 'issue_severity')})
        else:
            rows.append({'path': row.get('path'), 'check_id': row.get('check_id'),
                         'start': {'line': row.get('start', {}).get('line')},
                         'extra': {'severity': row.get('extra', {}).get('severity')}})
    scanned = [x for x in raw.get('metrics', {}) if x.startswith('/input/')] if name == 'bandit' else raw.get('paths', {}).get('scanned', [])
    skipped = []
    for row in raw.get('paths', {}).get('skipped', []):
        if isinstance(row, dict) and str(row.get('path', '')).startswith('/input/'):
            reason = str(row.get('reason', '')).lower()
            reason = 'timeout' if 'timeout' in reason else 'parse_error' if 'parse' in reason else 'excluded' if 'ignore' in reason else 'analysis_failed'
            skipped.append({'path': row['path'], 'reason': reason})
    return {'results': rows, 'errors': len(raw.get('errors', [])), 'version': raw.get('version'), 'scanned': scanned, 'skipped': skipped}


def main():
    for wheel in sorted(Path('/trusted/wheels').glob('*.whl')):
        with zipfile.ZipFile(wheel) as archive:
            # The host verifies official wheel hashes before mounting these.
            if any(x.startswith('/') or '..' in Path(x).parts for x in archive.namelist()):
                raise RuntimeError('invalid_wheel')
            archive.extractall('/tools')
    languages = json.loads(Path('/input-manifest.json').read_text())['languages']
    result = {}
    if 'python' in languages:
        result['bandit'] = tool([sys.executable, '-m', 'bandit', '-r', '/input', '--ini', '/trusted/empty.ini',
                               '-c', '/trusted/bandit.json', '--ignore-nosec', '-f', 'json', '-q'], 'bandit')
    if 'javascript' in languages:
        result['semgrep'] = tool(['semgrep', 'scan', '--config', '/trusted/rules.json', '--metrics=off',
                                 '--disable-version-check', '--oss-only', '--no-git-ignore', '--no-rewrite-rule-ids',
                                 '--json', '--quiet', '--jobs', '1', '--max-target-bytes', '1048576',
                                 '--timeout', '10', '/input'], 'semgrep')
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'driver_error': 'source_tool_failed'}))
        sys.exit(2)
