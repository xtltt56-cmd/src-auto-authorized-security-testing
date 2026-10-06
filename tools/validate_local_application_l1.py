"""Reproducible local-only L1 regression; generated evidence stays in the project."""

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETED = ("tests.test_scope", "tests.test_runtime_policy", "tests.test_local_application_scope",
            "tests.test_local_application", "tests.test_local_application_pipeline", "tests.test_disk_measurement")


def main():
    parser = argparse.ArgumentParser(description="本机 Web 审查 L1 本地回归（不启用云端 AI）")
    parser.add_argument("--full", action="store_true", help="执行整个 Python unittest 套件")
    parser.add_argument("--phase", choices=('l1', 'l2'), default='l1', help="验收阶段；L2 额外包含工作流、Agent 与控制接口回归")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    os.chdir(str(ROOT))
    phase = 'local-application-' + args.phase
    temp_root = ROOT / "validation" / phase / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(temp_root), TMP=str(temp_root), SRC_AUTO_REMOTE_AI_CONSENT="no")
    # Default-deny via the global gate, with no inherited per-provider override.
    # Fake-transport unit tests can then explicitly grant their own mock consent.
    for provider in ("DEEPSEEK", "ZHIPU", "OPENAI", "OPENROUTER"):
        os.environ.pop("SRC_AUTO_{}_CONSENT".format(provider), None)
    tempfile.tempdir = str(temp_root)
    started = datetime.now(timezone(timedelta(hours=8)))
    output = ROOT / "validation" / phase / started.strftime("%Y%m%d-%H%M%S-%f")
    output.mkdir(parents=True, exist_ok=False)
    captured, timer = io.StringIO(), time.monotonic()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        loader = unittest.defaultTestLoader
        selected = TARGETED + (('tests.test_local_application_workflow', 'tests.test_agent', 'tests.test_agent_service', 'tests.test_agent_provider', 'tests.test_dashboard_server') if args.phase == 'l2' else ())
        suite = loader.discover(str(ROOT / "tests")) if args.full else loader.loadTestsFromNames(selected)
        result = unittest.TextTestRunner(stream=captured, verbosity=1).run(suite)
    failed = {getattr(test, "test_case", test).id() for test, _ in result.failures + result.errors}
    summary = {
        "phase": phase, "started_at": started.isoformat(),
        "python_version": sys.version.split()[0], "mode": "full" if args.full else "targeted",
        "success": result.wasSuccessful(), "tests_run": result.testsRun,
        "passed": result.testsRun - len(failed) - len(result.skipped) - len(result.expectedFailures),
        "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures), "unexpected_successes": len(result.unexpectedSuccesses),
        "failed_test_ids": sorted(failed), "skipped_test_ids": [test.id() for test, _ in result.skipped],
        "elapsed_seconds": round(time.monotonic() - timer, 3),
        "cloud_consent_default": "disabled", "tested_targets": "synthetic loopback fixtures only",
        "not_verified_by_this_suite": ["real quant application scan", "cloud API integration", "Dashboard local app workflow",
                         "third-party scanner egress", "real trusted local HTTPS service", "IPv6 transport"],
    }
    report = output / "summary.json"
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(summary, report_path=str(report)), ensure_ascii=False, indent=2))
    if not result.wasSuccessful():
        # Do not persist arbitrary failing assertions or configuration excerpts.
        print("回归未通过，请按 failed_test_ids 定向重跑诊断。", file=sys.stderr)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
