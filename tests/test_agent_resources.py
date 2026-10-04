import unittest
from unittest.mock import patch

from src_auto.agent_resources import WindowsResources


class AgentResourceTests(unittest.TestCase):
    def test_first_gate_measures_an_interval_instead_of_claiming_zero_cpu(self):
        resources = WindowsResources({"max_cpu_percent": 70, "max_memory_gb": 20})
        calls = []
        def metrics():
            calls.append(True); resources.previous = (1, 2)
            return (0 if len(calls) == 1 else 85), 8
        resources.metrics = metrics
        resources.guard.metrics_fn = metrics
        with patch("src_auto.agent_resources.os.name", "nt"), patch("src_auto.agent_resources.time.sleep"):
            result = resources.check()
        self.assertFalse(result["allowed"])
        self.assertEqual(result["cpu_percent"], 85)
        self.assertEqual(result["max_memory_gb"], 20)


if __name__ == "__main__": unittest.main()
