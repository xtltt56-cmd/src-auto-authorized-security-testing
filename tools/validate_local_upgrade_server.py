"""Foreground, isolated real HTTP + SQLite + Docker UI acceptance fixture."""
import json
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src_auto.agent_service import AgentService
from src_auto.dashboard_server import create_server
from src_auto.agent_resources import WindowsResources


class Control:
    def __init__(self):
        self._lock = threading.RLock()
        self._closing = False
        self.agent = None
    def lifecycle(self): return {'activeWork': bool(self.agent and self.agent.active), 'closing': self._closing}
    def snapshot(self): return dict(source='loopback', dependency=dict(dockerReady=True), tasks=[], labs=[], findings=[], reports=[], events=[])
    def prepare_shutdown(self): return not self.lifecycle()['activeWork']


def main():
    artifact = ROOT / 'artifacts/l3'
    artifact.mkdir(parents=True, exist_ok=True)
    check = WindowsResources.check
    def measured(resource):
        result = check(resource)
        if not result.get('allowed'):
            with (artifact / 'ui-resource-denials.jsonl').open('a', encoding='utf-8') as output:
                output.write(json.dumps(result) + '\n')
        return result
    WindowsResources.check = measured
    with tempfile.TemporaryDirectory(dir=str(artifact)) as folder:
        workspace = Path(folder)
        for relative in ('config/policy.yaml', 'config/integrations/passive_scanners.json', 'config/integrations/source_scanners.json',
                         'config/integrations/source_wheels.json', 'config/integrations/source_rules.json', 'tools/source_audit_container.py', 'vendor/bin/docker.exe'):
            destination = workspace / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(ROOT / relative), str(destination))
        (workspace / 'config/models.yaml').write_text('{}', encoding='utf-8')
        for wheel in json.loads((ROOT / 'config/integrations/source_wheels.json').read_text()).keys():
            destination = workspace / 'vendor/source-audit/wheels' / wheel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(ROOT / 'vendor/source-audit/wheels' / wheel), str(destination))
        source = workspace / 'synthetic-source'
        source.mkdir()
        (source / 'app.py').write_text('import subprocess\nsubprocess.run("echo synthetic", shell=True)\n', encoding='utf-8')
        (source / 'app.js').write_text('function parse(value) { return eval(value) }\n', encoding='utf-8')
        (source / '.env').write_text('SYNTHETIC_SECRET_NO_EVIDENCE', encoding='utf-8')
        received = []
        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.path)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.send_header('Set-Cookie', 'PRIVATE_COOKIE')
                self.end_headers()
                self.wfile.write(b'<html><a href="/health">allowed</a><a href="/reset">excluded</a><a href="https://outside.test/?token=PRIVATE_TOKEN">blocked</a>PRIVATE_BODY</html>')
            def log_message(self, *args): pass
        target = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = threading.Thread(target=target.serve_forever, daemon=True)
        thread.start()
        control = Control()
        control.agent = AgentService(workspace, control, model_factory=lambda *args: (_ for _ in ()).throw(AssertionError('no cloud allowed')))
        server = create_server(control, port=4274, project_root=workspace, allowed_origin='http://127.0.0.1:4273', remote_ai_enabled=False)
        (artifact / 'ui-fixture.json').write_text(json.dumps(dict(origin='http://127.0.0.1:' + str(target.server_address[1]), source=str(source))), encoding='utf-8')
        print('Isolated API ready on 4274; only synthetic data and no model calls', flush=True)
        try: server.serve_forever()
        finally:
            control.agent.close()
            server.server_close(); target.shutdown(); target.server_close(); thread.join(2)
            (artifact / 'ui-requests.json').write_text(json.dumps(received), encoding='utf-8')


if __name__ == '__main__': main()
