"""Verify distributed bytes and boot/test a fresh extraction without Git/site packages."""
from __future__ import annotations
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_submission_package import allowed_source
from scripts.verify_submission import source_digest

MANIFEST_PATH = 'Tideway/package-manifest.json'
DELIVERABLES = {'pitch.pdf', 'architecture.pdf', 'security-assessment.pdf',
                'submission-notes.pdf', 'MODEL_CARD.md', 'SETUP_WINDOWS_MAC.md'}


def inspect_archive(z):
    """Validate every entry before extraction, including unmanifested extras."""
    names = z.namelist()
    if len(names) != len(set(names)) or len(names) != len({name.casefold() for name in names}):
        raise RuntimeError('Duplicate or case-colliding ZIP entries')
    for info in z.infolist():
        name = info.filename
        path = PurePosixPath(name)
        if (not name.startswith('Tideway/') or '\\' in name or path.is_absolute()
                or '..' in path.parts or path.as_posix() != name or any(':' in p for p in path.parts)
                or any(ord(c) < 32 for c in name) or info.is_dir()
                or ((info.external_attr >> 16) & 0o170000) == 0o120000):
            raise RuntimeError(f'Unsafe ZIP entry: {name}')
        if name.startswith('Tideway/source/'):
            if not allowed_source(name.removeprefix('Tideway/source/')):
                raise RuntimeError(f'Forbidden source entry: {name}')
        elif name not in {MANIFEST_PATH, 'Tideway/README-FIRST.md'}:
            if name.removeprefix('Tideway/deliverables/') not in DELIVERABLES or not name.startswith('Tideway/deliverables/'):
                raise RuntimeError(f'Unexpected deliverable entry: {name}')
    try:
        manifest = json.loads(z.read(MANIFEST_PATH))
        records = manifest['files']
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError('Missing or invalid package manifest') from exc
    if not isinstance(records, dict) or set(names) != set(records) | {MANIFEST_PATH} or MANIFEST_PATH in records:
        raise RuntimeError('ZIP entries must exactly match the manifest')
    for name, record in records.items():
        if (not isinstance(record, dict) or not isinstance(record.get('bytes'), int)
                or not isinstance(record.get('sha256'), str) or not re.fullmatch('[a-f0-9]{64}', record['sha256'])):
            raise RuntimeError(f'Invalid manifest record: {name}')
        data = z.read(name)
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise RuntimeError(f'Hash or size mismatch: {name}')
    return manifest


def isolated_environment():
    """Keep OS process essentials; omit credential/model/PYTHONPATH overrides."""
    essential = {'PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT',
                 'TEMP', 'TMP', 'TMPDIR', 'LANG', 'LC_ALL', 'LC_CTYPE'}
    env = {k: v for k, v in os.environ.items() if k.upper() in essential}
    env.update(PYTHONUTF8='1', TIDEWAY_HOST='127.0.0.1')
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', nargs='?', default=str(ROOT / 'dist/Tideway-submission.zip'))
    args = parser.parse_args()
    archive = Path(args.archive).resolve()
    with tempfile.TemporaryDirectory(prefix='tideway-distributed-') as directory:
        work = Path(directory)
        with zipfile.ZipFile(archive) as z:
            if z.testzip():
                raise RuntimeError('Corrupt archive')
            manifest = inspect_archive(z)
            z.extractall(work)
        source = work / 'Tideway/source'
        if (source / '.git').exists() or (source / 'submission-team.json').exists():
            raise RuntimeError('Private workstation state found in extraction')
        actual_digest, _files = source_digest(source)
        if actual_digest != manifest.get('source_tree_sha256'):
            raise RuntimeError('Extracted source differs from the tested/browser-verified source digest')
        roster = json.loads((source / 'submission-team.public.json').read_text(encoding='utf-8'))
        if len(roster['members']) != 5:
            raise RuntimeError('The five confirmed public members must be reproducible')
        env = isolated_environment()
        result = subprocess.run([sys.executable, '-S', '-m', 'unittest', 'discover', '-s', 'tests', '-q'],
                                cwd=source, env=env, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        # Bind an unused local port; only the disposable extracted database is written.
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
        log = work / 'server.log'
        with log.open('w') as output:
            process = subprocess.Popen([sys.executable, '-S', 'run.py', '--port', str(port), '--db', 'data/fresh.sqlite3'],
                                       cwd=source, env=env, stdout=output, stderr=subprocess.STDOUT)
        checks = {}
        asset_checks = {}
        binary_assets = {'/fonts/space-grotesk.woff2': 'font/woff2', '/fonts/unbounded.woff2': 'font/woff2',
                         '/fonts/jetbrains-mono.woff2': 'font/woff2', '/img/hero.webp': 'image/webp'}
        try:
            for _ in range(80):
                try:
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
                    connection.request('GET', '/api/config'); response = connection.getresponse()
                    data = json.loads(response.read()); connection.close()
                    if response.status == 200:
                        break
                except (OSError, json.JSONDecodeError):
                    if process.poll() is not None:
                        raise RuntimeError(log.read_text(encoding='utf-8'))
                    time.sleep(.1)
            else:
                raise RuntimeError('Extracted server did not start')
            for route, expected in (('/', 200), ('/guide', 404), ('/guide.html', 404), ('/guide.css', 404),
                                    ('/guide.js', 404), ('/personal-prep/project-guide/guide.html', 404), ('/benchmarks/tidepay.json', 200),
                                    ('/benchmarks/tidepay-deployed.json', 200),
                                    ('/benchmarks/tidepay-deployed-reliability.svg', 200),
                                    *[(route, 200) for route in binary_assets],
                                    ('/api/dashboard?business_id=shapla-services', 401)):
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                connection.request('GET', route); response = connection.getresponse()
                body = response.read(); content_type = response.getheader('Content-Type'); connection.close()
                checks[route] = response.status
                if response.status != expected:
                    raise RuntimeError(f'Unexpected HTTP status for {route}: {response.status}')
                if route in binary_assets:
                    if content_type != binary_assets[route] or not body:
                        raise RuntimeError(f'Invalid binary asset response for {route}')
                    asset_checks[route] = {'content_type': content_type, 'bytes': len(body)}
            if data['tidelm']['available'] is not False:
                raise RuntimeError('Fresh -S extraction unexpectedly enabled optional model inference')
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        report = {'passed': True, 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                  'source_tree_sha256': manifest['source_tree_sha256'], 'files_verified': len(manifest['files']),
                  'python': sys.version, 'git_present': False, 'site_packages_enabled': False,
                  'private_workstation_files_required': False, 'http_checks': checks,
                  'binary_asset_checks': asset_checks,
                  'test_result': result.stderr.strip().splitlines()[-5:]}
        (ROOT / 'dist').mkdir(exist_ok=True)
        path = ROOT / 'dist/extraction-verification.json'
        path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
