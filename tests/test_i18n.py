import unittest

from src_auto.i18n import human_summary, reason_zh, status_zh, with_zh_fields


class I18NTests(unittest.TestCase):
    def test_known_status_and_reason_have_simplified_chinese_text(self):
        self.assertEqual(status_zh("reachable"), "可访问")
        self.assertEqual(reason_zh("confirm_local_required"), "需要明确确认本机靶场")
        self.assertEqual(reason_zh("host_not_in_scope"), "目标主机不在已确认范围内")

    def test_unknown_values_fall_back_without_changing_machine_value(self):
        self.assertEqual(status_zh("future_status"), "future_status")
        self.assertEqual(reason_zh("future_reason"), "future_reason")

    def test_zh_fields_preserve_machine_fields(self):
        document = with_zh_fields(
            {"status": "POSSIBLE_FINDINGS", "reason": "manual_verification_required"}
        )
        self.assertEqual(document["status"], "POSSIBLE_FINDINGS")
        self.assertEqual(document["status_zh"], "存在待人工复核的可能项")
        self.assertEqual(document["reason_zh"], "需要人工复核后才能确认")

    def test_human_summary_uses_safe_fields(self):
        summary = human_summary(
            "juice-shop-status",
            {
                "status": "reachable",
                "http_status": 200,
                "url": "http://127.0.0.1:3000/",
                "title": "OWASP Juice Shop",
                "network_contact": True,
                "secret": "must-not-print",
            },
        )
        self.assertIn("本地 OWASP Juice Shop", summary)
        self.assertIn("状态：可访问", summary)
        self.assertNotIn("must-not-print", summary)

    def test_human_summary_lists_findings_without_raw_evidence(self):
        summary = human_summary(
            "findings",
            [
                {
                    "title": "Missing security header",
                    "status": "POSSIBLE",
                    "url": "http://127.0.0.1:3000/",
                    "evidence": "secret-token-value",
                }
            ],
        )
        self.assertIn("Finding 数量：1", summary)
        self.assertIn("Missing security header", summary)
        self.assertNotIn("secret-token-value", summary)

    def test_remote_preview_human_summary_keeps_digest_visible(self):
        summary = human_summary(
            "remote-preview",
            {
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "finding_id": 7,
                "payload_digest": "a" * 64,
                "payload": {"evidence": "redacted"},
            },
        )
        self.assertIn("远程 AI 预览不会联网", summary)
        self.assertIn("脱敏内容摘要：" + ("a" * 64), summary)


if __name__ == "__main__":
    unittest.main()
