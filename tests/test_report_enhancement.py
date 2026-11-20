"""L3 increment 2: enriched Butian candidate report (manual-review draft).

Written before production behavior (project contract). Stdlib + temp fixtures
only; renders stored finding/triage fields and marks missing ones for humans.
No real target, network, or Butian submission is performed.
"""
import tempfile
import unittest
from pathlib import Path

from src_auto.reporting import ButianReportGenerator
from src_auto.store import Store


def _candidate(run_id, **over):
    base = {
        "run_id": run_id,
        "title": "Reflected XSS",
        "url": "http://localhost:8765/search",
        "parameter": "q",
        "vuln_type": "xss",
        "severity": "high",
        "confidence": 0.8,
        "evidence": "q 参数值被反射到响应",
        "scanner": "zap",
        "template_id": "10016",
        "matched_at": "http://localhost:8765/search",
        "cwe": "CWE-79",
        "cvss": 6.1,
    }
    base.update(over)
    return base


class ReportEnhancementTests(unittest.TestCase):
    def test_report_renders_enriched_fields_sources_and_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            try:
                run_id = store.create_run("local", "scope-hash", "real")
                fp = store.insert_candidate(_candidate(run_id)).fingerprint
                store.insert_candidate(_candidate(run_id, scanner="nuclei", template_id="xss-reflected"))
                store.update_finding_triage(
                    fp,
                    {"reproduction": "访问 /search 观察 q 参数反射", "remediation": "对输出做 HTML 编码"},
                    status="triaged",
                )
                rows = store.list_findings(run_id)
                report = ButianReportGenerator(root, store).generate(run_id, "scope-hash", rows)
                text = report.read_text(encoding="utf-8")
                self.assertIn("Reflected XSS", text)
                self.assertIn("xss", text)
                self.assertIn("CWE-79", text)
                self.assertIn("6.1", text)
                self.assertIn("参数", text)
                self.assertIn("置信度", text)
                self.assertIn("zap", text)
                self.assertIn("nuclei", text)
                self.assertIn("triaged", text)
                self.assertIn("访问 /search 观察 q 参数反射", text)
                self.assertIn("对输出做 HTML 编码", text)
                self.assertIn("候选总数", text)
                self.assertIn("严重性分布", text)
                self.assertIn("队列状态分布", text)
            finally:
                store.close()

    def test_report_marks_missing_repro_remediation_and_cwe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            try:
                run_id = store.create_run("local", "scope-hash", "real")
                store.insert_candidate(_candidate(run_id, cwe="", cvss=None))
                rows = store.list_findings(run_id)
                text = ButianReportGenerator(root, store).generate(run_id, "scope-hash", rows).read_text(encoding="utf-8")
                self.assertIn("待人工补充最小复现步骤", text)
                self.assertIn("待人工评估修复建议", text)
                self.assertIn("待映射", text)
                self.assertIn("待评估", text)
            finally:
                store.close()

    def test_report_empty_findings_keeps_draft_notice(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            try:
                run_id = store.create_run("local", "scope-hash", "real")
                text = ButianReportGenerator(root, store).generate(run_id, "scope-hash", []).read_text(encoding="utf-8")
                self.assertIn("没有候选 Finding", text)
                self.assertIn("不会自动提交补天", text)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()