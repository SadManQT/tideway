"""Distribution must not include local credentials, data, caches or history."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from scripts.build_submission_package import allowed_source, team_gaps
from scripts.verify_submission import base_commit


class PackagePrivacy(unittest.TestCase):
    def test_source_archive_verification_does_not_require_git(self):
        with tempfile.TemporaryDirectory() as directory, patch('scripts.verify_submission.ROOT', Path(directory)):
            self.assertIsNone(base_commit())

    def test_private_paths_are_rejected(self):
        for name in ('.env', '.env.local', 'nested/.env', '.git/config', '.aws/credentials',
                     'data/customers.sqlite3', 'models/weights.bin', 'evidence/private/users.csv',
                     'tmp/.env', 'dist/old.zip', '../outside.txt', '/absolute.txt', 'C:/outside.txt',
                     'nested/__pycache__/a.pyc'):
            with self.subTest(name=name):
                self.assertFalse(allowed_source(name))

    def test_source_and_public_config_template_remain_reproducible(self):
        for name in ('.env.example', 'run.py', 'tideway/store.py', 'licenses/Qwen3-Apache-2.0.txt',
                     'evidence/screens/browser-verification.json', 'tests/test_local_model.py'):
            self.assertTrue(allowed_source(name), name)

    def test_missing_team_facts_are_never_marked_complete(self):
        team = {'team_name': 'Example', 'members': [{'name': 'Person', 'role': ''}]}
        gaps = team_gaps(team)
        self.assertIn('Team roles', gaps)
        self.assertIn('Roster of 2-5 members', gaps)
        self.assertIn('Registration confirmation', gaps)
