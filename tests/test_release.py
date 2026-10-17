"""A release must bind byte-exact checks and refuse noncanonical source text."""
import tempfile
import unittest
from pathlib import Path
from scripts.verify_submission import source_digest, line_ending_issues

class ReleaseSourcePolicy(unittest.TestCase):
    def fixture(self, directory, ending):
        root=Path(directory)
        for folder in ('tideway','tests','web','scripts'):(root/folder).mkdir(exist_ok=True)
        (root/'run.py').write_bytes(b'print("sandbox")'+ending)
        return root

    def test_lf_policy_reports_offending_file_without_mutating(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory,b'\r\n')
            before=source_digest(root)[0]
            self.assertEqual(line_ending_issues(root),['run.py'])
            self.assertEqual(before,source_digest(root)[0])
            (root/'run.py').write_bytes(b'print("sandbox")\n')
            self.assertEqual(line_ending_issues(root),[])
            self.assertNotEqual(before,source_digest(root)[0])

    def test_ci_workflow_is_part_of_verified_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory,b'\n');workflow=root/'.github/workflows/ci.yml'
            workflow.parent.mkdir(parents=True);workflow.write_text('name: Test\n',encoding='utf-8')
            before=source_digest(root)[0];workflow.write_text('name: Changed\n',encoding='utf-8')
            self.assertNotEqual(before,source_digest(root)[0])
            self.assertIn('.github/workflows/ci.yml',source_digest(root)[1])

    def test_shipped_svg_change_invalidates_source_stamp(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory,b'\n');icon=root/'web/favicon.svg'
            icon.write_text('<svg/>',encoding='utf-8');before=source_digest(root)[0]
            icon.write_text('<svg><path/></svg>',encoding='utf-8')
            self.assertNotEqual(before,source_digest(root)[0])
            self.assertIn('web/favicon.svg',source_digest(root)[1])

    def test_container_build_and_exclusion_changes_invalidate_source_stamp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, b'\n')
            for name, first, second in (('Dockerfile', 'FROM python:3.11\n', 'FROM python:3.14\n'),
                                        ('.dockerignore', 'data\n', 'data\nmodels\n')):
                with self.subTest(name=name):
                    path = root / name
                    path.write_bytes(first.encode())
                    before = source_digest(root)[0]
                    path.write_bytes(second.encode())
                    self.assertNotEqual(before, source_digest(root)[0])
                    self.assertIn(name, source_digest(root)[1])
