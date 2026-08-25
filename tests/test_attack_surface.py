import tempfile
import unittest
from pathlib import Path

from src_auto.scope import ScopeGuard, ScopePolicy
from src_auto.store import Store


class AttackSurfaceTests(unittest.TestCase):
    def _guard(self, confirmed=True):
        return ScopeGuard(
            ScopePolicy.from_mapping(
                {
                    "target_id": "owned-example",
                    "root_domains": ["example.test"],
                    "allowed_hosts": ["example.test"],
                    "excluded_hosts": ["third-party.example.test"],
                    "allowed_ports": [443],
                    "confirmed": confirmed,
                    "allow_network_contact": confirmed,
                }
            )
        )

    def test_target_normalizes_https_url_and_rejects_credentials(self):
        from src_auto.attack_surface import AttackSurfaceError, AttackSurfaceTarget

        target = AttackSurfaceTarget.from_url("owned-example", "HTTPS://Example.Test:443/path?q=1")
        self.assertEqual(target.root_url, "https://example.test:443/")
        self.assertEqual(target.hostname, "example.test")
        with self.assertRaisesRegex(AttackSurfaceError, "credentials_not_allowed"):
            AttackSurfaceTarget.from_url("bad", "https://user:pass@example.test/")

    def test_plan_requires_confirmed_scope_and_explicit_automation_permission(self):
        from src_auto.attack_surface import AttackSurfaceError, AttackSurfaceTarget, build_attack_surface_plan

        target = AttackSurfaceTarget.from_url("owned-example", "https://example.test/")
        with self.assertRaisesRegex(AttackSurfaceError, "scope_confirmation_required"):
            build_attack_surface_plan(target, self._guard(False), True, {"subfinder"})
        with self.assertRaisesRegex(AttackSurfaceError, "automation_permission_required"):
            build_attack_surface_plan(target, self._guard(True), False, {"subfinder"})

    def test_plan_uses_only_bounded_reviewed_tool_arguments(self):
        from src_auto.attack_surface import AttackSurfaceTarget, build_attack_surface_plan

        target = AttackSurfaceTarget.from_url("owned-example", "https://example.test/")
        plan = build_attack_surface_plan(
            target,
            self._guard(True),
            True,
            {"subfinder", "httpx", "katana", "nuclei", "bbot", "zap", "schemathesis"},
        ).to_mapping()

        self.assertEqual(plan["target_urls"], ["https://example.test/"])
        self.assertEqual(plan["max_requests_per_second"], 2)
        self.assertIn("subfinder", plan["sequence"])
        self.assertIn("nuclei", plan["sequence"])
        self.assertNotIn("schemathesis", plan["sequence"])
        self.assertEqual(plan["commands"]["bbot"][-2:], ["-p", "passive"])
        nuclei = " ".join(plan["commands"]["nuclei"]).lower()
        for required in ("-rl 2", "-c 1", "-bs 1", "-no-interactsh", "-disable-unsigned-templates"):
            self.assertIn(required, nuclei)
        for forbidden in ("fuzz", "headless", "code", "interactsh-url", "rate-limit 100"):
            self.assertNotIn(forbidden, nuclei)
        self.assertFalse(plan["execute"])
        self.assertTrue(plan["manual_execution_required"])

    def test_snapshot_and_diff_report_keep_only_bounded_asset_metadata(self):
        from src_auto.attack_surface import render_asset_diff_report, save_asset_snapshot

        with tempfile.TemporaryDirectory() as raw:
            store = Store(Path(raw) / "state.sqlite3")
            try:
                first = store.create_run("owned-example", "scope", "defense")
                save_asset_snapshot(
                    store,
                    first,
                    [{"host": "example.test", "port": 443, "url": "https://example.test/", "title": "Home", "body": "must-not-persist"}],
                )
                second = store.create_run("owned-example", "scope", "defense")
                save_asset_snapshot(
                    store,
                    second,
                    [
                        {"host": "example.test", "port": 443, "url": "https://example.test/", "title": "Home"},
                        {"host": "api.example.test", "port": 443, "url": "https://api.example.test/", "status_code": 200},
                    ],
                )
                report = render_asset_diff_report(store, first, second)
                self.assertEqual(report["summary"], {"added": 1, "removed": 0, "unchanged": 1})
                row = store.conn.execute("SELECT metadata_json FROM assets WHERE host='example.test'").fetchone()
                self.assertNotIn("must-not-persist", row[0])
                self.assertNotIn("body", row[0])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
