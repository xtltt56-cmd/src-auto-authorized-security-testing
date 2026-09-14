import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src_auto.juice_shop import (
    LocalTargetError,
    baseline_document,
    probe_local_target,
    safe_scan_urls,
    local_dependency_status,
    parse_zap_report,
    run_zap_quick_scan,
    summarize_discovery_tools,
    validation_metrics_document,
)
from src_auto.runtime_policy import RuntimePolicy


class _FakeResponse:
    status = 200
    reason = "OK"

    def __init__(self, body=b"<html><title>Juice Shop</title></html>", final_url="http://127.0.0.1:3000/"):
        self._body = body
        self._final_url = final_url
        self.headers = {"Content-Type": "text/html; charset=utf-8", "Server": "test"}

    def geturl(self):
        return self._final_url

    def read(self, limit=-1):
        if limit is not None and limit >= 0:
            return self._body[:limit]
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class JuiceShopRunnerTests(unittest.TestCase):
    def setUp(self):
        self.policy = RuntimePolicy.from_mapping(
            {
                "AI_PROVIDER": "local",
                "LOCAL_LLM_ONLY": True,
                "ALLOW_REMOTE_LLM": False,
                "allowed_hosts": ["127.0.0.1", "localhost"],
                "allowed_ports": [3000],
                "max_concurrency": 5,
            }
        )

    def test_probe_rejects_non_allowlisted_url_before_network(self):
        calls = []

        def fake_open(*args, **kwargs):
            calls.append((args, kwargs))
            return _FakeResponse()

        with self.assertRaises(LocalTargetError) as context:
            probe_local_target(self.policy, "https://example.com/", urlopen_fn=fake_open)
        self.assertEqual(context.exception.reason, "host_not_allowlisted")
        self.assertEqual(calls, [])

    def test_probe_rejects_malformed_request_without_network(self):
        calls = []

        def fake_open(*args, **kwargs):
            calls.append((args, kwargs))
            return _FakeResponse()

        with self.assertRaises(LocalTargetError) as context:
            probe_local_target(self.policy, "http://127.0.0.1:3000/\nX-Bad: value", urlopen_fn=fake_open)
        self.assertEqual(context.exception.reason, "invalid_url")
        self.assertEqual(calls, [])

    def test_probe_returns_minimal_metadata_and_no_response_body(self):
        response = _FakeResponse()
        result = probe_local_target(
            self.policy,
            "http://127.0.0.1:3000/",
            urlopen_fn=lambda *args, **kwargs: response,
        )
        self.assertEqual(result["status"], "reachable")
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["title"], "Juice Shop")
        self.assertNotIn("body", result)
        self.assertFalse(result["redirected"])

    def test_redirect_target_is_checked_after_local_contact(self):
        response = _FakeResponse(final_url="https://example.com/")
        with self.assertRaises(LocalTargetError) as context:
            probe_local_target(
                self.policy,
                "http://127.0.0.1:3000/",
                urlopen_fn=lambda *args, **kwargs: response,
            )
        self.assertEqual(context.exception.reason, "redirect_out_of_scope")

    def test_batch_preflights_all_urls_and_respects_policy_concurrency(self):
        calls = []

        def fake_open(request, timeout=0):
            calls.append(request.full_url)
            return _FakeResponse(final_url=request.full_url)

        results = safe_scan_urls(
            self.policy,
            ["http://127.0.0.1:3000/", "http://localhost:3000/api/Users"],
            urlopen_fn=fake_open,
            concurrency=99,
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(sorted(calls), ["http://127.0.0.1:3000/", "http://localhost:3000/api/Users"])

        with self.assertRaises(LocalTargetError):
            safe_scan_urls(
                self.policy,
                ["http://127.0.0.1:3000/", "http://example.com/"],
                urlopen_fn=fake_open,
                concurrency=1,
            )
        self.assertEqual(len(calls), 2)

    def test_baseline_document_is_explicit_when_dependency_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            path = baseline_document(
                Path(temp) / "baseline.json",
                status="BLOCKED_DEPENDENCY",
                reason="docker_unavailable",
                target_url="http://127.0.0.1:3000/",
                probe={"status": "unreachable", "network_contact": False},
                tools=[],
                findings=[],
                metrics=None,
            )
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["status"], "BLOCKED_DEPENDENCY")
            self.assertEqual(document["reason"], "docker_unavailable")
            self.assertIsNone(document["metrics"])
            self.assertEqual(document["network_contact"], False)

    def test_baseline_document_preserves_scan_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            path = baseline_document(
                Path(temp) / "baseline.json",
                status="COMPLETED_DISCOVERY_ONLY",
                reason="vulnerability_scanners_not_run",
                target_url="http://127.0.0.1:3000/",
                probe={"status": "reachable", "network_contact": True},
                tools=[],
                findings=[],
                metrics=None,
                scan_metadata={"scan_id": "test-scan", "http_request_count": 1},
            )
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["scan_metadata"]["scan_id"], "test-scan")
            self.assertEqual(document["scan_metadata"]["http_request_count"], 1)
            self.assertEqual(document["status_zh"], "已完成发现，尚未执行漏洞扫描")
            self.assertEqual(document["reason_zh"], "本次只执行发现，未运行漏洞扫描器")

    def test_metrics_placeholder_never_turns_an_unexecuted_scan_into_zero_score(self):
        document = validation_metrics_document(
            "NOT_RUN",
            "juice_shop_unreachable",
            "http://127.0.0.1:3000/",
            116,
            67,
            "not executed",
        )
        self.assertIsNone(document["precision"])
        self.assertEqual(document["ground_truth_count"], 116)
        self.assertEqual(document["remote_ai_calls"], 0)

    def test_metrics_document_preserves_discovery_metadata_without_scoring(self):
        document = validation_metrics_document(
            "NOT_RUN",
            "vulnerability_scanners_not_run",
            "http://127.0.0.1:3000/",
            116,
            67,
            "discovery only",
            scan_metadata={"scan_id": "test-scan", "discovered_url_count": 1},
        )
        self.assertEqual(document["scan_metadata"]["scan_id"], "test-scan")
        self.assertEqual(document["scan_metadata"]["discovered_url_count"], 1)
        self.assertIsNone(document["precision"])
        self.assertEqual(document["status_zh"], "未运行")
        self.assertEqual(document["reason_zh"], "本次只执行发现，未运行漏洞扫描器")

    def test_local_dependency_status_finds_explicit_docker_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "docker.exe"
            candidate.write_bytes(b"test")
            with patch("src_auto.juice_shop.shutil.which", return_value=None):
                result = local_dependency_status(extra_paths=[candidate])
        self.assertTrue(result["docker_available_on_path"])
        self.assertEqual(result["docker_command"], str(candidate))
        self.assertEqual(result["docker_source"], "explicit_candidate")

    def test_discovery_summary_filters_non_allowlisted_urls(self):
        tools = [
            {
                "tool": "katana",
                "result": {
                    "stdout": "http://127.0.0.1:3000/api/Users\nhttps://example.com/\n",
                    "stderr": "",
                },
            }
        ]
        summary = summarize_discovery_tools(self.policy, tools)
        self.assertEqual(summary["discovered_urls"], ["http://127.0.0.1:3000/api/Users"])
        self.assertEqual(summary["external_urls_excluded"], ["https://example.com/"])
        self.assertEqual(summary["discovered_url_count"], 1)

    def test_zap_report_parser_returns_unverified_local_findings_only(self):
        report = {
            "site": [
                {
                    "@name": "http://127.0.0.1:3000",
                    "alerts": [
                        {
                            "pluginid": "10038",
                            "name": "Content Security Policy (CSP) Header Not Set",
                            "riskcode": "2",
                            "confidence": "3",
                            "instances": [
                                {"uri": "http://127.0.0.1:3000/", "method": "GET", "param": "", "evidence": ""},
                                {"uri": "https://example.com/", "method": "GET", "param": "", "evidence": ""},
                            ],
                        }
                    ],
                }
            ]
        }
        summary = parse_zap_report(report, self.policy)
        self.assertEqual(summary["finding_count"], 1)
        self.assertEqual(summary["findings"][0]["status"], "POSSIBLE")
        self.assertEqual(summary["findings"][0]["endpoint"], "http://127.0.0.1:3000/")
        self.assertEqual(summary["external_urls_excluded"], ["https://example.com/"])

    def test_zap_quick_scan_uses_fixed_local_only_command(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            jar = root / "vendor" / "zap" / "ZAP_2.17.0" / "zap-2.17.0.jar"
            jar.parent.mkdir(parents=True)
            jar.write_bytes(b"jar")
            output = root / "zap.json"
            fake = type("Completed", (), {"returncode": 0, "stdout": "done", "stderr": ""})()
            with patch("src_auto.juice_shop.subprocess.run", return_value=fake) as run:
                result = run_zap_quick_scan(root, "http://127.0.0.1:3000/", output)
            command = run.call_args.args[0]
        self.assertEqual(result["status"], "completed")
        self.assertIn("-notel", command)
        self.assertIn("-quickurl", command)
        self.assertIn("http://127.0.0.1:3000/", command)
        self.assertIn("-quickout", command)
        self.assertIn("-dir", command)
        self.assertTrue(str(output.parent.resolve()) in command[command.index("-dir") + 1])


if __name__ == "__main__":
    unittest.main()
