"""L3 increment 1: controlled finding submission queue state machine.

Written before production behavior (project contract). Stdlib + temp fixtures
only; no real target, network, or Butian submission is performed. ``submitted``
records a human decision only and must carry an operator.
"""
import contextlib
import io
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from src_auto import cli
from src_auto.store import Store


def _finding(run_id):
    return {
        "run_id": run_id,
        "title": "Reflected XSS",
        "url": "http://localhost:8765/search",
        "parameter": "q",
        "vuln_type": "xss",
        "severity": "medium",
        "confidence": 0.7,
        "evidence": "payload reflected",
        "scanner": "zap",
        "template_id": "",
        "matched_at": "http://localhost:8765/search",
    }


@contextmanager
def _candidate():
    with tempfile.TemporaryDirectory() as temp:
        store = Store(Path(temp) / "db.sqlite3")
        try:
            run_id = store.create_run("local", "scope-hash", "real")
            fp = store.insert_candidate(_finding(run_id)).fingerprint
            yield store, fp
        finally:
            store.close()


def _status(store):
    return store.list_findings()[0]["status"]


class FindingQueueTests(unittest.TestCase):
    def test_forward_queue_transitions(self):
        with _candidate() as (store, fp):
            for target in ("triaged", "confirmed", "submission_ready"):
                store.transition_finding_status(fp, target, operator="analyst")
                self.assertEqual(_status(store), target)

    def test_submitted_requires_operator_and_is_terminal(self):
        with _candidate() as (store, fp):
            store.transition_finding_status(fp, "triaged")
            store.transition_finding_status(fp, "confirmed")
            store.transition_finding_status(fp, "submission_ready")
            with self.assertRaises(ValueError):
                store.transition_finding_status(fp, "submitted")
            self.assertEqual(_status(store), "submission_ready")
            store.transition_finding_status(fp, "submitted", operator="xu-tianle")
            self.assertEqual(_status(store), "submitted")
            with self.assertRaises(ValueError):
                store.transition_finding_status(fp, "triaged", operator="xu-tianle")
            self.assertEqual(_status(store), "submitted")

    def test_invalid_transition_is_fail_closed(self):
        with _candidate() as (store, fp):
            with self.assertRaises(ValueError):
                store.transition_finding_status(fp, "confirmed")
            self.assertEqual(_status(store), "candidate")

    def test_unknown_fingerprint_rejected(self):
        with _candidate() as (store, fp):
            with self.assertRaises(ValueError):
                store.transition_finding_status("does-not-exist", "triaged")

    def test_reject_and_reopen(self):
        with _candidate() as (store, fp):
            store.transition_finding_status(fp, "rejected", operator="analyst", note="out of scope")
            self.assertEqual(_status(store), "rejected")
            store.transition_finding_status(fp, "candidate", operator="analyst")
            self.assertEqual(_status(store), "candidate")

    def test_unknown_status_rejected(self):
        with _candidate() as (store, fp):
            with self.assertRaises(ValueError):
                store.transition_finding_status(fp, "bogus")
            self.assertEqual(_status(store), "candidate")


class FindingQueueCliTests(unittest.TestCase):
    def _seed(self, db_path):
        store = Store(db_path)
        try:
            run_id = store.create_run("local", "scope-hash", "real")
            return store.insert_candidate(_finding(run_id)).fingerprint
        finally:
            store.close()

    def _call(self, root, db_path, argv):
        output = io.StringIO()
        with patch.object(cli, "PROJECT_ROOT", root), patch.object(cli, "DB_PATH", db_path), contextlib.redirect_stdout(output):
            code = cli.main(argv)
        return code, json.loads(output.getvalue())

    def test_cli_transition_updates_real_store(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "state.sqlite3"
            fp = self._seed(db_path)
            code, value = self._call(root, db_path, ["finding-transition", "--fingerprint", fp, "--status", "triaged", "--operator", "analyst"])
            self.assertEqual(code, 0)
            self.assertEqual(value["new_status"], "triaged")
            store = Store(db_path)
            try:
                self.assertEqual(store.list_findings()[0]["status"], "triaged")
            finally:
                store.close()

    def test_cli_submitted_without_operator_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "state.sqlite3"
            fp = self._seed(db_path)
            for status in ("triaged", "confirmed", "submission_ready"):
                self._call(root, db_path, ["finding-transition", "--fingerprint", fp, "--status", status, "--operator", "analyst"])
            code, value = self._call(root, db_path, ["finding-transition", "--fingerprint", fp, "--status", "submitted"])
            self.assertEqual(code, 1)
            self.assertEqual(value["reason"], "operator_required")
            store = Store(db_path)
            try:
                self.assertEqual(store.list_findings()[0]["status"], "submission_ready")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()