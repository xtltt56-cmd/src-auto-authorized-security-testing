import importlib.util
import json
import threading
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

from src_auto.agent_actions import GuardedHTTP, LocalActions
from src_auto.agent_contracts import Limits, Decision
from src_auto.store import Store
from src_auto.local_labs import LocalLabManager

ROOT = Path(__file__).resolve().parents[1]


class AgentLabTests(unittest.TestCase):
    def test_discovery_action_truncates_large_static_documents_and_marks_degraded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ("config/validation/local_only.json", "config/models.yaml", "config/policy.yaml"):
                target = root / relative; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(ROOT / relative), str(target))
            manager = LocalLabManager(ROOT, ROOT / "config/labs/local_labs.json", ROOT / "docker-compose.local-labs.yml")
            actions = LocalActions(root, manager, "juice-shop", Limits(), threading.Event())

            class Response:
                headers = {"Content-Type": "text/javascript"}
                def __init__(self): self.closed = False
                def getcode(self): return 200
                def read(self, size): return b"x" * min(size, 600 * 1024)
                def close(self): self.closed = True

            class Opener:
                def __init__(self): self.response = Response()
                def open(self, *args, **kwargs): return self.response

            opener = Opener()
            actions.client.opener = opener

            def fake_discovery(policy, entry, fetch_fn, max_scripts):
                page = fetch_fn(entry)
                self.assertEqual(len(page["body"].encode("utf-8")), 512 * 1024)
                self.assertTrue(page["truncated"])
                return {"status": "COMPLETED", "discovered_urls": [entry], "api_urls": [],
                        "external_urls_excluded": [], "degraded": False, "request_count": 1}

            with patch("src_auto.agent_actions.discover_local_surface", side_effect=fake_discovery):
                result = actions.execute(Decision("discover_surface", "entry", (), "读取本地页面"))
            self.assertTrue(result["truncated"])
            self.assertTrue(result["degraded"])
            self.assertTrue(opener.response.closed)

    def test_candidate_is_durable_and_never_confirmed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ("config/validation/local_only.json", "config/models.yaml", "config/policy.yaml", "config/agent/permissions.json"):
                target = root / relative; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(ROOT / relative), str(target))
            manager = LocalLabManager(ROOT, ROOT / "config/labs/local_labs.json", ROOT / "docker-compose.local-labs.yml")
            actions = LocalActions(root, manager, "business-api", Limits(), threading.Event())
            value = Decision("compare_object_authorization", "case-01", (), "合成测试")
            key = actions.persist_candidate("synthetic-agent-id", value, {"id": "o1"})
            report = root / "reports/agent/synthetic-agent-id.md"
            report.parent.mkdir(parents=True); report.write_text("合成报告", encoding="utf-8")
            actions.link_report("synthetic-agent-id", report)
            store = Store(root / "data/src_auto.sqlite3")
            try:
                finding = store.list_findings()[0]
                self.assertEqual(str(finding["id"]), key)
                self.assertEqual(finding["status"], "candidate")
                self.assertFalse(finding["triage"]["confirmed"])
                self.assertFalse(finding["triage"]["submission_ready"])
                self.assertEqual(store.list_reports()[0]["run_id"], finding["run_id"])
                self.assertEqual(store.list_reports()[0]["path"], "reports/agent/synthetic-agent-id.md")
            finally: store.close()

    def test_twenty_frozen_permission_controls_over_real_http(self):
        spec = importlib.util.spec_from_file_location("agent_lab_fixture", str(ROOT / "lab/business-api/app.py"))
        app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app)
        server = app.build_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            client = GuardedHTTP("http://127.0.0.1:{}/health".format(server.server_port), Limits(max_requests=60), threading.Event())
            verdicts = []
            for index in range(1, 21):
                case = "case-{:02d}".format(index)
                path = "/agent/cases/" + case
                own = client.fetch(client.origin + path, user="buyer-a")
                peer = client.fetch(client.origin + path, user="buyer-b")
                anonymous = client.fetch(client.origin + path)
                privacy = "public" if index >= 16 else "private"
                verdicts.append(privacy == "private" and own["status_code"] == 200 and peer["status_code"] == 200 and own["body"] == peer["body"])
                self.assertIn(anonymous["status_code"], [200, 403])
            self.assertEqual(verdicts, [True] * 10 + [False] * 10)
            self.assertEqual(client.requests, 60)
        finally:
            server.shutdown(); thread.join(5); server.server_close()


if __name__ == "__main__": unittest.main()
