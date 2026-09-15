import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src_auto.offline_scope_picker import discover_review_targets, inspect_review_targets


class OfflineScopePickerTests(unittest.TestCase):
    def test_discovers_nested_confirmed_scope_only_when_plan_is_present(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "config" / "targets"
            valid = root / "group" / "juice-shop"
            missing_plan = root / "group" / "missing-plan"
            candidate_only = root / "draft-target"
            valid.mkdir(parents=True)
            missing_plan.mkdir(parents=True)
            candidate_only.mkdir(parents=True)
            (valid / "scope_confirmed.yaml").write_text(
                "target: juice-shop\n", encoding="utf-8"
            )
            (valid / "live_plan.yaml").write_text(
                "plan: offline\n", encoding="utf-8"
            )
            (missing_plan / "scope_confirmed.yaml").write_text(
                "target: incomplete\n", encoding="utf-8"
            )
            (candidate_only / "scope_candidate.yaml").write_text(
                "target: draft\n", encoding="utf-8"
            )

            found = discover_review_targets(root, root)

            self.assertEqual(
                [item.scope_path for item in found],
                [(valid / "scope_confirmed.yaml").resolve()],
            )
            self.assertEqual(found[0].plan_path, (valid / "live_plan.yaml").resolve())
            self.assertEqual(found[0].target_dir, valid.resolve())
            self.assertEqual(found[0].relative_name, "group/juice-shop")

    def test_direct_target_directory_can_be_selected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "config" / "targets"
            selected = root / "group" / "target-a"
            selected.mkdir(parents=True)
            (selected / "scope_confirmed.yaml").write_text(
                "target: target-a\n", encoding="utf-8"
            )
            (selected / "live_plan.yaml").write_text(
                "plan: offline\n", encoding="utf-8"
            )

            found = discover_review_targets(selected, root)

            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].relative_name, "group/target-a")

    def test_rejects_a_directory_outside_targets_root(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "config" / "targets"
            outside = Path(raw) / "elsewhere"
            root.mkdir(parents=True)
            outside.mkdir()

            with self.assertRaisesRegex(ValueError, "outside_targets_root"):
                discover_review_targets(outside, root)

    def test_rejects_a_missing_or_non_directory_selection(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "config" / "targets"
            root.mkdir(parents=True)
            file_path = root / "not-a-directory.txt"
            file_path.write_text("local fixture", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "selected_directory_missing"):
                discover_review_targets(root / "missing", root)
            with self.assertRaisesRegex(ValueError, "selected_path_not_directory"):
                discover_review_targets(file_path, root)

    def test_inspection_reports_confirmed_candidate_and_missing_plan_states(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "config" / "targets"
            ready = root / "ready"
            missing_plan = root / "missing-plan"
            candidate = root / "candidate"
            for directory in (ready, missing_plan, candidate):
                directory.mkdir(parents=True)
            (ready / "scope_confirmed.yaml").write_text("target: ready\n", encoding="utf-8")
            (ready / "live_plan.yaml").write_text("plan: offline\n", encoding="utf-8")
            (missing_plan / "scope_confirmed.yaml").write_text(
                "target: missing-plan\n", encoding="utf-8"
            )
            (candidate / "scope_candidate.yaml").write_text(
                "target: candidate\n", encoding="utf-8"
            )

            entries = inspect_review_targets(root, root)

            by_name = {entry.relative_name: entry for entry in entries}
            self.assertTrue(by_name["ready"].actionable)
            self.assertEqual(by_name["ready"].status, "ready")
            self.assertFalse(by_name["missing-plan"].actionable)
            self.assertEqual(by_name["missing-plan"].status, "missing_plan")
            self.assertFalse(by_name["candidate"].actionable)
            self.assertEqual(by_name["candidate"].status, "candidate_only")

    def test_module_cli_returns_machine_readable_local_targets(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "config" / "targets"
            target = root / "group" / "target-a"
            target.mkdir(parents=True)
            (target / "scope_confirmed.yaml").write_text(
                "target: target-a\n", encoding="utf-8"
            )
            (target / "live_plan.yaml").write_text(
                "plan: offline\n", encoding="utf-8"
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src_auto.offline_scope_picker",
                    "--selected",
                    str(root),
                    "--root",
                    str(root),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["entries"][0]["status"], "ready")
            self.assertEqual(payload["targets"][0]["relative_name"], "group/target-a")
            self.assertEqual(
                Path(payload["targets"][0]["scope_path"]).resolve(),
                (target / "scope_confirmed.yaml").resolve(),
            )

    def test_module_cli_fails_closed_for_outside_directory(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "config" / "targets"
            outside = Path(raw) / "outside"
            root.mkdir(parents=True)
            outside.mkdir()

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src_auto.offline_scope_picker",
                    "--selected",
                    str(outside),
                    "--root",
                    str(root),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(completed.returncode, 2)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload, {"status": "blocked", "reason": "outside_targets_root"})


if __name__ == "__main__":
    unittest.main()
