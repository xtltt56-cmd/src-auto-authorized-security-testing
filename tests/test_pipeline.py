import tempfile
import unittest
from pathlib import Path

from src_auto.pipeline import PipelineRunner
from src_auto.scope import ScopeGuard, ScopePolicy
from src_auto.store import Store


class PipelineTests(unittest.TestCase):
    def test_local_pipeline_has_ordered_stages_and_no_network_requirement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "state.sqlite3")
            run_id = store.create_run("local-lab", "scope-a", "local")
            scope = ScopeGuard(
                ScopePolicy.from_mapping(
                    {
                        "target_id": "local-lab",
                        "root_domains": ["localhost"],
                        "allowed_hosts": ["localhost"],
                        "allowed_ports": [8765],
                        "confirmed": True,
                        "allow_network_contact": True,
                    }
                )
            )
            fixture = {
                "assets": [{"host": "localhost", "port": 8765, "url": "http://localhost:8765/"}],
                "findings": [
                    {
                        "title": "Missing security header",
                        "url": "http://localhost:8765/",
                        "severity": "low",
                        "evidence": "X-Content-Type-Options absent",
                    }
                ],
            }
            result = PipelineRunner(store, scope, root).run_local(run_id, fixture)
            store.close()
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["stages"], [
                "asset_discovery", "http_probe", "crawl", "candidate_scan",
                "passive_scan", "normalize", "dedup", "triage", "evidence", "report",
            ])


if __name__ == "__main__":
    unittest.main()
