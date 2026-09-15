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
    (workspace / 'config').mkdir(parents=True)
    (workspace / 'config' / 'models.yaml').write_text('''{
  "remote_providers": {
    "deepseek": {"display_name": "DeepSeek V4.1 Flash", "model": "deepseek-flash", "endpoint": "https://api.deepseek.com/chat/completions"},
    "zhipu": {"display_name": "智谱 GLM-5.3-Flash", "model": "glm-5.3-flash", "endpoint": "https://open.bigmodel.cn/api/paas/v4/chat/completions"},
    "openrouter": {"display_name": "OpenRouter 通用入口", "model": "openrouter/free", "endpoint": "https://openrouter.ai/api/v1/chat/completions"}
  }
}''', encoding='utf-8')
    (workspace / 'reports' / 'lab' / 'nested').mkdir(parents=True)
    (workspace / 'reports' / 'lab' / 'nested' / 'acceptance.md').write_text('# 本地验收报告\n真实文件内容\nAuthorization: Bearer dummy-secret', encoding='utf-8')
    server = create_server(IdleService(), project_root=workspace)
    try: server.serve_forever()
    finally: server.server_close()
