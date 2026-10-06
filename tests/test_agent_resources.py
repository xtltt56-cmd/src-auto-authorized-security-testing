import unittest
from unittest.mock import patch

from src_auto.agent_resources import WindowsResources
from src_auto.controls import ResourceGuard


class AgentResourceTests(unittest.TestCase):
    def test_cpu_counter_sampling_does_not_reset_on_rapid_tool_gates(self):
        resources = WindowsResources({})
        resources._sample_cpu(0, 0, 10.0)
        self.assertAlmostEqual(resources._sample_cpu(95, 100, 10.25), 5)
        # A 10 ms quantized counter burst must not replace the measured interval.
        self.assertAlmostEqual(resources._sample_cpu(95, 110, 10.26), 5)
        # Once a complete interval really exceeds the unchanged CPU limit, block.
        cpu = resources._sample_cpu(110, 200, 10.50)
        self.assertGreater(cpu, 70)
        self.assertFalse(ResourceGuard(metrics_fn=lambda: (cpu, 20)).check()['allowed'])

    def test_default_memory_boundary_preserves_cpu_and_explicit_limits(self):
        for factory in (lambda cpu, memory: ResourceGuard(metrics_fn=lambda: (cpu, memory)),
                        lambda cpu, memory: WindowsResources({}).guard):
            for cpu, memory, expected in ((30, 29.9, True), (30, 30, True),
                                          (30, 30.1, False), (70.1, 29, False)):
                with self.subTest(cpu=cpu, memory=memory, factory=factory):
                    guard = factory(cpu, memory)
                    guard.metrics_fn = lambda: (cpu, memory)
                    self.assertEqual(guard.check()["allowed"], expected)
        self.assertFalse(ResourceGuard(max_memory_gb=20, metrics_fn=lambda: (30, 21)).check()["allowed"])

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
