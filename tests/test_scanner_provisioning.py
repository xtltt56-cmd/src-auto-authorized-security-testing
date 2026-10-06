import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import install_controlled_scanners as installer


class ScannerProvisioningTests(unittest.TestCase):
    def test_verified_cached_images_do_not_require_registry_access(self):
        with tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parents[1] / 'validation')) as folder:
            root = Path(folder)
            (root / 'config/integrations').mkdir(parents=True)
            (root / 'vendor/bin').mkdir(parents=True)
            content = b'synthetic verified binary'
            (root / 'vendor/bin/docker.exe').write_bytes(content)
            registry = dict(docker_sha256=hashlib.sha256(content).hexdigest(), image='synthetic@sha256:123', image_id='sha256:123')
            for name in ('passive_scanners.json', 'source_scanners.json'):
                (root / 'config/integrations' / name).write_text(json.dumps(registry), encoding='utf-8')
            (root / 'config/integrations/source_wheels.json').write_text('{}', encoding='utf-8')
            with patch.object(installer, 'ROOT', root), patch.object(installer.subprocess, 'run') as run, patch.object(installer.subprocess, 'check_output', return_value=b'[{"Id":"sha256:123"}]'), patch('src_auto.guarded_passive.ZapOfflineScanner.prepare'), patch('src_auto.source_audit.SourceScanner.prepare'):
                installer.main()
            self.assertFalse(any('pull' in call.args[0] for call in run.call_args_list))
