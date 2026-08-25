import unittest

from src_auto.local_discovery import discover_documents, discover_local_surface, redact_headers
from src_auto.runtime_policy import RuntimePolicy


class LocalDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.policy = RuntimePolicy.from_mapping(
            {
                "AI_PROVIDER": "local",
                "LOCAL_LLM_ONLY": True,
                "ALLOW_REMOTE_LLM": False,
                "allowed_hosts": ["127.0.0.1", "localhost"],
                "allowed_ports": [3000],
                "max_concurrency": 2,
            }
        )

    def test_document_discovery_extracts_api_routes_and_excludes_external_urls(self):
        result = discover_documents(
            "http://127.0.0.1:3000/",
            [
                ("http://127.0.0.1:3000/", "text/html", '<script src="/main.js"></script><a href="/login">Login</a>'),
                ("http://127.0.0.1:3000/main.js", "text/javascript", "fetch('/api/Users?q=x'); fetch('https://outside.example/x'); fetch('http://api.ipinfodb.com/v3/ip-country'); const path='/basket';"),
            ],
            self.policy,
        )
        self.assertIn("http://127.0.0.1:3000/api/Users?q=x", result["api_urls"])
        self.assertIn("http://127.0.0.1:3000/login", result["auth_surface"])
        self.assertIn("http://127.0.0.1:3000/basket", result["client_routes"])
        self.assertIn("https://outside.example/x", result["external_urls_excluded"])
        self.assertNotIn("http://127.0.0.1:3000/api.ipinfodb.com/v3/ip-country", result["api_urls"])
        self.assertEqual(result["network_contact"], False)

    def test_static_surface_fetches_only_allowlisted_urls_and_redacts_headers(self):
        calls = []
        documents = {
            "http://127.0.0.1:3000/": ("text/html", '<script src="/app.js"></script><script src="https://outside.example/x.js"></script>', {"Content-Type": "text/html"}),
            "http://127.0.0.1:3000/app.js": ("text/javascript", "fetch('/rest/data');", {"Content-Type": "text/javascript", "Authorization": "Bearer secret"}),
        }

        def fetch(url):
            calls.append(url)
            content_type, body, headers = documents[url]
            return {"url": url, "final_url": url, "content_type": content_type, "body": body, "headers": headers}

        result = discover_local_surface(self.policy, "http://127.0.0.1:3000/", fetch_fn=fetch)
        self.assertEqual(calls, ["http://127.0.0.1:3000/", "http://127.0.0.1:3000/app.js"])
        self.assertIn("http://127.0.0.1:3000/rest/data", result["api_urls"])
        self.assertIn("https://outside.example/x.js", result["external_urls_excluded"])
        self.assertEqual(result["network_contact"], True)
        self.assertNotIn("secret", str(result))

    def test_static_parser_does_not_count_minified_symbols_as_client_routes(self):
        result = discover_documents(
            "http://127.0.0.1:3000/",
            [("http://127.0.0.1:3000/app.js", "text/javascript", "const a='/a'; const basket='/basket'; const x='/:/g';")],
            self.policy,
        )
        self.assertIn("http://127.0.0.1:3000/basket", result["client_routes"])
        self.assertNotIn("http://127.0.0.1:3000/a", result["client_routes"])
        self.assertNotIn("http://127.0.0.1:3000/:/g", result["client_routes"])

    def test_sensitive_headers_are_replaced(self):
        result = redact_headers({"Authorization": "Bearer abc", "Cookie": "sid=secret", "Content-Type": "text/html"})
        self.assertEqual(result["authorization"], "<redacted>")
        self.assertEqual(result["cookie"], "<redacted>")
        self.assertEqual(result["content-type"], "text/html")


if __name__ == "__main__":
    unittest.main()
