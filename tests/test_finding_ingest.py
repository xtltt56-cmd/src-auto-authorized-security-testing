"""L0/L1: schema migration, candidate ingestion, redaction and ZAP closed loop.

These tests are written before the production behavior (project contract).
They use only stdlib and loopback/temp fixtures; no real target is contacted.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src_auto.cli as cli
from src_auto.adapters import SafeToolAdapter, ToolRegistry
from src_auto.finding_ingest import ingest_zap_candidates
from src_auto.redaction import decode_tool_bytes, redact_tool_output
from src_auto.reporting import ButianReportGenerator
from src_auto.scope import ScopeGuard, ScopePolicy
from src_auto.store import Store

OLD_FINDINGS_DDL = """
CREATE TABLE findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    parameter TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info',
    evidence TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'candidate',
    triage_json TEXT NOT NULL DEFAULT '{}',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
"""

NEW_COLUMNS = {
    "vuln_type", "scanner", "template_id", "matched_at",
    "confidence", "cwe", "cvss", "sources_json",
}


def juice_scope():
    return ScopeGuard(
        ScopePolicy.from_mapping(
            {
                "target_id": "juice-shop-local",
                "allowed_hosts": ["127.0.0.1"],
                "allowed_ports": [3000],
                "confirmed": True,
                "allow_network_contact": True,
            }
        )
    )


def zap_parsed_fixture():
    return {
        "findings": [
            {
                "title": "Content Security Policy (CSP) Header Not Set",
                "endpoint": "http://127.0.0.1:3000/",
                "parameter": "",
                "method": "GET",
                "severity": "medium",
                "confidence": 0.9,
                "evidence": "CSP header absent",
                "scanner": "zap",
                "status": "POSSIBLE",
                "scanner_alert_id": "10038",
            },
            {
                "title": "Content Security Policy (CSP) Header Not Set",
                "endpoint": "http://127.0.0.1:3000/",
                "parameter": "",
                "method": "GET",
                "severity": "medium",
                "confidence": 0.9,
                "evidence": "CSP header absent (second instance)",
                "scanner": "zap",
                "status": "POSSIBLE",
                "scanner_alert_id": "10038",
            },
            {
                "title": "X-Frame-Options Header Not Set",
                "endpoint": "http://127.0.0.1:3000/",
                "parameter": "",
                "method": "GET",
                "severity": "low",
                "confidence": 0.7,
                "evidence": "X-Frame-Options absent",
                "scanner": "zap",
                "status": "POSSIBLE",
                "scanner_alert_id": "10020",
            },
            {
                "title": "Out Of Scope Alert",
                "endpoint": "https://third-party.example/",
                "parameter": "",
                "method": "GET",
                "severity": "high",
                "confidence": 0.9,
                "evidence": "must never be ingested",
                "scanner": "zap",
                "status": "POSSIBLE",
                "scanner_alert_id": "99999",
            },
        ],
        "finding_count": 4,
        "alert_count": 4,
        "external_urls_excluded": [],
        "external_excluded_count": 0,
    }


class MigrationTests(unittest.TestCase):
    def test_migration_adds_columns_idempotently_and_preserves_old_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old.sqlite3"
            import sqlite3

            legacy = sqlite3.connect(str(path))
            legacy.executescript(OLD_FINDINGS_DDL)
            legacy.execute(
                "INSERT INTO findings(fingerprint,run_id,title,url,parameter,severity,evidence,status,triage_json,first_seen,last_seen) "
                "VALUES('fp-old','run-old','Old finding','http://127.0.0.1:3000/','','low','old evidence','candidate','{}','t','t')"
            )
            legacy.commit()
            legacy.close()

            store = Store(path)
            try:
                columns = {row[1] for row in store.conn.execute("PRAGMA table_info(findings)")}
                self.assertTrue(NEW_COLUMNS <= columns)
                rows = store.list_findings()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["title"], "Old finding")
                self.assertEqual(rows[0]["vuln_type"], "")
                self.assertEqual(rows[0]["sources_json"], "[]")
            finally:
                store.close()
            # Second open must not fail or duplicate columns.
            store = Store(path)
            try:
                self.assertEqual(len(store.list_findings()), 1)
            finally:
                store.close()


class InsertCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "db.sqlite3")
        self.run_id = self.store.create_run("juice-shop-local", juice_scope().policy.digest(), "zap")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _candidate(self, **overrides):
        base = {
            "run_id": self.run_id,
            "title": "CSP Header Not Set",
            "url": "http://127.0.0.1:3000/",
            "parameter": "",
            "severity": "medium",
            "evidence": "CSP absent",
            "vuln_type": "csp-header-not-set",
            "scanner": "zap",
            "template_id": "10038",
            "confidence": 0.7,
            "status": "candidate",
        }
        base.update(overrides)
        return base

    def test_same_vuln_merges_sources_and_keeps_highest_severity(self):
        first = self.store.insert_candidate(self._candidate())
        second = self.store.insert_candidate(
            self._candidate(scanner="nuclei", template_id="csp-header", severity="high", confidence=0.9)
        )
        self.assertTrue(first.inserted)
        self.assertFalse(second.inserted)
        self.assertEqual(first.fingerprint, second.fingerprint)
        rows = self.store.list_findings(self.run_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "high")
        self.assertEqual(rows[0]["confidence"], 0.9)
        sources = json.loads(rows[0]["sources_json"])
        self.assertEqual(len(sources), 2)
        self.assertEqual({s["scanner"] for s in sources}, {"zap", "nuclei"})

    def test_different_vuln_type_same_url_parameter_stays_separate(self):
        self.store.insert_candidate(self._candidate())
        self.store.insert_candidate(self._candidate(vuln_type="x-frame-options-not-set", title="XFO Not Set"))
        self.assertEqual(len(self.store.list_findings(self.run_id)), 2)

    def test_query_values_do_not_split_fingerprint(self):
        self.store.insert_candidate(self._candidate(url="http://127.0.0.1:3000/search?q=apple"))
        self.store.insert_candidate(self._candidate(url="http://127.0.0.1:3000/search?q=banana"))
        self.assertEqual(len(self.store.list_findings(self.run_id)), 1)

    def test_cvss_roundtrip_and_sources_cap(self):
        self.store.insert_candidate(self._candidate(cvss=7.5))
        for index in range(25):
            self.store.insert_candidate(self._candidate(scanner="nuclei", template_id="t{}".format(index)))
        rows = self.store.list_findings(self.run_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cvss"], 7.5)
        self.assertEqual(len(json.loads(rows[0]["sources_json"])), 20)

    def test_canonical_url_fallbacks_and_port(self):
        self.assertEqual(Store._canonical_finding_url("not a url"), "not a url")
        self.assertEqual(Store._canonical_finding_url("http://[bad"), "http://[bad")
        self.assertEqual(Store._canonical_finding_url("HTTP://Example.COM:8080/p?q=1#f"), "http://example.com:8080/p")
        self.assertEqual(Store._canonical_finding_url("http://example.com"), "http://example.com/")

    def test_merge_keeps_existing_higher_severity_and_optional_run(self):
        self.store.insert_candidate(self._candidate(severity="high"))
        merged = self.store.insert_candidate(self._candidate(scanner="nuclei", template_id="x", severity="low"))
        self.assertFalse(merged.inserted)
        self.assertEqual(self.store.list_findings(self.run_id)[0]["severity"], "high")
        orphan = self.store.insert_candidate(self._candidate(run_id="", title="Orphan", vuln_type="orphan"))
        self.assertTrue(orphan.inserted)
        self.assertEqual(len(self.store.list_findings()), 2)

    def test_legacy_insert_finding_behavior_unchanged(self):
        self.store.insert_finding({"run_id": self.run_id, "title": "A", "url": "http://127.0.0.1:3000/", "parameter": ""})
        self.store.insert_finding({"run_id": self.run_id, "title": "B", "url": "http://127.0.0.1:3000/", "parameter": ""})
        self.assertEqual(len(self.store.list_findings(self.run_id)), 2)


class RedactionTests(unittest.TestCase):
    def test_masks_credentials_and_query_values(self):
        text = (
            "Cookie: session=abc123; token=xyz\n"
            "Authorization: Bearer supersecret\n"
            "GET http://127.0.0.1:3000/search?q=apple&token=leak HTTP/1.1\n"
        )
        redacted = redact_tool_output(text)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("supersecret", redacted)
        self.assertNotIn("leak", redacted)
        self.assertNotIn("apple", redacted)
        self.assertIn("[REDACTED]", redacted)
        self.assertIn("/search", redacted)

    def test_truncates_long_output(self):
        redacted = redact_tool_output("x" * 50000, limit=1000)
        self.assertLessEqual(len(redacted), 1100)
        self.assertIn("[TRUNCATED]", redacted)

    def test_decode_tool_bytes_replaces_invalid_and_caps(self):
        decoded = decode_tool_bytes(b"\xff\xfeok\n")
        self.assertIn("ok", decoded)
        self.assertIn("\ufffd", decoded)
        capped = decode_tool_bytes(b"a" * 2000000, cap=1024)
        self.assertLessEqual(len(capped), 1100)

    def test_hostless_and_invalid_urls_are_fully_masked(self):
        redacted = redact_tool_output("see http:///path and http://[bad end")
        self.assertNotIn("http:///path", redacted)
        self.assertNotIn("http://[bad", redacted)
        self.assertEqual(redacted.count("[REDACTED_URL]"), 2)

    def test_portless_url_keeps_host_and_masks_query(self):
        self.assertIn("http://example.com/p?a=[REDACTED]", redact_tool_output("http://example.com/p?a=1"))

    def test_decode_accepts_text_input(self):
        self.assertEqual(decode_tool_bytes("abc"), "abc")


class AdapterOutputTests(unittest.TestCase):
    def test_utf8_output_decoded_without_locale_errors(self):
        scope = juice_scope()
        registry = ToolRegistry(commands={"fake": sys.executable})
        code = "import sys; sys.stdout.buffer.write(b'\\xff\\xfeok\\n')"
        result = SafeToolAdapter("fake", registry).run(["-c", code], scope, target_urls=["http://127.0.0.1:3000/"])
        self.assertEqual(result.status, "completed")
        self.assertIn("ok", result.stdout)
        self.assertIn("\ufffd", result.stdout)


class ZapIngestTests(unittest.TestCase):
    def test_ingest_creates_candidates_evidence_and_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            try:
                scope = juice_scope()
                run_id = store.create_run("juice-shop-local", scope.policy.digest(), "juice-shop-zap")
                result = ingest_zap_candidates(store, root, run_id, scope, zap_parsed_fixture())
                self.assertEqual(result["skipped_out_of_scope"], 1)
                self.assertEqual(result["finding_count"], 2)
                rows = store.list_findings(run_id)
                self.assertEqual(len(rows), 2)
                self.assertTrue(all(row["status"] == "candidate" for row in rows))
                self.assertTrue(all(row["scanner"] == "zap" for row in rows))
                for row in rows:
                    evidence_path = root / "evidence" / run_id / (row["fingerprint"] + ".json")
                    self.assertTrue(evidence_path.is_file())
                report = ButianReportGenerator(root, store).generate(run_id, scope.policy.digest(), rows)
                text = report.read_text(encoding="utf-8")
                self.assertIn("Content Security Policy", text)
                self.assertIn("X-Frame-Options", text)
                self.assertNotIn("third-party.example", text)
            finally:
                store.close()


class ZapIngestRobustnessTests(unittest.TestCase):
    def test_ingest_ignores_non_mapping_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            try:
                scope = juice_scope()
                run_id = store.create_run("juice-shop-local", scope.policy.digest(), "juice-shop-zap")
                parsed = zap_parsed_fixture()
                parsed["findings"] = ["junk", None] + parsed["findings"][:1]
                result = ingest_zap_candidates(store, root, run_id, scope, parsed)
                self.assertEqual(result["inserted"], 1)
                self.assertEqual(result["finding_count"], 1)
            finally:
                store.close()


class CliZapIngestTests(unittest.TestCase):
    def test_zap_cli_persists_findings_and_report(self):
        report = {
            "@version": "2.17.0",
            "site": [
                {
                    "@name": "http://127.0.0.1:3000",
                    "alerts": [
                        {
                            "pluginid": "10038",
                            "name": "Content Security Policy (CSP) Header Not Set",
                            "riskcode": "2",
                            "confidence": "3",
                            "instances": [{"uri": "http://127.0.0.1:3000/", "method": "GET"}],
                        }
                    ],
                }
            ],
        }

        def fake_zap(project_root, target_url, output_path, timeout=300):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report), encoding="utf-8")
            return {"status": "completed", "returncode": 0, "report_path": str(output_path)}

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out_dir = root / "validation"
            db_path = root / "state.sqlite3"
            import io
            import contextlib

            output = io.StringIO()
            with patch.object(cli, "PROJECT_ROOT", root), patch.object(cli, "DB_PATH", db_path), patch.object(
                cli, "probe_local_target", return_value={"status": "reachable", "network_contact": True}
            ), patch.object(cli, "run_zap_quick_scan", side_effect=fake_zap), contextlib.redirect_stdout(output):
                code = cli.main(
                    [
                        "juice-shop-zap",
                        "--confirm-local",
                        "--scope",
                        str(Path(__file__).parents[1] / "config" / "targets" / "juice-shop-local" / "scope_confirmed.yaml"),
                        "--out-dir",
                        str(out_dir),
                    ]
                )
            value = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(value["finding_count"], 1)
            self.assertTrue(Path(value["report_path"]).is_file())
            self.assertTrue(value["run_id"])
            store = Store(db_path)
            try:
                rows = store.list_findings(value["run_id"])
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["scanner"], "zap")
                self.assertEqual(rows[0]["status"], "candidate")
            finally:
                store.close()
            artifact = json.loads((out_dir / "zap_findings.json").read_text(encoding="utf-8"))
            self.assertEqual(artifact["status_zh"], "存在待人工复核的可能项")


if __name__ == "__main__":
    unittest.main()