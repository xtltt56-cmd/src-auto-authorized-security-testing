import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src_auto.dashboard_detection import LocalDetectionWorkflow
from src_auto.local_labs import LabSpec
from src_auto.store import Store


class FakeManager:
    def __init__(self, root):
        self.project_root = Path(root)
        self.specs = {
            "business-api": LabSpec(
                lab_id="business-api",
                service="business-api",
                image="example/business-api",
                digest="sha256:" + "1" * 64,
                container_port=8084,
                host="127.0.0.1",
                host_port=8084,
                health_url="http://127.0.0.1:8084/health",
            )
        }

    def spec(self, lab_id):
        return self.specs[lab_id]

    def status(self, lab_id):
        return {"status": "READY", "lab_id": lab_id}


class DashboardDetectionWorkflowTests(unittest.TestCase):
    def test_actual_loopback_http_is_contacted_and_reported(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                body = b'<html><title>Local lab</title><a href="/api/items">API</a></html>'
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                port = int(server.server_address[1])
                (root / "config" / "validation").mkdir(parents=True)
                (root / "config" / "validation" / "local_only.json").write_text(
                    json.dumps({
                        "AI_PROVIDER": "local", "LOCAL_LLM_ONLY": True, "ALLOW_REMOTE_LLM": False,
                        "allowed_hosts": ["127.0.0.1"], "allowed_ports": [port], "max_concurrency": 1,
                    }),
                    encoding="utf-8",
                )

                class LiveManager:
                    project_root = root

                    def spec(self, lab_id):
                        return LabSpec(
                            lab_id=lab_id, service=lab_id, image="example/local",
                            digest="sha256:" + "2" * 64, container_port=port,
                            host="127.0.0.1", host_port=port,
                            health_url="http://127.0.0.1:{}/".format(port),
                        )

                    def status(self, lab_id):
                        return {"status": "READY", "lab_id": lab_id}

                result = LocalDetectionWorkflow(root, LiveManager()).run(
                    "juice-shop", threading.Event(), lambda *_args, **_kwargs: None
                )

                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["networkContact"], "loopback")
                self.assertGreaterEqual(result["endpointCount"], 2)
                self.assertGreaterEqual(result["candidateCount"], 1)
                self.assertTrue((root / result["reportId"]).is_file())
                self.assertGreaterEqual(requests.count("/"), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_real_loopback_detection_persists_candidates_and_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config" / "validation").mkdir(parents=True)
            (root / "config" / "validation" / "local_only.json").write_text(
                json.dumps(
                    {
                        "AI_PROVIDER": "local",
                        "LOCAL_LLM_ONLY": True,
                        "ALLOW_REMOTE_LLM": False,
                        "allowed_hosts": ["127.0.0.1", "localhost"],
                        "allowed_ports": [8084],
                        "max_concurrency": 1,
                    }
                ),
                encoding="utf-8",
            )
            manager = FakeManager(root)
            stages = []
            workflow = LocalDetectionWorkflow(
                root,
                manager,
                probe_fn=lambda policy, url: {
                    "status": "reachable",
                    "url": url,
                    "final_url": url,
                    "http_status": 200,
                    "headers": {
                        "content-security-policy": "",
                        "x-content-type-options": "",
                        "x-frame-options": "DENY",
                    },
                    "network_contact": True,
                },
                discover_fn=lambda policy, url: {
                    "status": "COMPLETED",
                    "discovered_urls": [url, "http://127.0.0.1:8084/api/v1/orders/order-a"],
                    "api_urls": ["http://127.0.0.1:8084/api/v1/orders/order-a"],
                    "external_urls_excluded": [],
                    "request_count": 1,
                    "network_contact": True,
                },
                business_matrix_fn=lambda url: {
                    "status": "COMPLETED",
                    "disposition": "candidate_broken_object_authorization",
                    "owner_peer_equivalent": True,
                    "response_statuses": {"owner": 200, "peer": 200, "anonymous": 401},
                    "body_fingerprints": {"owner": "a" * 64, "peer": "a" * 64, "anonymous": "b" * 64},
                    "raw_bodies_retained": False,
                    "network_contact": True,
                },
            )

            result = workflow.run(
                "business-api",
                threading.Event(),
                lambda stage, progress, counters, message, level="info": stages.append((stage, progress, counters, message, level)),
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["candidateCount"], 3)
            self.assertEqual(result["networkContact"], "loopback")
            self.assertTrue(result["reportId"].startswith("reports/"))
            self.assertTrue((root / result["reportId"]).is_file())
            self.assertEqual(stages[-1][0], "检测完成")
            self.assertEqual(stages[-1][1], 100)
            store = Store(root / "data" / "src_auto.sqlite3")
            try:
                findings = store.list_findings(result["runId"])
                self.assertEqual(len(findings), 3)
                self.assertTrue(any("对象级授权" in item["title"] for item in findings))
                self.assertTrue(all("raw" not in item["evidence"].lower() for item in findings))
            finally:
                store.close()

    def test_cancel_before_network_contact_creates_no_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config" / "validation").mkdir(parents=True)
            (root / "config" / "validation" / "local_only.json").write_text(
                json.dumps({"AI_PROVIDER": "local", "LOCAL_LLM_ONLY": True, "ALLOW_REMOTE_LLM": False,
                            "allowed_hosts": ["127.0.0.1"], "allowed_ports": [8084], "max_concurrency": 1}),
                encoding="utf-8",
            )
            cancelled = threading.Event()
            cancelled.set()
            workflow = LocalDetectionWorkflow(root, FakeManager(root), probe_fn=lambda *_: self.fail("network must not be contacted"))

            result = workflow.run("business-api", cancelled, lambda *args, **kwargs: None)

            self.assertEqual(result["status"], "cancelled")
            self.assertFalse((root / "data" / "src_auto.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
