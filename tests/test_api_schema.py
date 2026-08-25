import unittest
from pathlib import Path


class ApiSchemaSmokeTests(unittest.TestCase):
    def test_local_schema_command_is_read_only_bounded_and_utf8_wrapped(self):
        from src_auto.api_schema import build_local_schema_smoke_command

        command = build_local_schema_smoke_command(
            Path(r"D:\网络安全文件夹\SRC-Auto"),
            "http://127.0.0.1:8083/openapi.json",
            Path(r"D:\网络安全文件夹\SRC-Auto\validation\vampi\schema"),
        )
        text = " ".join(command)
        self.assertIn("vendor\\bin\\schemathesis.cmd", text)
        self.assertIn("--include-method GET", text)
        self.assertIn("--phases examples", text)
        self.assertIn("--max-examples 1", text)
        self.assertIn("--rate-limit 20/m", text)
        self.assertNotIn("POST", text)
        self.assertNotIn("DELETE", text)

    def test_schema_result_treats_contract_failures_as_candidate_not_crash(self):
        from src_auto.api_schema import classify_schema_smoke_result

        candidate = classify_schema_smoke_result(1, True)
        self.assertEqual(candidate["status"], "POSSIBLE_SCHEMA_CONTRACT_ISSUES")
        self.assertTrue(candidate["manual_review_required"])
        self.assertFalse(candidate["confirmed"])
        success = classify_schema_smoke_result(0, True)
        self.assertEqual(success["status"], "COMPLETED")
        missing = classify_schema_smoke_result(1, False)
        self.assertEqual(missing["status"], "FAILED_RUNTIME")

    def test_schema_command_rejects_non_loopback_or_external_output(self):
        from src_auto.api_schema import ApiSchemaError, build_local_schema_smoke_command

        root = Path(r"D:\网络安全文件夹\SRC-Auto")
        with self.assertRaisesRegex(ApiSchemaError, "schema_url_must_be_loopback"):
            build_local_schema_smoke_command(root, "https://example.com/openapi.json", root / "validation")
        with self.assertRaisesRegex(ApiSchemaError, "output_outside_project"):
            build_local_schema_smoke_command(root, "http://127.0.0.1:8083/openapi.json", Path(r"C:\Temp"))


if __name__ == "__main__":
    unittest.main()
