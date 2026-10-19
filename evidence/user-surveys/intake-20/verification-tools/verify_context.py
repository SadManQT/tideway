"""Verify supplied export linkage and capture current context, never backdate it.

Original study CSVs stay private. No downloads, model inference or financial writes.
Run from a source checkout with the private intake present. Existing captures are
immutable: use --check to verify their bytes, or --out for a separate new capture.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'scripts/user_study.py').is_file())
sys.path.insert(0, str(ROOT))
from scripts.local_demo_model import MODEL_PROFILES, RUNTIMES, RUNTIME_RELEASE, digest
from scripts.verify_submission import source_digest

PUBLIC = ROOT / 'evidence/user-surveys/intake-20'
PRIVATE = ROOT / 'evidence/private/survey-intake-20'
SOURCE_PATHS = ['run.py', '.github/workflows/ci.yml', 'Dockerfile', '.dockerignore',
                'tideway', 'tests', 'web', 'scripts']


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_exports():
    analysis = json.loads((PUBLIC / 'analysis.json').read_text(encoding='utf-8'))
    receipt = json.loads((PRIVATE / 'manifest.json').read_text(encoding='utf-8'))
    metadata = (PUBLIC / 'session-metadata.json').read_bytes()
    require(hashlib.sha256(metadata).hexdigest() == analysis['metadata_followup']['sha256'],
            'Session metadata does not match the analysis hash')
    initial = (PRIVATE / 'analysis-before-session-metadata.json').read_bytes()
    require(hashlib.sha256(initial).hexdigest() == analysis['metadata_followup']['initial_analysis_sha256'],
            'Initial aggregate snapshot hash differs')
    old = json.loads(initial)
    require(old['sme']['tasks'] == analysis['sme']['tasks'] and old['sme']['sus'] == analysis['sme']['sus']
            and old['security']['cases'] == analysis['security']['cases'], 'Calculated observations changed')
    rows, results = {}, {}
    for kind, source in analysis['sources'].items():
        path = PRIVATE / source['filename']
        require(digest(path) == source['sha256'] == receipt['sources'][kind]['sha256'],
                'Archived CSV hash differs from the intake and public analysis')
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            rows[kind] = list(reader)
            require(reader.fieldnames == source['columns'], 'Source CSV columns changed')
        require(len(rows[kind]) == source['rows'], 'CSV row count differs')
        require(all(None not in row and all(v is not None for v in row.values()) for row in rows[kind]),
                'Malformed CSV row')
        ids = [row['participant_id'] for row in rows[kind]]
        require(len(ids) == len(set(ids)), 'Duplicate anonymous IDs')
        download = Path.home() / 'Downloads' / source['filename']
        require(not download.exists() or digest(download) == source['sha256'],
                'Download differs from the preserved source; review it as a new version')
        results[kind] = {'filename': source['filename'], 'rows': len(ids),
                         'sha256': source['sha256'], 'archived_bytes_match_intake': True,
                         'download_copy_checked': download.exists()}
    maps = {kind: {row['participant_id']: row for row in values} for kind, values in rows.items()}
    links = []
    for number in range(1, 11):
        sme_id, security_id = f'P{number + 20}', f'S{number:02d}'
        require(sme_id in maps['sme'] and security_id in maps['security'],
                'Reported overlap references an absent record')
        links.append({'sme_id': sme_id, 'security_id': security_id,
                      'basis': 'Team-provided correspondence, not independently verified identity',
                      'role_labels_agree': maps['sme'][sme_id]['role'] == maps['security'][security_id]['role']})
    fingerprints = {kind: [{'record_number': index, 'anonymous_id': row['participant_id'],
                            'row_sha256': hashlib.sha256(json.dumps(row, sort_keys=True,
                                                                   ensure_ascii=False).encode()).hexdigest()}
                           for index, row in enumerate(values, 1)] for kind, values in rows.items()}
    private = {'schema_version': 'tideway-private-export-linkage-v1', 'sources': results,
               'records': fingerprints, 'reported_overlap': links,
               'scope': 'Links supplied CSV rows and team-reported cross-cohort IDs only; no real identity map.'}
    return results, private


def current_system():
    command = r'''
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$edgeCandidates = @('C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe','C:\Program Files\Microsoft\Edge\Application\msedge.exe')
$edgeData = @()
foreach ($candidate in $edgeCandidates) {
    if (Test-Path -LiteralPath $candidate) {
        $file = Get-Item -LiteralPath $candidate
        $edgeData += [pscustomobject]@{product_version=$file.VersionInfo.ProductVersion; file_version=$file.VersionInfo.FileVersion; executable_sha256=(Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant(); executable_last_write_utc=$file.LastWriteTimeUtc.ToString('o')}
    }
}
$os = Get-CimInstance Win32_OperatingSystem
$machine = Get-CimInstance Win32_ComputerSystem
[pscustomobject]@{cpu=@(Get-CimInstance Win32_Processor | ForEach-Object {$_.Name.Trim()}); physical_ram_gib=[math]::Round($machine.TotalPhysicalMemory/1GB,2); os=$os.Caption; os_version=$os.Version; os_build=$os.BuildNumber; architecture=$os.OSArchitecture; edge=$edgeData} | ConvertTo-Json -Depth 5 -Compress
'''
    result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, text=True, encoding='utf-8', timeout=30, check=True)
    data = json.loads(result.stdout.lstrip('\ufeff'))
    require(data.get('edge'), 'No Microsoft Edge executable was found at the standard locations')
    data['scope'] = 'Measured on the current audit machine; compare the measured CPU/RAM fields with the reported Intel Core i5/16 GB survey laptop. The two contexts are not established as the same machine. Browser version is not assigned retrospectively to the survey.'
    return data


def runtime_artifacts(cache):
    profile = MODEL_PROFILES['qwen3-4b']
    archive, size, expected = RUNTIMES['windows-vulkan']
    model = cache / profile['file']
    runtime = cache / archive
    model_hash, runtime_hash = digest(model), digest(runtime)
    require(model.stat().st_size == profile['bytes'] and model_hash == profile['sha256'],
            'Model cache bytes differ from the pinned artifact')
    require(runtime.stat().st_size == size and runtime_hash == expected,
            'Runtime archive differs from the pinned artifact')
    return {'model_id': profile['id'], 'model_filename': profile['file'],
            'model_revision': profile['revision'], 'model_bytes': model.stat().st_size,
            'model_sha256': model_hash, 'runtime_release': RUNTIME_RELEASE,
            'runtime_archive': archive, 'runtime_archive_bytes': runtime.stat().st_size,
            'runtime_archive_sha256': runtime_hash, 'repository_pins_match': True,
            'model_inference_run': False, 'survey_session_binding_verified': False,
            'scope': 'Fresh integrity measurement of cached compatible Windows artifacts, not a survey-generation log, native MLX adapter, receipt model or proof of participant use.'}


def source_lineage():
    current, _ = source_digest()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    comparisons = []
    for ref in ('cb45bc7', 'e360e8b', '39552f0'):
        revision = subprocess.check_output(['git', 'rev-parse', ref], cwd=ROOT, text=True).strip()
        result = subprocess.run(['git', 'diff', '--quiet', revision, 'HEAD', '--', *SOURCE_PATHS], cwd=ROOT)
        require(result.returncode in (0, 1), 'Git source comparison failed')
        comparisons.append({'commit': revision, 'application_tree_matches_current': result.returncode == 0})
    proof = {}
    for filename in ('evidence/test-summary.json', 'evidence/screens/browser-verification.json'):
        receipt = json.loads((ROOT / filename).read_text(encoding='utf-8'))
        require(receipt['passed'] and receipt['source_tree_sha256'] == current,
                'Stored engineering check does not cover the current application source')
        proof[filename] = digest(ROOT / filename)
    return {'audit_checkout_commit': head, 'application_source_tree_sha256': current,
            'related_commits': comparisons, 'engineering_receipt_sha256': proof,
            'historical_survey_commit': None, 'historical_survey_working_tree': None,
            'scope': 'These commits share the verified application tree. Date or byte equivalence alone does not identify which checkout ran during the survey.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-cache', type=Path)
    parser.add_argument('--out', type=Path, default=PUBLIC / 'verification')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    require(out.is_relative_to(PUBLIC.resolve()), 'Store aggregate capture under this public intake directory')
    sources, linkage = read_exports()
    if args.check:
        manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
        for name, expected in manifest['sha256'].items():
            require(Path(name).name == name and digest(out / name) == expected, 'Captured artifact hash changed')
        require(digest(Path(__file__)) == manifest['collector_sha256'], 'Collector changed since capture')
        require(linkage == json.loads((PRIVATE / 'record-linkage.json').read_text(encoding='utf-8')),
                'Private export linkage changed')
        print('PASS: original export chain, reported overlap references and immutable capture hashes.')
        return
    require(args.model_cache is not None, 'Supply --model-cache for a fresh cache measurement')
    require(not out.exists(), 'Capture already exists; use --check or a new --out directory')
    at = datetime.now(timezone.utc).isoformat()
    system, runtime, lineage = current_system(), runtime_artifacts(args.model_cache), source_lineage()
    findings = {'schema_version': 'tideway-survey-context-verification-v1', 'captured_at_utc': at,
                'scope': 'Current artifact measurements and supplied export linkage; historical session binding is unresolved.',
                'sources': sources, 'record_linkage': {'source_rows_verified': 40,
                    'reported_overlap_references_verified': len(linkage['reported_overlap']),
                    'role_label_differences': sum(not item['role_labels_agree'] for item in linkage['reported_overlap']),
                    'identity_independently_verified': False,
                    'role_note': 'Different role labels do not by themselves prove different people; the correspondence remains team-reported.'},
                'original_observation_sheets_identified': False,
                'survey_commit_verified': False, 'survey_browser_version_verified': False,
                'survey_runtime_verified': False,
                'current_edge_version': system['edge'][0]['product_version'],
                'cache_artifact_integrity_verified': True,
                'completion': 'Export linkage and current context verified; original session provenance cannot be reconstructed from these artifacts alone.'}
    reports = {'verification.json': findings, 'system-info.json': {'captured_at_utc': at, **system},
               'runtime-provenance.json': {'captured_at_utc': at, **runtime},
               'source-lineage.json': {'captured_at_utc': at, **lineage}}
    readable = ('Tideway CURRENT audit context\nCaptured at UTC: ' + at + '\n'
                + 'Edge: ' + system['edge'][0]['product_version'] + '\nCPU: ' + '; '.join(system['cpu'])
                + '\nPhysical RAM GiB: ' + str(system['physical_ram_gib']) + '\nOS: ' + system['os']
                + '\nApplication source SHA-256: ' + lineage['application_source_tree_sha256']
                + '\nScope: current machine only; historical survey laptop/build/browser not established.\n')
    files = {name: encoded(value) for name, value in reports.items()}
    files['system-info.txt'] = readable.encode('utf-8')
    manifest = {'schema_version': 'tideway-survey-context-capture-manifest-v1', 'captured_at_utc': at,
                'collector_sha256': digest(Path(__file__)),
                'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    private_path = PRIVATE / 'record-linkage.json'
    require(not private_path.exists() or private_path.read_bytes() == encoded(linkage),
            'Refusing to replace different private record linkage')
    private_path.write_bytes(encoded(linkage))
    out.mkdir(parents=True)
    for name, data in {**files, 'manifest.json': encoded(manifest)}.items():
        with (out / name).open('xb') as handle:
            handle.write(data)
    print(json.dumps(findings, indent=2))


if __name__ == '__main__':
    main()
