import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


class DashboardStaticServerTests(unittest.TestCase):
    def setUp(self):
        from src_auto.dashboard_web import create_static_server

        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        (root / "assets").mkdir()
        (root / "index.html").write_text("<h1>SRC-Auto Dashboard</h1>", encoding="utf-8")
        (root / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
        self.server = create_static_server(root, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:{}".format(self.server.server_address[1])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def test_serves_index_with_security_headers(self):
        with urlopen(self.base_url + "/", timeout=2) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("SRC-Auto Dashboard", body)
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_serves_asset_and_spa_fallback(self):
        with urlopen(self.base_url + "/assets/app.js", timeout=2) as response:
            self.assertIn("javascript", response.headers["Content-Type"])
            self.assertEqual(response.read().decode("utf-8"), "console.log('ok')")
        with urlopen(self.base_url + "/labs/juice-shop", timeout=2) as response:
            self.assertIn("SRC-Auto Dashboard", response.read().decode("utf-8"))

    def test_rejects_non_loopback_host_header_and_missing_asset(self):
        import http.client

        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=2)
        connection.request("GET", "/", headers={"Host": "example.com"})
        response = connection.getresponse()
        self.assertEqual(response.status, 403)
        response.read()
        connection.close()
        with self.assertRaises(HTTPError) as missing:
            urlopen(self.base_url + "/assets/missing.js", timeout=2)
        self.assertEqual(missing.exception.code, 404)

    def test_proxies_only_api_routes_to_fixed_loopback_backend(self):
        class ApiHandler(BaseHTTPRequestHandler):
            def log_message(self, _format, *_args):
                return

            def do_GET(self):
                body = b'{"service":"api-fixture"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        backend = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
        backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
        backend_thread.start()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        from src_auto.dashboard_web import create_static_server

        self.server = create_static_server(
            Path(self.tempdir.name), port=0, api_port=backend.server_address[1]
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:{}".format(self.server.server_address[1])
        try:
            with urlopen(self.base_url + "/api/session", timeout=2) as response:
                self.assertEqual(response.read(), b'{"service":"api-fixture"}')
        finally:
            backend.shutdown()
            backend.server_close()
            backend_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
