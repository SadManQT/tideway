"""Distribution must not include local credentials, data, caches or history."""
import hashlib
import io
import json
import os
import unittest
import tempfile
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch
from scripts.build_submission_package import allowed_source, source_file, team_gaps
from scripts.verify_package import inspect_archive, isolated_environment
from scripts.verify_submission import base_commit, source_digest


class PackagePrivacy(unittest.TestCase):
    def test_source_archive_verification_does_not_require_git(self):
        with tempfile.TemporaryDirectory() as directory, patch('scripts.verify_submission.ROOT', Path(directory)):
            self.assertIsNone(base_commit())

    def test_private_paths_are_rejected(self):
        for name in ('.env', '.env.local', 'nested/.env', '.git/config', '.aws/credentials',
                     'data/customers.sqlite3', 'models/weights.bin', 'evidence/private/users.csv',
                     'tmp/.env', 'dist/old.zip', '../outside.txt', '/absolute.txt', 'C:/outside.txt',
                     'nested/__pycache__/a.pyc', 'docs/.aws/credentials', 'scripts/.ssh/id_rsa',
                     'docs/.git/config', 'docs/private/team.json', 'docs/PRIVATE/details.json',
                     'evidence/secret.PEM', 'docs/identity-documents/id.pdf', 'docs/team-passport.pdf',
                     'docs/submission-team.private.json', 'docs/credentials.json', 'docs/.ENV.LOCAL',
                     'scripts/keystore.P12', 'tests/customer.sqlite', 'docs//double.md',
                     'docs\\private.json', 'docs/account:secret.json'):
            with self.subTest(name=name):
                self.assertFalse(allowed_source(name))

    def test_source_and_public_config_template_remain_reproducible(self):
        for name in ('.env.example', 'run.py', 'tideway/store.py', 'licenses/Qwen3-Apache-2.0.txt',
                     'evidence/screens/browser-verification.json', 'tests/test_local_model.py',
                     '.github/workflows/ci.yml'):
            self.assertTrue(allowed_source(name), name)

    def test_ci_exception_does_not_expose_other_hidden_workstation_files(self):
        for name in ('.github/workflows/private.yml', '.github/credentials.json',
                     '.github/workflows/../ci.yml', '.github/workflows/ci.yml/extra'):
            self.assertFalse(allowed_source(name), name)

    def test_workflow_changes_invalidate_the_verified_release_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'run.py').write_text('pass\n', encoding='utf-8')
            workflow = root / '.github/workflows/ci.yml'
            workflow.parent.mkdir(parents=True)
            workflow.write_text('name: first\n', encoding='utf-8')
            first, files = source_digest(root)
            self.assertIn('.github/workflows/ci.yml', files)
            workflow.write_text('name: second\n', encoding='utf-8')
            self.assertNotEqual(first, source_digest(root)[0])

    def test_missing_team_facts_are_never_marked_complete(self):
        team = {'team_name': 'Example', 'members': [{'name': 'Person', 'role': ''}]}
        gaps = team_gaps(team)
        self.assertIn('Team roles', gaps)
        self.assertIn('Roster of 2-5 members', gaps)
        self.assertIn('Registration confirmation', gaps)

    def test_parent_directory_symlink_cannot_package_external_workstation_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'source'
            outside = Path(directory) / 'outside'
            (root / 'docs').mkdir(parents=True)
            outside.mkdir()
            (outside / 'ordinary.md').write_text('private workstation content')
            try:
                (root / 'docs/linked').symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest('Symlink creation unavailable on this OS')
            self.assertIsNone(source_file(root, 'docs/linked/ordinary.md'))
            (root / 'docs/public.md').write_text('public')
            self.assertEqual(source_file(root, 'docs/public.md'), (root / 'docs/public.md').resolve())

    def test_digest_can_verify_extracted_bytes_without_using_workstation_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'run.py').write_text('print("standalone")\n')
            first, files = source_digest(root)
            self.assertEqual(set(files), {'run.py'})
            (root / 'run.py').write_text('print("changed")\n')
            self.assertNotEqual(first, source_digest(root)[0])

    def test_fresh_process_environment_drops_credentials_and_python_overrides(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-key', 'AWS_SECRET_ACCESS_KEY': 'synthetic-secret',
                                     'TIDEWAY_LOCAL_MODEL_URL': 'http://127.0.0.1:1234/v1',
                                     'TIDEWAY_TEXT_BACKEND': 'local', 'PYTHONPATH': '/private/packages'}):
            env = isolated_environment()
        self.assertFalse(set(env) & {'OPENAI_API_KEY', 'AWS_SECRET_ACCESS_KEY', 'TIDEWAY_LOCAL_MODEL_URL',
                                     'TIDEWAY_TEXT_BACKEND', 'PYTHONPATH'})
        self.assertEqual(env['TIDEWAY_HOST'], '127.0.0.1')


class DistributedIntegrity(unittest.TestCase):
    @staticmethod
    def archive(entries=None, extras=(), bad_size=False):
        entries = entries or {'Tideway/source/run.py': b'print("sandbox")\n',
                              'Tideway/README-FIRST.md': b'Local source review only.\n'}
        files = {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                 for name, data in entries.items()}
        if bad_size:
            files['Tideway/source/run.py']['bytes'] += 1
        memory = io.BytesIO()
        with warnings.catch_warnings(), zipfile.ZipFile(memory, 'w') as archive:
            warnings.simplefilter('ignore', UserWarning)  # deliberate duplicate-entry fixture
            for name, data in entries.items():
                archive.writestr(name, data)
            for name, data in extras:
                archive.writestr(name, data)
            archive.writestr('Tideway/package-manifest.json', json.dumps({'files': files}))
        memory.seek(0)
        return zipfile.ZipFile(memory)

    def test_exact_manifest_accepts_expected_bytes(self):
        with self.archive() as archive:
            self.assertEqual(len(inspect_archive(archive)['files']), 2)

    def test_unmanifested_source_is_refused_before_execution(self):
        with self.archive(extras=[('Tideway/source/scripts/extra.py', b'print("unmanifested")')]) as archive:
            with self.assertRaisesRegex(RuntimeError, 'exactly match'):
                inspect_archive(archive)

    def test_private_deliverable_is_refused_even_with_matching_manifest(self):
        entries = {'Tideway/source/run.py': b'pass', 'Tideway/deliverables/private-roster.json': b'{}'}
        with self.archive(entries) as archive, self.assertRaisesRegex(RuntimeError, 'Unexpected deliverable'):
            inspect_archive(archive)

    def test_duplicates_and_case_collisions_are_refused(self):
        cases = [[('Tideway/source/run.py', b'changed')],
                 [('Tideway/source/docs/One.md', b'one'), ('Tideway/source/docs/one.md', b'two')]]
        for extras in cases:
            with self.subTest(extras=extras), self.archive(extras=extras) as archive:
                with self.assertRaisesRegex(RuntimeError, 'case-colliding'):
                    inspect_archive(archive)

    def test_size_mismatch_is_refused(self):
        with self.archive(bad_size=True) as archive, self.assertRaisesRegex(RuntimeError, 'size mismatch'):
            inspect_archive(archive)

    def test_symlink_archive_member_is_refused(self):
        link = zipfile.ZipInfo('Tideway/source/docs/linked.md')
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        with self.archive(extras=[(link, b'/private/workstation/file')]) as archive:
            with self.assertRaisesRegex(RuntimeError, 'Unsafe ZIP entry'):
                inspect_archive(archive)
