import unittest

from src_auto.cli import build_parser


class DefenseCliContractTests(unittest.TestCase):
    def test_defense_commands_are_explicit_and_project_artifact_based(self):
        parser = build_parser()
        cases = [
            (["defense-register", "--asset", "asset.json", "--output", "registered.json"], "defense-register"),
            (["defense-plan", "--asset", "asset.json", "--output", "plan.json"], "defense-plan"),
            (["defense-import-log", "--input", "access.jsonl", "--output", "log.json"], "defense-import-log"),
            (["defense-report", "--asset", "asset.json", "--log-report", "log.json", "--output", "report.json"], "defense-report"),
        ]
        for argv, command in cases:
            args = parser.parse_args(argv)
            self.assertEqual(args.command, command)
            self.assertTrue(args.output.endswith(".json"))

    def test_defense_report_requires_local_inputs(self):
        parser = build_parser()
        args = parser.parse_args(
            ["defense-report", "--asset", "asset.json", "--log-report", "log.json", "--output", "report.json"]
        )
        self.assertEqual(args.log_report, "log.json")
        self.assertFalse(hasattr(args, "execute"))


if __name__ == "__main__":
    unittest.main()
