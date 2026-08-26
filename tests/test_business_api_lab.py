import json
import sys
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).parents[1]
LAB = ROOT / "lab" / "business-api"


class BusinessApiLabTests(unittest.TestCase):
    def test_cli_exposes_loopback_authorization_matrix_command(self):
        from src_auto.cli import build_parser

        args = build_parser().parse_args(
            ["business-api-matrix", "--url", "http://127.0.0.1:8084", "--output", "validation/business-api/matrix.json", "--json"]
        )
        self.assertEqual(args.command, "business-api-matrix")
        self.assertEqual(args.url, "http://127.0.0.1:8084")

    def test_fixture_contains_openapi_and_loopback_only_contract(self):
        spec_path = LAB / "openapi.json"
        self.assertTrue(spec_path.is_file())
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        self.assertEqual(spec["openapi"], "3.0.3")
        self.assertIn("/api/v1/orders/{order_id}", spec["paths"])
        self.assertEqual(spec["x-src-auto"]["host"], "127.0.0.1")
        self.assertEqual(spec["x-src-auto"]["port"], 8084)
        self.assertEqual(spec["x-src-auto"]["reset"], "process-local synthetic data only")

    def test_compose_adds_pinned_loopback_business_api_service(self):
        compose = (ROOT / "docker-compose.local-labs.yml").read_text(encoding="utf-8")
        self.assertIn("business-api:", compose)
        self.assertIn("127.0.0.1:8084:8084", compose)
        self.assertRegex(compose, r"python:3\.12-slim@sha256:[0-9a-f]{64}")
        self.assertIn("./lab/business-api:/app:ro", compose)

    def test_app_exposes_health_and_deterministic_authorization_fixture(self):
        sys.path.insert(0, str(LAB))
        try:
            from app import build_server, reset_state
        finally:
            sys.path.pop(0)
        reset_state()
        server = build_server("127.0.0.1", 0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen("http://127.0.0.1:%d/health" % port, timeout=3) as response:
                self.assertEqual(response.status, 200)
            request = Request("http://127.0.0.1:%d/api/v1/orders/order-a" % port, headers={"X-Test-User": "buyer-b"})
            with urlopen(request, timeout=3) as response:
                body = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(body["owner"], "buyer-a")
            self.assertTrue(body["x-src-auto"]["intentional_candidate"])
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_authorization_matrix_is_candidate_only_and_redacts_bodies(self):
        from src_auto.business_api_lab import run_authorization_matrix

        result = run_authorization_matrix("http://127.0.0.1:8084", fetcher=lambda user, order: {
            "buyer-a": {"status_code": 200, "body": {"id": order, "owner": "buyer-a", "viewer": user}},
            "buyer-b": {"status_code": 200, "body": {"id": order, "owner": "buyer-a", "viewer": user}},
            "anonymous": {"status_code": 403, "body": {"error": "denied"}},
        }[user])
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["disposition"], "candidate_broken_object_authorization")
        self.assertTrue(result["manual_review_required"])
        self.assertNotIn("buyer-a", json.dumps(result, ensure_ascii=False))
        self.assertNotIn('"body"', json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
