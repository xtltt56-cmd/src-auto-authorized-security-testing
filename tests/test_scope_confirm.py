import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from src_auto import cli
from src_auto.scope import ScopeGuard, ScopePolicy


PROJECT_ROOT = Path(__file__).parents[1]
VALIDATION = PROJECT_ROOT / "validation"


def candidate(**overrides):
    document = {
        "target_id": "juice-shop-local",
        "vendor": "operator-started-local-docker",
        "authorization_source": "local Docker instance started by operator",
        "root_domains": [],
        "allowed_hosts": ["127.0.0.1", "localhost"],
        "excluded_hosts": [],
        "allowed_ports": [3000],
        "test_window": "operator-invoked local validation only",
        "confirmed": False,
        "allow_network_contact": False,
    }
    document.update(overrides)
    return document


class ConfirmScopeCliTests(unittest.TestCase):
    def _run(self, argv):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = cli.main(argv)
        return code, json.loads(stream.getvalue())

    def _write_candidate(self, root, document):
        path = Path(root) / "scope_candidate.yaml"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def _confirm(self, candidate_path, output_dir, extra=None):
        argv = [
            "confirm-scope",
            "--candidate", str(candidate_path),
            "--output-dir", str(output_dir),
            "--operator", "tester",
            "--authorization-note", "local lab authorization",
            "--confirm",
            "--json",
        ]
        if extra is not None:
            argv = extra
        return self._run(argv)

    def test_confirm_generates_confirmed_scope_without_network(self):
        with tempfile.TemporaryDirectory(dir=str(VALIDATION)) as temp:
            root = Path(temp)
            candidate_path = self._write_candidate(root, candidate())
            output_dir = root / "confirmed"
            code, payload = self._confirm(candidate_path, output_dir)
            scope_path = output_dir / "scope_confirmed.yaml"
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "confirmed")
            self.assertFalse(payload["network_contact"])
            self.assertTrue(scope_path.exists())
            document = json.loads(scope_path.read_text(encoding="utf-8"))
            self.assertTrue(document["confirmed"])
            self.assertTrue(document["allow_network_contact"])
            policy = ScopePolicy.from_file(scope_path)
            self.assertEqual(policy.digest(), payload["scope_hash"])
            # The confirmed scope now authorizes the loopback target; confirm is not execution.
            self.assertTrue(ScopeGuard(policy).decide("http://127.0.0.1:3000/").allowed)
            self.assertFalse(ScopeGuard(policy).decide("http://127.0.0.1:8081/").allowed)

    def test_confirm_requires_explicit_flag(self):
        with tempfile.TemporaryDirectory(dir=str(VALIDATION)) as temp:
            root = Path(temp)
            candidate_path = self._write_candidate(root, candidate())
            code, payload = self._run([
                "confirm-scope", "--candidate", str(candidate_path), "--output-dir", str(root / "out"),
                "--operator", "tester", "--authorization-note", "note", "--json",
            ])
            self.assertNotEqual(code, 0)
            self.assertEqual(payload["reason"], "explicit_confirmation_required")
            self.assertFalse((root / "out" / "scope_confirmed.yaml").exists())

    def test_confirm_requires_operator_and_authorization_note(self):
        with tempfile.TemporaryDirectory(dir=str(VALIDATION)) as temp:
            root = Path(temp)
            candidate_path = self._write_candidate(root, candidate())
            code, payload = self._run([
                "confirm-scope", "--candidate", str(candidate_path), "--output-dir", str(root / "out"),
                "--operator", "", "--authorization-note", "", "--confirm", "--json",
            ])
            self.assertNotEqual(code, 0)
            self.assertEqual(payload["reason"], "operator_and_authorization_note_required")

    def test_confirm_rejects_empty_hosts(self):
        with tempfile.TemporaryDirectory(dir=str(VALIDATION)) as temp:
            root = Path(temp)
            candidate_path = self._write_candidate(root, candidate(allowed_hosts=[], root_domains=[]))
            code, payload = self._confirm(candidate_path, root / "out")
            self.assertNotEqual(code, 0)
            self.assertEqual(payload["reason"], "empty_scope_hosts")

    def test_confirm_rejects_empty_ports(self):
        with tempfile.TemporaryDirectory(dir=str(VALIDATION)) as temp:
            root = Path(temp)
            candidate_path = self._write_candidate(root, candidate(allowed_ports=[]))
            code, payload = self._confirm(candidate_path, root / "out")
            self.assertNotEqual(code, 0)
            self.assertEqual(payload["reason"], "empty_scope_ports")

    def test_confirm_rejects_already_confirmed_candidate(self):
        with tempfile.TemporaryDirectory(dir=str(VALIDATION)) as temp:
            root = Path(temp)
            candidate_path = self._write_candidate(root, candidate(confirmed=True, allow_network_contact=True))
            code, payload = self._confirm(candidate_path, root / "out")
            self.assertNotEqual(code, 0)
            self.assertEqual(payload["reason"], "candidate_already_confirmed")

    def test_confirm_rejects_malformed_candidate(self):
        with tempfile.TemporaryDirectory(dir=str(VALIDATION)) as temp:
            root = Path(temp)
            candidate_path = self._write_candidate(root, candidate(allowed_ports=[0]))
            code, payload = self._confirm(candidate_path, root / "out")
            self.assertNotEqual(code, 0)
            self.assertFalse((root / "out" / "scope_confirmed.yaml").exists())

    def test_confirm_does_not_overwrite_existing_scope(self):
        with tempfile.TemporaryDirectory(dir=str(VALIDATION)) as temp:
            root = Path(temp)
            candidate_path = self._write_candidate(root, candidate())
            output_dir = root / "out"
            output_dir.mkdir()
            existing = output_dir / "scope_confirmed.yaml"
            existing.write_text(json.dumps(candidate(confirmed=True)), encoding="utf-8")
            before = existing.read_text(encoding="utf-8")
            code, payload = self._confirm(candidate_path, output_dir)
            self.assertNotEqual(code, 0)
            self.assertEqual(payload["reason"], "confirmed_scope_already_exists")
            self.assertEqual(existing.read_text(encoding="utf-8"), before)

    def test_parser_exposes_confirm_scope_command(self):
        parser = cli.build_parser()
        args = parser.parse_args([
            "confirm-scope", "--candidate", "c", "--output-dir", "d", "--confirm", "--json",
        ])
        self.assertEqual(args.command, "confirm-scope")


if __name__ == "__main__":
    unittest.main()
