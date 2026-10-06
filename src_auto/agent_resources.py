"""Read-only Windows resource observations; reuse the balanced policy limits."""
import ctypes
import os
import time
from ctypes import wintypes

from .controls import ResourceGuard


class WindowsResources:
    def __init__(self, policy):
        self.previous = None
        self.previous_sampled_at = None
        self.cpu_percent = 0.0
        self.guard = ResourceGuard(float(policy.get("max_cpu_percent", 70)), float(policy.get("max_memory_gb", 30)), metrics_fn=self.metrics)

    def _sample_cpu(self, idle, total, now):
        # Tool polling can call gates every few milliseconds. Keep cumulative
        # counters until a measured interval is available, rather than treating
        # one quantized Windows accounting tick as sustained system saturation.
        if self.previous is None:
            self.previous, self.previous_sampled_at = (idle, total), now
        elif now - self.previous_sampled_at >= 0.25 and total > self.previous[1]:
            self.cpu_percent = max(0.0, min(100.0, 100.0 * (1.0 - (idle - self.previous[0]) / (total - self.previous[1]))))
            self.previous, self.previous_sampled_at = (idle, total), now
        return self.cpu_percent

    def metrics(self):
        class Memory(ctypes.Structure):
            _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [(name, ctypes.c_ulonglong) for name in
                ("total", "available", "total_page", "available_page", "total_virtual", "available_virtual", "extended")]
        memory = Memory(); memory.length = ctypes.sizeof(memory)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)): raise OSError("memory_metrics_unavailable")
        values = [wintypes.FILETIME() for _ in range(3)]
        if not ctypes.windll.kernel32.GetSystemTimes(*(ctypes.byref(x) for x in values)): raise OSError("cpu_metrics_unavailable")
        idle, kernel, user = [(x.dwHighDateTime << 32) + x.dwLowDateTime for x in values]
        cpu = self._sample_cpu(idle, kernel + user, time.monotonic())
        return cpu, (memory.total - memory.available) / 1024 ** 3

    def check(self):
        if os.name != "nt":
            # Do not pretend unmeasured system limits have been checked.
            return {"allowed": False, "known": False, "reason": "windows_resource_metrics_required"}
        try:
            first = self.previous is None
            if first:
                self.metrics()
                time.sleep(0.25)  # A measured initial interval, not fabricated 0% CPU.
            result = self.guard.check()
            result["memoryMetric"] = "system_used_gb"
            result["max_memory_gb"] = self.guard.max_memory_gb
            result["max_cpu_percent"] = self.guard.max_cpu_percent
            result["cpuFirstSample"] = first
            return result
        except (OSError, AttributeError):
            return {"allowed": False, "known": False, "reason": "resource_metrics_unavailable"}
