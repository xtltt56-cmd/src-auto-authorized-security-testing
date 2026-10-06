import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src_auto.controls import DiskGuard


class DiskMeasurementTests(unittest.TestCase):
    def test_measure_uses_cached_directory_metadata_and_counts_real_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "nested").mkdir()
            (root / "a.bin").write_bytes(b"a" * 12)
            (root / "nested" / "b.bin").write_bytes(b"b" * 23)
            with patch.object(Path, "rglob", side_effect=AssertionError("avoid per-file Path.stat traversal")):
                self.assertEqual(DiskGuard._measure_used_gb(root), 35 / 1024 ** 3)

    def test_windows_reparse_points_are_not_traversed_or_counted(self):
        with tempfile.TemporaryDirectory() as temp:
            entry = Mock(path="outside-project")
            entry.stat.return_value = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400, st_size=100)
            with patch("os.scandir") as scan:
                scan.return_value.__enter__.return_value = iter([entry])
                self.assertEqual(DiskGuard._measure_used_gb(Path(temp)), 0)
                self.assertEqual(scan.call_count, 1)

    def test_unreadable_workspace_does_not_report_zero_usage_as_safe(self):
        def unavailable(root):
            raise PermissionError("synthetic unreadable directory")
        result = DiskGuard(Path("unused"), used_gb_fn=unavailable).check()
        self.assertFalse(result["allowed"])
        self.assertFalse(result["known"])
        self.assertEqual(result["reason"], "disk_measurement_unavailable")

    def test_missing_workspace_is_unknown_and_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            result = DiskGuard(Path(temp) / "missing").check()
            self.assertFalse(result["allowed"])
            self.assertFalse(result["known"])


if __name__ == "__main__":
    unittest.main()
