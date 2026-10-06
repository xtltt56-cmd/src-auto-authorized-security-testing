"""Explicit, D-project-only provisioning. Tasks never download tools on demand.

Docker Desktop must already be installed and running; no global installation,
no services, no target contact. Images/wheels are pinned and verified offline.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    registries = [json.loads((ROOT / 'config/integrations' / filename).read_text(encoding='utf-8'))
                  for filename in ('passive_scanners.json', 'source_scanners.json')]
    destination = ROOT / 'vendor/bin/docker.exe'
    expected = registries[0]['docker_sha256']
    if not destination.is_file() or hashlib.sha256(destination.read_bytes()).hexdigest() != expected:
        original = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Docker/Docker/resources/bin/docker.exe'
        if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest() != expected:
            raise RuntimeError('This tool profile requires the verified Docker Desktop 4.87 CLI; another CLI must be reviewed before provisioning.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(original), str(destination))
    args = [str(destination)] + (['--host', 'npipe:////./pipe/dockerDesktopLinuxEngine'] if os.name == 'nt' else [])
    subprocess.run(args + ['info', '--format', '{{.ServerVersion}}'], check=True, timeout=15)
    for registry in registries:
        try:
            cached = json.loads(subprocess.check_output(args + ['image', 'inspect', registry['image']], stderr=subprocess.DEVNULL, timeout=15))[0]
        except subprocess.CalledProcessError:
            cached = None
        if cached is None:
            subprocess.run(args + ['pull', registry['image']], check=True, timeout=600)
            found = json.loads(subprocess.check_output(args + ['image', 'inspect', registry['image']], timeout=15))[0]
        else:
            found = cached
        if found['Id'] != registry['image_id']: raise RuntimeError('Pinned image does not match')
    wheels = json.loads((ROOT / 'config/integrations/source_wheels.json').read_text(encoding='utf-8'))
    folder = ROOT / 'vendor/source-audit/wheels'
    folder.mkdir(parents=True, exist_ok=True)
    for filename, digest in wheels.items():
        target = folder / filename
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest: continue
        package = filename.split('-', 1)[0]
        with urlopen('https://pypi.org/pypi/' + package + '/json', timeout=20) as response:
            data = json.load(response)
        match = next((item for release in data['releases'].values() for item in release
                      if item['filename'] == filename and item['digests']['sha256'] == digest), None)
        if not match or urlsplit(match['url']).hostname != 'files.pythonhosted.org': raise RuntimeError('Wheel source mismatch')
        partial = target.with_suffix('.download')
        try:
            with urlopen(match['url'], timeout=30) as response, partial.open('wb') as output:
                content = response.read(4 * 1048576 + 1)
                if len(content) > 4 * 1048576 or hashlib.sha256(content).hexdigest() != digest: raise RuntimeError('Wheel checksum mismatch')
                output.write(content)
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
    sys.path.insert(0, str(ROOT))
    import threading
    from src_auto.guarded_passive import ZapOfflineScanner
    from src_auto.source_audit import SourceScanner
    ZapOfflineScanner(ROOT, threading.Event(), lambda: '').prepare()
    SourceScanner(ROOT, threading.Event(), lambda: '').prepare()
    print('Pinned ZAP, Semgrep and Bandit are ready. No target has been contacted.')


if __name__ == '__main__': main()
