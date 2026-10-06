"""Fresh offline ZAP proof using synthetic header-only data; no target service."""
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src_auto.guarded_passive import PassiveCapture, ZapOfflineScanner
from src_auto.scope import ScopePolicy
from src_auto.local_application import LocalApplicationError
from tests.test_local_application_scope import local_scope_document


def main():
    root = Path(__file__).resolve().parents[1]
    document = local_scope_document(now=datetime.now(timezone.utc))
    document['allowed_paths'] = ['/']
    document['limits']['output_limit_bytes'] = 1048576
    scope = ScopePolicy.from_mapping(document)
    capture = PassiveCapture(scope)
    capture.record(scope.local_web.origin + '/', 'GET', 200, [('Content-Type', 'text/html')], b'<html>synthetic</html>', False)
    scanner = ZapOfflineScanner(root, threading.Event(), lambda: '')
    original = scanner.process.run
    def diagnostic(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except LocalApplicationError:
            # Synthetic-only, no target response values enter this process.
            print(getattr(scanner.process, 'last_output', b'')[-7000:].decode('utf-8', errors='replace'))
            raise
    scanner.process.run = diagnostic
    result = scanner.run(scope, capture, 90)
    output = root / 'artifacts/l3/passive-proof.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
