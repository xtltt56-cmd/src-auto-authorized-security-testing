import tempfile
import unittest
from pathlib import Path

from src_auto.adapters import SafeToolAdapter, ToolRegistry
from src_auto.scope import ScopeGuard, ScopePolicy


class AdapterTests(unittest.TestCase):
    def test_out_of_scope_target_is_blocked_before_process_start(self):
        guard = ScopeGuard(
            ScopePolicy.from_mapping(
                {
                    "target_id": "local",
                    "allowed_hosts": ["localhost"],
                    "allowed_ports": [8765],
                    "confirmed": True,
                    "allow_network_contact": True,
                }
            )
        )
        registry = ToolRegistry(commands={"fake": "definitely-not-a-real-command"})
        result = SafeToolAdapter("fake", registry).run([], guard, ["https://third-party.example/"])
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.detail, "host_not_in_scope")

    def test_missing_binary_is_explicitly_unavailable(self):
        guard = ScopeGuard(ScopePolicy.from_mapping({"target_id": "x", "confirmed": True, "allow_network_contact": True, "allowed_hosts": ["localhost"], "allowed_ports": [80]}))
        result = SafeToolAdapter("missing", ToolRegistry()).run([], guard, ["http://localhost/"])
        self.assertEqual(result.status, "unavailable")


if __name__ == "__main__":
    unittest.main()
