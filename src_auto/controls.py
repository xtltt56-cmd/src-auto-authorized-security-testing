import datetime as _dt
import os
import shutil
import stat
from pathlib import Path
from typing import Callable, Dict, List, Optional


class BudgetGovernor:
    def __init__(self, monthly_limit: float, daily_limit: float, now_fn: Optional[Callable[[], _dt.datetime]] = None):
        self.monthly_limit = float(monthly_limit)
        self.daily_limit = float(daily_limit)
        self.now_fn = now_fn or _dt.datetime.now
        self.records: List[Dict[str, object]] = []

    def _now(self) -> _dt.datetime:
        value = self.now_fn()
        return value.replace(tzinfo=None) if value.tzinfo else value

    def _spent(self, predicate: Callable[[_dt.datetime], bool]) -> float:
        return sum(float(item["amount"]) for item in self.records if predicate(item["at"]))  # type: ignore[arg-type]

    def can_spend(self, amount: float) -> bool:
        amount = float(amount)
        if amount < 0:
            raise ValueError("amount cannot be negative")
        now = self._now()
        month_spent = self._spent(lambda value: value.year == now.year and value.month == now.month)
        day_spent = self._spent(lambda value: value.date() == now.date())
        return month_spent + amount <= self.monthly_limit and day_spent + amount <= self.daily_limit

    def record(self, amount: float, category: str) -> None:
        if not self.can_spend(amount):
            raise RuntimeError("budget_limit_exceeded")
        self.records.append({"amount": float(amount), "category": str(category), "at": self._now()})

    def status(self) -> Dict[str, float]:
        now = self._now()
        month_spent = self._spent(lambda value: value.year == now.year and value.month == now.month)
        day_spent = self._spent(lambda value: value.date() == now.date())
        return {
            "spent": month_spent,
            "daily_spent": day_spent,
            "monthly_limit": self.monthly_limit,
            "daily_limit": self.daily_limit,
            "remaining": max(0.0, self.monthly_limit - month_spent),
        }


class DiskGuard:
    def __init__(
        self,
        root: Path,
        warn_used_gb: float = 80.0,
        hard_used_gb: float = 90.0,
        used_gb_fn: Optional[Callable[[Path], float]] = None,
    ):
        self.root = Path(root)
        self.warn_used_gb = float(warn_used_gb)
        self.hard_used_gb = float(hard_used_gb)
        self.used_gb_fn = used_gb_fn or self._measure_used_gb

    @staticmethod
    def _measure_used_gb(root: Path) -> float:
        # The project limit is for this workspace, not all unrelated data on the D: volume.
        total = 0
        pending = [str(root)]
        while pending:
            # On Windows DirEntry.stat reuses directory-enumeration metadata.
            # Path.is_file + Path.stat did redundant per-file system calls and
            # consumed the local request task deadline on this workspace.
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    metadata = entry.stat(follow_symlinks=False)
                    if getattr(metadata, "st_file_attributes", 0) & 0x400:
                        continue  # Windows junction/symlink must not count another project.
                    if stat.S_ISDIR(metadata.st_mode):
                        pending.append(entry.path)
                    elif stat.S_ISREG(metadata.st_mode):
                        total += metadata.st_size
        return total / (1024 ** 3)

    def check(self) -> Dict[str, object]:
        try:
            used = float(self.used_gb_fn(self.root))
        except OSError:
            return {"allowed": False, "known": False, "reason": "disk_measurement_unavailable", "root": str(self.root)}
        warning = used >= self.warn_used_gb
        allowed = used < self.hard_used_gb
        return {"allowed": allowed, "known": True, "warning": warning, "used_gb": round(used, 3), "root": str(self.root)}

    def assert_allowed(self) -> None:
        result = self.check()
        if not result["allowed"]:
            raise RuntimeError("disk_hard_limit_exceeded")


class StopController:
    def __init__(self, marker: Path):
        self.marker = Path(marker)

    def requested(self) -> bool:
        return self.marker.exists()

    def request(self) -> None:
        self.marker.parent.mkdir(parents=True, exist_ok=True)
        self.marker.write_text("stop requested\n", encoding="utf-8")

    def clear(self) -> None:
        if self.marker.exists():
            self.marker.unlink()


class ResourceGuard:
    """Soft CPU/RAM gate; no psutil dependency is required for the local control layer."""

    def __init__(self, max_cpu_percent: float = 70.0, max_memory_gb: float = 30.0, metrics_fn=None):
        self.max_cpu_percent = float(max_cpu_percent)
        self.max_memory_gb = float(max_memory_gb)
        self.metrics_fn = metrics_fn

    def check(self) -> Dict[str, object]:
        if self.metrics_fn is None:
            return {"allowed": True, "known": False, "reason": "metrics_unavailable"}
        cpu, memory = self.metrics_fn()
        allowed = float(cpu) <= self.max_cpu_percent and float(memory) <= self.max_memory_gb
        return {"allowed": allowed, "known": True, "cpu_percent": float(cpu), "memory_gb": float(memory)}
