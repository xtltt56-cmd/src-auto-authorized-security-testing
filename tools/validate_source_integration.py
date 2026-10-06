"""Known-risk / fixed synthetic source proof. Never reads customer projects."""
import json
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src_auto.source_audit import source_manifest, SourceScanner
from src_auto.local_application import LocalApplicationError


def main():
    root = Path(__file__).resolve().parents[1]
    results = []
    for fixed in (False, True):
        with tempfile.TemporaryDirectory(dir=str(root / 'validation')) as folder:
            target = Path(folder)
            (target / 'app.py').write_text('import subprocess\nsubprocess.run(["echo", "synthetic"], check=True)\n' if fixed else 'import subprocess\nsubprocess.run("echo synthetic", shell=True)\n', encoding='utf-8')
            (target / 'app.js').write_text('function parse(value) { return JSON.parse(value) }\n' if fixed else 'function parse(value) { return eval(value) }\n', encoding='utf-8')
            (target / '.env').write_text('SYNTHETIC_SECRET_DO_NOT_KEEP', encoding='utf-8')
            manifest = source_manifest(target, ['python', 'javascript'], True)
            scanner = SourceScanner(root, threading.Event(), lambda: '')
            original = scanner.process.run
            def diagnostic(*args, **kwargs):
                try: return original(*args, **kwargs)
                except LocalApplicationError:
                    print(getattr(scanner.process, 'last_output', b'')[-4000:].decode('utf-8', errors='replace'))
                    raise
            scanner.process.run = diagnostic
            result = scanner.run_source(manifest, threading.Event(), lambda: '')
            assert result['complete'], 'parser coverage incomplete'
            assert 'SYNTHETIC_SECRET' not in json.dumps(result)
            assert not fixed and len(result['findings']) >= 2 or fixed and not result['findings']
            results.append(dict(case='fixed' if fixed else 'known-risk', **result))
            print(json.dumps(results[-1], ensure_ascii=False))
    output = root / 'artifacts/l3/source-proof.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__': main()
