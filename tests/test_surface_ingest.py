"""L2: surface asset ingestion, nuclei candidates, partial tool ingest, plan bridge.

Written before production behavior (project contract). Stdlib + loopback/temp
fixtures only; no real target or Docker daemon is contacted.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src_auto.adapters import ToolRegistry
from src_auto.attack_surface import AttackSurfaceTarget, build_attack_surface_plan
from src_auto.finding_ingest import ingest_nuclei_candidates
from src_auto.live_plan import LivePlanError, validate_live_plan
from src_auto.models import ToolResult
from src_auto.pipeline import PipelineRunner
from src_auto.scope import ScopeGuard, ScopePolicy
from src_auto.store import Store
from src_auto.surface_ingest import (
    ingest_tool_output,
    parse_httpx_assets,
    parse_katana_assets,
    parse_nuclei_candidates,
)

HTTPX_LINE = json.dumps(
    {
        "url": "http://localhost:8765/",
        "host": "localhost",
        "port": "8765",
        "title": "Lab",
        "status_code": 200,
        "webserver": "nginx",
        "tech": ["nginx", "php"],
    }
)
KATANA_LINE = json.dumps({"request": {"endpoint": "http://localhost:8765/api", "method": "GET"}})
NUCLEI_LINE = json.dumps(
    {
        "template-id": "csp-header-not-set",
        "info": {"name": "CSP Header Not Set", "severity": "medium", "classification": {"cwe-id": ["CWE-693"]}},
        "matched-at": "http://localhost:8765/",
        "host": "localhost",
        "matcher-name": "header",
    }
)
OUT_LINE = json.dumps({"url": "https://third-party.example/", "host": "third-party.example", "port": "443"})


def scope():
    return ScopeGuard(
        ScopePolicy.from_mapping(
            {
                "target_id": "local",
                "allowed_hosts": ["localhost"],
                "allowed_ports": [8765],
                "confirmed": True,
                "allow_network_contact": True,
            }
        )
    )


class ParserTests(unittest.TestCase):
    def test_httpx_parses_bounded_assets_and_drops_junk(self):
        assets = parse_httpx_assets(HTTPX_LINE + "\nnot json\n\n")
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["host"], "localhost")
        self.assertEqual(assets[0]["port"], 8765)
        self.assertEqual(assets[0]["metadata"]["server"], "nginx")
        self.assertEqual(assets[0]["metadata"]["status_code"], 200)

    def test_katana_parses_endpoints(self):
        assets = parse_katana_assets(KATANA_LINE + "\n")
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["url"], "http://localhost:8765/api")
        self.assertEqual(assets[0]["kind"], "endpoint")

    def test_nuclei_parses_candidate_shape(self):
        items = parse_nuclei_candidates(NUCLEI_LINE + "\n")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["vuln_type"], "csp-header-not-set")
        self.assertEqual(items[0]["scanner"], "nuclei")
        self.assertEqual(items[0]["severity"], "medium")
        self.assertEqual(items[0]["url"], "http://localhost:8765/")


class SurfaceIngestTests(unittest.TestCase):
    def test_ingest_httpx_drops_out_of_scope_and_snapshots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            try:
                guard = scope()
                run_id = store.create_run("local", guard.policy.digest(), "real")
                result = ingest_tool_output(
                    store, root, run_id, guard, "httpx", ToolResult("httpx", "completed", 0, HTTPX_LINE + "\n" + OUT_LINE)
                )
                self.assertEqual(result["assets"], 1)
                self.assertEqual(result["skipped_out_of_scope"], 1)
                self.assertEqual(len(store.diff_assets(run_id, run_id)["unchanged"]), 1)
            finally:
                store.close()

    def test_ingest_nuclei_creates_candidate_and_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            try:
                guard = scope()
                run_id = store.create_run("local", guard.policy.digest(), "real")
                result = ingest_tool_output(
                    store, root, run_id, guard, "nuclei", ToolResult("nuclei", "completed", 0, NUCLEI_LINE)
                )
                self.assertEqual(result["inserted"], 1)
                rows = store.list_findings(run_id)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["scanner"], "nuclei")
                self.assertTrue((root / "evidence" / run_id / (rows[0]["fingerprint"] + ".json")).is_file())
            finally:
                store.close()

    def test_ingest_skips_failed_tool_and_unknown_parser(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            try:
                guard = scope()
                run_id = store.create_run("local", guard.policy.digest(), "real")
                failed = ingest_tool_output(store, root, run_id, guard, "httpx", ToolResult("httpx", "error", 1))
                self.assertFalse(failed["ingested"])
                unknown = ingest_tool_output(store, root, run_id, guard, "zap", ToolResult("zap", "completed", 0, "x"))
                self.assertFalse(unknown["ingested"])
            finally:
                store.close()

    def test_nuclei_and_zap_same_vuln_merge_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            try:
                guard = scope()
                run_id = store.create_run("local", guard.policy.digest(), "real")
                ingest_nuclei_candidates(store, root, run_id, guard, parse_nuclei_candidates(NUCLEI_LINE))
                zap_item = {
                    "title": "CSP Header Not Set",
                    "endpoint": "http://localhost:8765/",
                    "parameter": "",
                    "method": "GET",
                    "severity": "high",
                    "confidence": 0.9,
                    "evidence": "zap",
                    "scanner_alert_id": "10038",
                }
                from src_auto.finding_ingest import ingest_zap_candidates

                ingest_zap_candidates(store, root, run_id, guard, {"findings": [zap_item]})
                rows = store.list_findings(run_id)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["severity"], "high")
                self.assertEqual({s["scanner"] for s in json.loads(rows[0]["sources_json"])}, {"nuclei", "zap"})
            finally:
                store.close()


class RunExternalIngestTests(unittest.TestCase):
    def _runner(self, root, store, guard):
        return PipelineRunner(store, guard, root)

    def test_success_ingests_assets_and_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            try:
                guard = scope()
                run_id = store.create_run("local", guard.policy.digest(), "real")
                adapters = {
                    "httpx": _Fake("httpx", HTTPX_LINE),
                    "katana": _Fake("katana", KATANA_LINE),
                    "nuclei": _Fake("nuclei", NUCLEI_LINE),
                }
                result = self._runner(root, store, guard).run_external(
                    run_id, ["http://localhost:8765/"], adapters=adapters, execute=True,
                    sequence=["httpx", "katana", "nuclei"],
                )
                self.assertEqual(result["status"], "completed_tools")
                self.assertEqual(result["ingest"]["assets"], 2)
                self.assertEqual(result["ingest"]["inserted"], 1)
                self.assertEqual(len(store.list_findings(run_id)), 1)
            finally:
                store.close()

    def test_failure_keeps_completed_tool_results_as_partial(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            try:
                guard = scope()
                run_id = store.create_run("local", guard.policy.digest(), "real")
                adapters = {"httpx": _Fake("httpx", HTTPX_LINE), "nuclei": _Fake("nuclei", "", status="error")}
                result = self._runner(root, store, guard).run_external(
                    run_id, ["http://localhost:8765/"], adapters=adapters, execute=True,
                    sequence=["httpx", "nuclei"],
                )
                self.assertEqual(result["status"], "partial_tools")
                self.assertEqual(result["ingest"]["assets"], 1)
                self.assertEqual(len(result["stages"]), 2)
                self.assertEqual(store.get_run(run_id)["status"], "partial_tools")
            finally:
                store.close()


class _Fake:
    def __init__(self, name, stdout, status="completed"):
        self.name = name
        self.stdout = stdout
        self.status = status

    def run(self, args, scope_guard, target_urls=None):
        return ToolResult(self.name, self.status, 0 if self.status == "completed" else 1, self.stdout)


class PlanBridgeTests(unittest.TestCase):
    def test_surface_plan_mapping_feeds_live_plan_validator(self):
        from dataclasses import replace

        guard = scope()
        target = AttackSurfaceTarget.from_url("local", "http://localhost:8765/")
        plan = build_attack_surface_plan(target, guard, True, {"httpx", "katana"})
        mapping = plan.to_mapping()
        self.assertEqual(mapping["operator"], "")
        self.assertFalse(mapping["manual_execution_confirmed"])
        reviewed = replace(plan, operator="xtl", authorization_note="lab authorization", manual_execution_confirmed=True)
        canonical = validate_live_plan(reviewed.to_mapping())
        self.assertEqual(canonical["operator"], "xtl")
        self.assertTrue(canonical["manual_execution_confirmed"])
        self.assertIn("httpx", canonical["sequence"])

    def test_reconftw_is_no_longer_an_allowed_live_tool(self):
        with self.assertRaisesRegex(LivePlanError, "unsupported tool"):
            validate_live_plan(
                {
                    "name": "p",
                    "operator": "x",
                    "authorization_note": "n",
                    "manual_execution_confirmed": True,
                    "target_urls": ["http://localhost:8765/"],
                    "sequence": ["reconftw"],
                    "commands": {"reconftw": []},
                }
            )


class NucleiRunnerTests(unittest.TestCase):
    def test_missing_docker_binary_fails_closed_without_subprocess(self):
        from src_auto.nuclei_runner import NucleiDockerRunner

        with tempfile.TemporaryDirectory() as temp:
            runner = NucleiDockerRunner(Path(temp))
            with patch("src_auto.nuclei_runner.subprocess.run") as proc:
                result = runner.run(["-u", "http://localhost:8765/"], scope(), ["http://localhost:8765/"])
            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.detail, "docker_binary_missing")
            proc.assert_not_called()

    def test_fixed_container_argv_and_self_cleanup(self):
        from src_auto.nuclei_runner import NucleiDockerRunner

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "vendor" / "bin").mkdir(parents=True)
            docker = root / "vendor" / "bin" / "docker.exe"
            docker.write_bytes(b"fake-docker")
            import hashlib

            digest = hashlib.sha256(b"fake-docker").hexdigest()
            (root / "config" / "integrations").mkdir(parents=True)
            (root / "config" / "integrations" / "passive_scanners.json").write_text(
                json.dumps({"schema_version": 1, "image": "ghcr.io/zaproxy/zaproxy@sha256:" + "a" * 64,
                            "image_id": "sha256:" + "b" * 64, "docker_sha256": digest}),
                encoding="utf-8",
            )
            (root / "tools.lock.yaml").write_text(
                json.dumps({"tools": {"nuclei": {"image_digest": "sha256:" + "c" * 64}}}), encoding="utf-8"
            )
            runner = NucleiDockerRunner(root)
            calls = []

            def fake_run(argv, **kwargs):
                calls.append(list(argv))
                joined = " ".join(argv)
                if "version" in argv:
                    return _Completed(0, b"27.0.0")
                if "inspect" in argv and "image" in argv:
                    return _Completed(0, json.dumps([{"Id": "sha256:" + "c" * 64, "RepoDigests": ["projectdiscovery/nuclei@sha256:" + "c" * 64]}]).encode())
                if "create" in argv:
                    return _Completed(0, b"container-id")
                if "start" in argv:
                    return _Completed(0, NUCLEI_LINE.encode())
                if "inspect" in argv:
                    return _Completed(0, json.dumps([{"State": {"ExitCode": 0}, "Image": "sha256:" + "c" * 64, "HostConfig": {}}]).encode())
                return _Completed(0, b"")

            with patch("src_auto.nuclei_runner.subprocess.run", side_effect=fake_run):
                result = runner.run(["-u", "http://localhost:8765/", "-jsonl"], scope(), ["http://localhost:8765/"])
            self.assertEqual(result.status, "completed")
            self.assertIn("csp-header-not-set", result.stdout)
            create = next(c for c in calls if "create" in c)
            self.assertIn("--pull", create)
            self.assertIn("never", create)
            self.assertIn("--cap-drop", create)
            self.assertIn("ALL", create)
            self.assertIn("projectdiscovery/nuclei@sha256:" + "c" * 64, create)
            rm = next(c for c in calls if "rm" in c)
            self.assertIn("container-id", rm)


class _Completed:
    def __init__(self, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = b""


if __name__ == "__main__":
    unittest.main()