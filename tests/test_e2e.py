import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from lab.server import Handler
from src_auto.config import load_mapping
from src_auto.pipeline import PipelineRunner
from src_auto.scope import ScopeGuard, ScopePolicy
from src_auto.store import Store
from http.server import ThreadingHTTPServer


class E2ETests(unittest.TestCase):
    def test_loopback_server_and_report_chain(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                store = Store(root / "data.sqlite3")
                scope = ScopeGuard(
                    ScopePolicy.from_mapping(
                        {
                            "target_id": "loopback",
                            "root_domains": ["localhost"],
                            "allowed_hosts": ["localhost", "127.0.0.1"],
                            "allowed_ports": [port],
                            "confirmed": True,
                            "allow_network_contact": True,
                        }
                    )
                )
                url = "http://127.0.0.1:{}/".format(port)
                self.assertIn(b"SRC-Auto local lab", urlopen(url, timeout=3).read())
                run_id = store.create_run("loopback", scope.policy.digest(), "local")
                fixture = load_mapping(Path(__file__).parents[1] / "lab" / "fixtures.json")
                fixture["assets"][0]["port"] = port
                fixture["assets"][0]["url"] = url
                fixture["findings"][0]["url"] = url
                fixture["findings"][1]["url"] = url
                result = PipelineRunner(store, scope, root).run_local(run_id, fixture)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["finding_count"], 1)
                self.assertTrue((root / "reports" / (run_id + ".md")).exists())
                evidence = list((root / "evidence" / run_id).glob("*.json"))
                self.assertEqual(len(evidence), 1)
                self.assertTrue(any(event["message"] == "finding_out_of_scope" for event in store.list_events(run_id)))
                store.close()
        except Exception:
            try:
                store.close()
            except (UnboundLocalError, AttributeError):
                pass
            raise
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
