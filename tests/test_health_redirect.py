import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from src_auto.local_labs import LocalLabManager


class HealthRedirectTests(unittest.TestCase):
    def test_redirect_is_blocked_before_contact_and_first_request_is_recorded(self):
        hits = []
        class Destination(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(True)
                self.send_response(200)
                self.end_headers()
            def log_message(self, *args): pass
        dest = ThreadingHTTPServer(('127.0.0.1', 0), Destination)
        class Redirect(Destination):
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', 'http://127.0.0.1:%s/' % dest.server_port)
                self.end_headers()
        source = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
        servers = (source, dest)
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        manager = LocalLabManager.__new__(LocalLabManager)
        manager.status = lambda _: {'status': 'UNHEALTHY'}
        spec = SimpleNamespace(lab_id='test', host_port=source.server_port,
                               health_url='http://127.0.0.1:%s/' % source.server_port)
        try:
            result = manager._wait_health(spec, timeout=2)
            self.assertEqual(hits, [])
            self.assertTrue(result['network_contact'])
            self.assertNotEqual(result['status'], 'READY')
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
