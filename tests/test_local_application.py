import json
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from src_auto.local_application import LocalApplicationError, LocalApplicationHTTP, LocalReadOnlyPlan
from src_auto.scope import ScopeGuard, ScopePolicy
from tests.test_local_application_scope import local_scope_document


class LocalApplicationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.received = []
        self.started = threading.Event()
        received, started = self.received, self.started

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append((self.command, self.path))
                started.set()
                body = b'{"token":"SYNTHETIC_PRIVATE_BODY","holding":123}'
                if self.path == "/slow":
                    time.sleep(1.5)
                self.send_response(302 if self.path.startswith("/redirect") else 200)
                if self.path == "/redirect-safe":
                    self.send_header("Location", "/api/health")
                elif self.path == "/redirect-bad":
                    self.send_header("Location", "/api/reset")
                elif self.path == "/redirect-other-port":
                    self.send_header("Location", "http://127.0.0.1:1/api/health")
                elif self.path == "/redirect-external":
                    self.send_header("Location", "https://example.test/")
                if self.path == "/big":
                    body = b"x" * 4096
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", "secret=SYNTHETIC_PRIVATE_COOKIE")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    try:
                        self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        pass

            do_HEAD = do_GET

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.05))
        self.thread.start()
        self.document = local_scope_document(port=self.server.server_port, now=datetime.now(timezone.utc))
        self.document["allowed_paths"] = ["/", "/api/health", "/redirect-safe", "/redirect-bad",
                                          "/redirect-other-port", "/redirect-external", "/slow", "/big"]
        self.document["excluded_paths"] = ["/api/reset"]
        self.cancel = threading.Event()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def plan(self, paths=("/",), method="GET", scope=None):
        scope = scope or ScopePolicy.from_mapping(self.document)
        document = {"plan_version": 1, "scope_digest": scope.digest(), "manual_execution_confirmed": True,
                    "requests": [{"path": path, "method": method} for path in paths]}
        return scope, LocalReadOnlyPlan.from_mapping(document, scope)

    def client(self, scope, plan, **kwargs):
        return LocalApplicationHTTP(ScopeGuard(scope), plan, self.cancel, **kwargs)

    def test_real_readonly_request_returns_metadata_not_private_data(self):
        scope, plan = self.plan()
        client = self.client(scope, plan)
        result = client.fetch(plan.requests[0])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(self.received, [("GET", "/")])
        self.assertEqual(client.request_count, 1)
        self.assertFalse(result["raw_body_retained"])
        rendered = json.dumps(result)
        self.assertNotIn("SYNTHETIC_PRIVATE", rendered)
        self.assertNotIn("holding", rendered)

    def test_process_proxies_are_ignored_and_head_remains_head(self):
        scope, plan = self.plan(method="HEAD")
        with patch.dict("os.environ", {"HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1", "ALL_PROXY": "http://127.0.0.1:1"}):
            result = self.client(scope, plan).fetch(plan.requests[0])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(self.received, [("HEAD", "/")])

    def test_safe_relative_redirect_is_counted_and_rechecked(self):
        scope, plan = self.plan(paths=("/redirect-safe",))
        client = self.client(scope, plan)
        result = client.fetch(plan.requests[0])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(client.request_count, 2)
        self.assertEqual(self.received, [("GET", "/redirect-safe"), ("GET", "/api/health")])

    def test_denied_redirect_never_reaches_other_route_or_origin(self):
        import http.client
        original_connect = http.client.HTTPConnection.connect

        def checked_connect(connection):
            self.assertEqual((connection.host, connection.port), ("127.0.0.1", self.server.server_port))
            return original_connect(connection)

        for path, reason in (("/redirect-bad", "path_excluded"),
                             ("/redirect-other-port", "origin_not_in_scope"),
                             ("/redirect-external", "origin_not_in_scope")):
            with self.subTest(path=path):
                self.received.clear()
                scope, plan = self.plan(paths=(path,))
                client = self.client(scope, plan)
                # A redirect bug must fail this test before contacting an
                # uncontrolled origin, not pass because that connection fails.
                with patch.object(http.client.HTTPConnection, "connect", checked_connect):
                    with self.assertRaisesRegex(LocalApplicationError, reason):
                        client.fetch(plan.requests[0])
                self.assertEqual(client.request_count, 1)
                self.assertEqual(self.received, [("GET", path)])

    def test_redirect_cannot_bypass_request_limit(self):
        self.document["limits"]["request_limit"] = 1
        scope, plan = self.plan(paths=("/redirect-safe",))
        with self.assertRaisesRegex(LocalApplicationError, "request_limit"):
            self.client(scope, plan).fetch(plan.requests[0])
        self.assertEqual(self.received, [("GET", "/redirect-safe")])

    def test_large_body_is_bounded_and_not_retained(self):
        scope, plan = self.plan(paths=("/big",))
        result = self.client(scope, plan).fetch(plan.requests[0])
        self.assertTrue(result["body_truncated"])
        self.assertLessEqual(result["response_bytes_read"], self.document["limits"]["response_limit_bytes"] + 1)
        self.assertNotIn("body", result)

    def test_cancel_before_request_and_stop_marker_send_nothing(self):
        scope, plan = self.plan()
        self.cancel.set()
        with self.assertRaisesRegex(LocalApplicationError, "cancelled"):
            self.client(scope, plan).fetch(plan.requests[0])
        self.cancel.clear()
        with self.assertRaisesRegex(LocalApplicationError, "cancelled"):
            self.client(scope, plan, stop=lambda: True).fetch(plan.requests[0])
        self.assertEqual(self.received, [])

    def test_running_request_can_be_cancelled_without_next_stage(self):
        scope, plan = self.plan(paths=("/slow",))
        outcome = []
        client = self.client(scope, plan)

        def run():
            try:
                client.fetch(plan.requests[0])
                outcome.append("unexpected_success")
            except LocalApplicationError as exc:
                outcome.append(exc.reason)

        worker = threading.Thread(target=run)
        worker.start()
        self.assertTrue(self.started.wait(1))
        self.cancel.set()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcome, ["cancelled"])
        self.assertEqual(self.received, [("GET", "/slow")])

    def test_expired_or_changed_scope_and_unapproved_request_send_nothing(self):
        scope, plan = self.plan()
        client = self.client(scope, plan, now_fn=lambda: datetime.now(timezone.utc) + timedelta(hours=1))
        with self.assertRaisesRegex(LocalApplicationError, "outside_test_window"):
            client.fetch(plan.requests[0])
        scope.confirmed = False
        with self.assertRaises(LocalApplicationError):
            self.client(scope, plan)
        self.assertEqual(self.received, [])

    def test_wall_clock_rollback_is_blocked(self):
        scope, plan = self.plan(paths=("/", "/api/health"))
        current = [datetime.now(timezone.utc)]
        client = self.client(scope, plan, now_fn=lambda: current[0])
        client.fetch(plan.requests[0])
        current[0] -= timedelta(seconds=10)
        with self.assertRaisesRegex(LocalApplicationError, "clock_rollback"):
            client.fetch(plan.requests[1])
        self.assertEqual(self.received, [("GET", "/")])

    def test_request_timeout_and_task_deadline_are_distinct(self):
        self.document["limits"]["request_timeout_seconds"] = 1
        scope, plan = self.plan(paths=("/slow",))
        with self.assertRaisesRegex(LocalApplicationError, "request_timeout"):
            self.client(scope, plan).fetch(plan.requests[0])
        self.received.clear()
        scope, plan = self.plan()
        client = self.client(scope, plan)
        client.deadline = time.monotonic() - 1
        with self.assertRaisesRegex(LocalApplicationError, "task_timeout"):
            client.fetch(plan.requests[0])
        self.assertEqual(self.received, [])

    def test_resource_callback_is_checked_for_redirect_requests(self):
        scope, plan = self.plan(paths=("/redirect-safe",))
        remaining = ["", "paused_resource"]
        with self.assertRaisesRegex(LocalApplicationError, "paused_resource"):
            self.client(scope, plan, before_request=lambda: remaining.pop(0)).fetch(plan.requests[0])
        self.assertEqual(self.received, [("GET", "/redirect-safe")])

    def test_unapproved_request_and_output_limit_are_rejected(self):
        from src_auto.local_application import LocalReadOnlyRequest
        scope, plan = self.plan()
        client = self.client(scope, plan)
        with self.assertRaisesRegex(LocalApplicationError, "request_not_in_approved_plan"):
            client.fetch(LocalReadOnlyRequest("request-999", "/api/reset", "GET"))
        self.assertEqual(self.received, [])
        self.document["limits"]["output_limit_bytes"] = 1
        scope, plan = self.plan()
        with self.assertRaisesRegex(LocalApplicationError, "output_limit"):
            self.client(scope, plan).fetch(plan.requests[0])

    def test_https_retains_default_certificate_verification(self):
        import ssl
        self.document["origin"] = self.document["origin"].replace("http:", "https:")
        scope, plan = self.plan()
        with patch("http.client.HTTPSConnection") as https:
            https.return_value.connect.side_effect = ssl.SSLCertVerificationError("untrusted local fixture")
            with self.assertRaises(LocalApplicationError):
                self.client(scope, plan).fetch(plan.requests[0])
            context = https.call_args.kwargs["context"]
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
        self.assertEqual(self.received, [])

    def test_plan_is_typed_and_bound_to_approval(self):
        scope, plan = self.plan()
        self.assertEqual(plan.scope_digest, scope.digest())
        valid = plan.canonical()
        for updated in (dict(valid, scope_digest="0" * 64), dict(valid, commands=["whoami"]),
                        dict(valid, manual_execution_confirmed="true"), dict(valid, manual_execution_confirmed=False),
                        dict(valid, requests=[{"path": "/api/reset", "method": "GET"}]),
                        dict(valid, requests=[{"path": "/", "method": "POST"}]),
                        dict(valid, requests=[{"path": "/", "method": "GET", "headers": {"X": "Y"}}]),
                        dict(valid, requests=[{"url": "https://example.test/", "method": "GET"}])):
            with self.subTest(updated=updated), self.assertRaises(ValueError):
                LocalReadOnlyPlan.from_mapping(updated, scope)

    def test_unadmitted_tool_adapter_does_not_start_process_for_local_scope(self):
        from src_auto.adapters import SafeToolAdapter, ToolRegistry
        scope, plan = self.plan()
        with patch("subprocess.run", side_effect=AssertionError("must not spawn")):
            result = SafeToolAdapter("httpx", ToolRegistry(commands={"httpx": "fake"})).run(
                ["-u", "https://example.test/"], ScopeGuard(scope), [scope.local_web.origin + "/"])
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.detail, "local_scope_requires_guarded_adapter")


if __name__ == "__main__":
    unittest.main()
