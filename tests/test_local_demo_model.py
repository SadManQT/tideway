"""Optional provisioning must reject corrupt downloads and unsafe native archives.

All payloads are tiny authored bytes. These tests never download or run a model.
"""
import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from scripts import local_demo_model as helper


class PinnedDownloads(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'artifact.bin'
        self.payload = 'pinned UTF-8 bytes বাংলা'.encode('utf-8')
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.disk = patch.object(helper.shutil, 'disk_usage', return_value=SimpleNamespace(free=1 << 40))
        self.disk.start()
        self.addCleanup(self.disk.stop)

    def download(self, response):
        with patch.object(helper.urllib.request, 'urlopen', return_value=response):
            helper.fetch('https://example.invalid/artifact', self.target, len(self.payload), self.sha)

    def test_verified_cache_is_used_without_network(self):
        self.target.write_bytes(self.payload)
        with patch.object(helper.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network')):
            helper.fetch('https://example.invalid/artifact', self.target, len(self.payload), self.sha)

    def test_valid_download_replaces_corrupt_cache_only_after_verification(self):
        self.target.write_bytes(b'old cache')
        self.download(io.BytesIO(self.payload))
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assertFalse(self.target.with_suffix('.bin.partial').exists())

    def test_bad_hash_short_and_oversized_responses_preserve_cache_and_remove_partial(self):
        for payload in (b'x' * len(self.payload), self.payload[:-1], self.payload + b'x'):
            with self.subTest(bytes=len(payload)):
                self.target.write_bytes(b'previous cache')
                with self.assertRaisesRegex(RuntimeError, 'Checksum or size|exceeds'):
                    self.download(io.BytesIO(payload))
                self.assertEqual(self.target.read_bytes(), b'previous cache')
                self.assertFalse(self.target.with_suffix('.bin.partial').exists())

    def test_interrupted_download_removes_partial_and_preserves_cache(self):
        self.target.write_bytes(b'previous cache')
        class Interrupted(io.BytesIO):
            def read(self, _size=-1):
                raise OSError('injected connection interruption')
        with self.assertRaises(OSError):
            self.download(Interrupted())
        self.assertEqual(self.target.read_bytes(), b'previous cache')
        self.assertFalse(self.target.with_suffix('.bin.partial').exists())

    def test_insufficient_disk_space_does_not_open_network(self):
        with patch.object(helper.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)), \
             patch.object(helper.urllib.request, 'urlopen') as network:
            with self.assertRaisesRegex(RuntimeError, 'disk space'):
                helper.fetch('https://example.invalid/artifact', self.target, len(self.payload), self.sha)
            network.assert_not_called()


class RuntimeArchives(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, entries):
        path = self.root / 'runtime.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, payload in entries:
                if isinstance(name, str):
                    # ZipInfo's constructor normalizes native backslashes on
                    # Windows; set the raw field to model a foreign archive.
                    info = zipfile.ZipInfo()
                    info.filename = name
                else:
                    info = name
                archive.writestr(info, payload)
        return path

    def test_zip_rejects_traversal_windows_aliases_links_and_case_collisions_before_writing(self):
        link = zipfile.ZipInfo('link')
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        cases = [('../outside', b'x'), ('/outside', b'x'), ('C:/outside', b'x'),
                 ('folder\\outside', b'x'), ('folder//outside', b'x'), ('bad\x01name', b'x'), (link, b'../outside')]
        for index, bad in enumerate(cases):
            with self.subTest(entry=bad[0]):
                archive = self.archive([('ordinary', b'first'), bad])
                destination = self.root / f'bad-{index}'
                with self.assertRaises(RuntimeError):
                    helper.extract_runtime(archive, destination)
                self.assertFalse((destination / 'ordinary').exists())
        with self.assertRaises(RuntimeError):
            helper.extract_runtime(self.archive([('Server.exe', b'a'), ('server.exe', b'b')]), self.root / 'collision')
        self.assertFalse((self.root / 'outside').exists())

    def test_excessive_archive_entry_count_is_rejected(self):
        archive = self.archive([(f'file-{index}', b'') for index in range(1001)])
        destination = self.root / 'too-many'
        with self.assertRaisesRegex(RuntimeError, 'limits'):
            helper.extract_runtime(archive, destination)
        self.assertEqual(list(destination.iterdir()), [])

    def test_tar_traversal_external_links_and_devices_are_rejected_before_writing(self):
        for index, kind in enumerate(('traversal', 'symlink', 'device')):
            path = self.root / f'bad-{kind}.tar.gz'
            with tarfile.open(path, 'w:gz') as archive:
                ordinary = tarfile.TarInfo('ordinary')
                ordinary.size = 5
                archive.addfile(ordinary, io.BytesIO(b'first'))
                bad = tarfile.TarInfo('../outside' if kind == 'traversal' else 'unsafe')
                if kind == 'symlink':
                    bad.type, bad.linkname = tarfile.SYMTYPE, '../outside'
                elif kind == 'device':
                    bad.type = tarfile.CHRTYPE
                archive.addfile(bad)
            destination = self.root / f'tar-{index}'
            with self.assertRaises(RuntimeError):
                helper.extract_runtime(path, destination)
            self.assertFalse((destination / 'ordinary').exists())
        self.assertFalse((self.root / 'outside').exists())

    def test_valid_tar_preserves_native_server_executable_permissions(self):
        path = self.root / 'valid.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            server = tarfile.TarInfo('bin/llama-server')
            server.size, server.mode = 6, 0o755
            archive.addfile(server, io.BytesIO(b'native'))
        destination = self.root / 'valid'
        helper.extract_runtime(path, destination)
        self.assertEqual((destination / 'bin/llama-server').read_bytes(), b'native')

    def test_serving_uses_fresh_archive_bytes_and_literal_loopback_not_stale_cache(self):
        cache = self.root / 'cache'
        stale = cache / 'windows-cpu/000/llama-server.exe'
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b'untrusted stale executable')
        (stale.parent / 'library.dll').write_bytes(b'untrusted stale library')
        archive = self.archive([('llama-server.exe', b'verified executable'), ('library.dll', b'verified library')])
        launched = []
        def inspect(command):
            executable = Path(command[0])
            launched.append(executable)
            self.assertNotEqual(executable, stale)
            self.assertEqual(executable.read_bytes(), b'verified executable')
            self.assertEqual((executable.parent / 'library.dll').read_bytes(), b'verified library')
            self.assertEqual(command[command.index('--host') + 1], '127.0.0.1')
            self.assertEqual(command[command.index('-ngl') + 1], '0')
            return 0
        with patch.object(helper, 'CACHE', cache), patch.object(helper.subprocess, 'call', side_effect=inspect):
            self.assertEqual(helper.serve(archive, self.root / 'model.gguf', 'windows-cpu', 8790, cpu=True), 0)
        self.assertEqual(len(launched), 1)
        self.assertFalse(launched[0].exists())
        self.assertEqual(stale.read_bytes(), b'untrusted stale executable')

    def test_ambiguous_server_executables_are_never_launched(self):
        archive = self.archive([('a/llama-server.exe', b'a'), ('b/llama-server.exe', b'b')])
        with patch.object(helper, 'CACHE', self.root), patch.object(helper.subprocess, 'call') as launch:
            with self.assertRaisesRegex(RuntimeError, 'exactly one'):
                helper.serve(archive, self.root / 'model.gguf', 'windows-cpu', 8790)
            launch.assert_not_called()


class ProfileSelection(unittest.TestCase):
    def test_explicit_cache_and_profile_control_verified_file_and_server_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory).resolve() / 'explicit-cache'
            cache.mkdir()
            runtime_bytes, model_bytes = b'pinned-runtime', b'pinned-larger-profile'
            (cache / 'runtime.zip').write_bytes(runtime_bytes)
            (cache / 'larger.gguf').write_bytes(model_bytes)
            profile = {'id': 'larger-test-model', 'file': 'larger.gguf', 'bytes': len(model_bytes),
                       'sha256': hashlib.sha256(model_bytes).hexdigest()}
            runtimes = {'windows-cpu': ('runtime.zip', len(runtime_bytes), hashlib.sha256(runtime_bytes).hexdigest())}
            arguments = ['local_demo_model.py', '--serve', '--cpu', '--profile', 'qwen3-4b', '--cache-dir', str(cache)]
            with patch.object(helper, 'MODEL_PROFILES', {'qwen3-4b': profile}), \
                 patch.object(helper, 'RUNTIMES', runtimes), \
                 patch.object(helper, 'runtime_key', return_value='windows-cpu'), \
                 patch.object(helper.sys, 'argv', arguments), \
                 patch.object(helper, 'serve', return_value=0) as serve:
                self.assertEqual(helper.main(), 0)
                serve.assert_called_once_with(cache / 'runtime.zip', cache / 'larger.gguf', 'windows-cpu', 8790, True,
                                              cache=cache.resolve(), model_id='larger-test-model')
                # A profile mismatch must fail before any native process runs.
                (cache / 'larger.gguf').write_bytes(b'other model')
                serve.reset_mock()
                with self.assertRaisesRegex(RuntimeError, 'verification failed'):
                    helper.main()
                serve.assert_not_called()


if __name__ == '__main__':
    unittest.main()
