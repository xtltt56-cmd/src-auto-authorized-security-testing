"""Real HTTP/storage fixture: isolated D-drive files; no Docker or remote requests."""
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root))
from src_auto.dashboard_server import create_server


class IdleService:
    def snapshot(self):
        return dict(source='loopback', dependency=dict(executionServiceReady=True, dockerReady=False, message='隔离测试环境'),
                    tasks=[], labs=[], events=[], findings=[], reports=[])


artifact_root = root / 'validation' / 'dashboard-reliability'
artifact_root.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=str(artifact_root)) as temporary:
    workspace = Path(temporary)
    (workspace / 'reports').mkdir()
    (workspace / 'reports' / 'acceptance.md').write_text('# 本地验收报告\n真实文件内容\nAuthorization: Bearer dummy-secret', encoding='utf-8')
    server = create_server(IdleService(), project_root=workspace)
    try: server.serve_forever()
    finally: server.server_close()
