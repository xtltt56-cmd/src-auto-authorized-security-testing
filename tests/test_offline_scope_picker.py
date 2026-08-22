from pathlib import Path
import tempfile
import unittest

from src_auto.offline_scope_picker import discover_review_targets


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
                [valid / "scope_confirmed.yaml"],
            )
            self.assertEqual(found[0].plan_path, valid / "live_plan.yaml")
            self.assertEqual(found[0].target_dir, valid)
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


if __name__ == "__main__":
    unittest.main()
