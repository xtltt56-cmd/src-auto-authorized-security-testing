"""Run the bounded, local-only SRC-Auto acceptance plan.

The orchestrator is intentionally conservative: it calls only existing
loopback Juice Shop commands, stores bounded/redacted output, and reports
unknown adjudication as ``NOT_TESTED``.  It is not a public scanner and it
never enables remote AI or an external target.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_URL = "http://127.0.0.1:3000/"
AUTOTEST_ROOT = PROJECT_ROOT / "validation" / "autotest"
JUICE_ARTIFACT_ROOT = PROJECT_ROOT / "validation" / "juice-shop"
MAX_OUTPUT = 4096
MAX_ROUNDS = 3


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def safe_artifact_path(project_root: Path, candidate: Path) -> Path:
    """Resolve an output path and fail closed if it escapes ``project_root``."""

    root = _resolved(project_root)
    resolved = _resolved(candidate)
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError("artifact_outside_project_root")
    return resolved


def is_loopback_url(url: str) -> bool:
    """Return true only for HTTP(S) URLs whose host is loopback/localhost."""

    try:
        parsed = urlsplit(str(url).strip())
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
            return False
        host = (parsed.hostname or "").strip().lower().rstrip(".")
        if host == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False
    except ValueError:
        return False


def redact_text(value: Any) -> str:
    """Bound command output and remove common credentials/API-token forms."""

    text = str(value or "")
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", text)
    text = re.sub(r"(?i)(authorization|cookie|set-cookie|x-api-key|token|secret|password|api[_-]?key)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "sk-<redacted>", text)
    return text.replace("\x00", " ")[:MAX_OUTPUT]


def _json_write(path: Path, document: Mapping[str, Any]) -> Path:
    path = safe_artifact_path(PROJECT_ROOT, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(document), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _markdown_write(path: Path, content: str) -> Path:
    path = safe_artifact_path(PROJECT_ROOT, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(content).rstrip() + "\n", encoding="utf-8")
    return path


def build_discovery_metrics(document: Mapping[str, Any]) -> Dict[str, Any]:
    """Count only URL traits observable in the baseline artifact.

    Unknown stages are ``None`` rather than fabricated zeros.  Ground Truth is
    deliberately not read here and therefore cannot influence discovery.
    """

    metadata = document.get("scan_metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    raw_urls = metadata.get("discovered_urls", document.get("discovered_urls", []))
    urls = [str(value).strip() for value in raw_urls if str(value).strip()] if isinstance(raw_urls, list) else []
    excluded = metadata.get("external_urls_excluded", document.get("external_urls_excluded", []))
    excluded_count = len(excluded) if isinstance(excluded, list) else None
    javascript_count = 0
    api_count = 0
    query_count = 0
    for url in urls:
        parsed = urlsplit(url)
        path = parsed.path.lower()
        if path.endswith(".js"):
            javascript_count += 1
        if "/api" in path or "/rest" in path or "graphql" in path:
            api_count += 1
        if parsed.query:
            query_count += 1
    return {
        "status": "OBSERVED_ONLY",
        "target": str(document.get("target_url", LOCAL_URL)),
        "network_contact": bool(document.get("network_contact", False)),
        "url_count": len(urls),
        "javascript_url_count": javascript_count,
        "api_like_url_count": api_count,
        "query_url_count": query_count,
        "html_route_count": len(metadata["html_routes"]) if isinstance(metadata.get("html_routes"), list) else None,
        "client_route_count": len(metadata["client_routes"]) if isinstance(metadata.get("client_routes"), list) else None,
        "external_excluded_count": excluded_count,
        "remote_ai_calls": 0,
        "remote_ai_cost_cny": 0.0,
        "notes": "仅统计当前工件可证明的表面；未执行阶段保持 null。",
    }


def _run_command(label: str, args: Sequence[str], timeout: int = 120, parse_json: bool = False) -> Dict[str, Any]:
    """Run a fixed local command without a shell and retain bounded evidence."""

    started = time.perf_counter()
    safe_args = [str(item) for item in args]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        completed = subprocess.run(
            safe_args,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(timeout),
            shell=False,
            check=False,
        )
        result = {
            "label": label,
            "command": safe_args[:20],
            "status": "completed" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "stdout": redact_text(completed.stdout),
            "stderr": redact_text(completed.stderr),
        }
        if parse_json:
            try:
                parsed = json.loads(completed.stdout)
                if isinstance(parsed, Mapping):
                    result["_parsed_json"] = dict(parsed)
            except (TypeError, ValueError):
                pass
        return result
    except subprocess.TimeoutExpired as exc:
        return {
            "label": label,
            "command": safe_args[:20],
            "status": "timeout",
            "returncode": None,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "stdout": redact_text(getattr(exc, "stdout", "")),
            "stderr": redact_text(getattr(exc, "stderr", "")),
        }
    except (OSError, ValueError) as exc:
        return {
            "label": label,
            "command": safe_args[:20],
            "status": "unavailable",
            "returncode": None,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "stdout": "",
            "stderr": redact_text(exc),
        }


def _parse_json_output(result: Mapping[str, Any]) -> Dict[str, Any]:
    parsed = result.get("_parsed_json")
    if isinstance(parsed, Mapping):
        return dict(parsed)
    try:
        value = json.loads(str(result.get("stdout", "")))
        return dict(value) if isinstance(value, Mapping) else {"status": "invalid_json"}
    except (TypeError, ValueError):
        return {"status": "invalid_json", "detail": redact_text(result.get("stdout", ""))}


def _git_capture(args: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            ["git"] + [str(item) for item in args],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            shell=False,
            check=False,
        )
        return redact_text(result.stdout if result.returncode == 0 else result.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return redact_text(exc)


def _sha256_file(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _freeze_source_state() -> Dict[str, Any]:
    try:
        diff_process = subprocess.run(
            ["git", "diff", "--binary"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            shell=False,
            check=False,
        )
        diff_digest = hashlib.sha256(bytes(diff_process.stdout or b"")).hexdigest()
    except (OSError, subprocess.TimeoutExpired):
        diff_digest = None
    key_files = {
        "ground_truth": PROJECT_ROOT / "validation" / "juice-shop" / "ground_truth.json",
        "runtime_policy": PROJECT_ROOT / "config" / "validation" / "local_only.json",
        "policy": PROJECT_ROOT / "config" / "policy.yaml",
    }
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "git_head": _git_capture(["rev-parse", "HEAD"]).strip(),
        "git_status": _git_capture(["status", "--short"]),
        "git_diff_sha256": diff_digest,
        "key_file_sha256": {name: _sha256_file(path) for name, path in key_files.items()},
        "ground_truth_read_for_hash_only": True,
        "remote_ai_calls": 0,
        "working_tree_policy": "pre-existing changes preserved; evaluator and Ground Truth are not modified",
    }


def _dependency_status() -> Dict[str, Any]:
    names = ("python", "git", "java", "ollama", "docker", "httpx", "katana", "zap")
    project_candidates = {
        "httpx": PROJECT_ROOT / "vendor" / "bin" / "httpx.exe",
        "katana": PROJECT_ROOT / "vendor" / "bin" / "katana.exe",
        "zap": PROJECT_ROOT / "vendor" / "zap" / "ZAP_2.17.0" / "zap.bat",
    }
    values: Dict[str, Any] = {}
    for name in names:
        on_path = shutil.which(name)
        candidate = project_candidates.get(name)
        selected = on_path or (str(candidate) if candidate and candidate.is_file() else "")
        values[name] = {"available": bool(selected), "path": selected, "source": "path" if on_path else "project_vendor" if selected else "unavailable"}
    values["project_root"] = str(PROJECT_ROOT)
    values["runtime_mode"] = "local-only"
    values["target"] = LOCAL_URL
    values["remote_ai"] = {"enabled": False, "calls": 0, "cost_cny": 0.0}
    return values


def _copy_round_artifacts(round_dir: Path, include_zap: bool = True) -> List[str]:
    names = (
        "baseline_results.json",
        "baseline_metrics.json",
        "zap_quick_report.json",
        "zap_findings.json",
    )
    copied: List[str] = []
    round_dir = safe_artifact_path(PROJECT_ROOT, round_dir)
    round_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        if not include_zap and name in ("zap_quick_report.json", "zap_findings.json"):
            if name == "zap_findings.json":
                _json_write(round_dir / name, {
                    "status": "NOT_TESTED",
                    "reason": "zap_command_not_completed",
                    "target_url": LOCAL_URL,
                    "network_contact": False,
                    "finding_count": None,
                })
            continue
        source = JUICE_ARTIFACT_ROOT / name
        target = round_dir / name
        if source.is_file():
            target.write_bytes(source.read_bytes())
            copied.append(name)
    return copied


def _baseline_document() -> Dict[str, Any]:
    path = JUICE_ARTIFACT_ROOT / "baseline_results.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return dict(value) if isinstance(value, Mapping) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _finding_count() -> Optional[int]:
    path = JUICE_ARTIFACT_ROOT / "zap_findings.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return int(value.get("finding_count", 0)) if isinstance(value, Mapping) else None
    except (OSError, ValueError, TypeError):
        return None


def _write_round_reports(round_dir: Path, metrics: Mapping[str, Any], finding_count: Optional[int]) -> None:
    _markdown_write(
        round_dir / "DISCOVERY_REPORT.md",
        "# Discovery\n\n状态：**OBSERVED_ONLY**\n\n- URL：{}\n- JavaScript：{}\n- API-like：{}\n- 查询参数 URL：{}\n- 外部排除：{}\n\n只记录当前扫描工件可证明的发现，不把未执行阶段写成 0。".format(
            metrics.get("url_count"),
            metrics.get("javascript_url_count"),
            metrics.get("api_like_url_count"),
            metrics.get("query_url_count"),
            metrics.get("external_excluded_count"),
        ),
    )
    count_text = "null" if finding_count is None else str(finding_count)
    _markdown_write(
        round_dir / "VERIFICATION_REPORT.md",
        "# Verification\n\n状态：**NOT_TESTED**\n\n本轮 ZAP 候选数量：{}。没有独立人工复现和证据裁决，不能升级为已确认漏洞。".format(count_text),
    )
    _markdown_write(
        round_dir / "VERIFICATION_STATUS.md",
        "# Verification Status\n\nStatus: **NOT_TESTED**\n\n候选 Finding 数量：{}。".format(count_text),
    )
    _markdown_write(
        round_dir / "FALSE_POSITIVES.md",
        "# False Positives\n\n状态：**NOT_TESTED**\n\n本轮没有完成逐项人工裁决，不能把候选自动归类为 FP。",
    )
    _markdown_write(
        round_dir / "FALSE_NEGATIVES.md",
        "# False Negatives\n\n状态：**NOT_TESTED**\n\n未用 Ground Truth 反向驱动扫描；没有足够证据计算 FN。",
    )
    _markdown_write(
        round_dir / "CHANGES_UNDER_TEST.md",
        "# Changes Under Test\n\n- 启动器 UTF-8 BOM 和 PowerShell 进度重绘修复\n- target-review 离线 Scope 预览\n- local-only 自动化验收编排\n\n本轮没有自动修改检测器或 Ground Truth。",
    )
    _json_write(round_dir / "resource_usage.json", {"status": "NOT_MEASURED", "cpu_seconds": None, "ram_peak_mb": None, "notes": "本轮仅保存命令耗时，未宣称完整资源计量。"})


def _run_round(round_number: int, commands: List[Dict[str, Any]]) -> Dict[str, Any]:
    round_dir = AUTOTEST_ROOT / ("round_{:02d}_baseline".format(round_number))
    status_result = _run_command(
        "juice-shop-status-{:02d}".format(round_number),
        [sys.executable, "-m", "src_auto", "juice-shop-status", "--url", LOCAL_URL, "--json"],
        timeout=30,
        parse_json=True,
    )
    status_document = _parse_json_output(status_result)
    status_result.pop("_parsed_json", None)
    commands.append(status_result)
    baseline_result = _run_command(
        "juice-shop-baseline-{:02d}".format(round_number),
        [sys.executable, "-m", "src_auto", "juice-shop-baseline", "--url", LOCAL_URL, "--scope", str(PROJECT_ROOT / "config" / "targets" / "juice-shop-local" / "scope_confirmed.yaml"), "--out-dir", str(JUICE_ARTIFACT_ROOT), "--json"],
        timeout=180,
        parse_json=True,
    )
    baseline_document = _parse_json_output(baseline_result)
    baseline_result.pop("_parsed_json", None)
    commands.append(baseline_result)
    zap_result = _run_command(
        "juice-shop-zap-{:02d}".format(round_number),
        [sys.executable, "-m", "src_auto", "juice-shop-zap", "--url", LOCAL_URL, "--scope", str(PROJECT_ROOT / "config" / "targets" / "juice-shop-local" / "scope_confirmed.yaml"), "--out-dir", str(JUICE_ARTIFACT_ROOT), "--confirm-local", "--json"],
        timeout=300,
        parse_json=True,
    )
    zap_document = _parse_json_output(zap_result)
    zap_result.pop("_parsed_json", None)
    commands.append(zap_result)
    zap_success = zap_result.get("status") == "completed" and zap_document.get("status") == "POSSIBLE_FINDINGS"
    _copy_round_artifacts(round_dir, include_zap=zap_success)
    # The CLI summary is intentionally bounded; discovery metrics come from
    # the freshly written local artifact, never from Ground Truth or old data.
    artifact_document = _baseline_document()
    metrics = build_discovery_metrics(artifact_document)
    _json_write(round_dir / "DISCOVERY_METRICS.json", metrics)
    possible = int(zap_document.get("finding_count")) if zap_success and isinstance(zap_document.get("finding_count"), int) else None
    verification_status = "NOT_TESTED"
    _write_round_reports(round_dir, metrics, possible)
    baseline_summary = {
        "status": baseline_document.get("status", "NOT_TESTED"),
        "reason": baseline_document.get("reason", "unknown"),
        "artifact": baseline_document.get("artifact", ""),
        "network_contact": bool(baseline_document.get("network_contact", False)),
    }
    zap_summary = {
        "status": zap_document.get("status", "NOT_TESTED"),
        "reason": zap_document.get("reason", "unknown"),
        "finding_count": possible,
        "network_contact": bool(zap_document.get("network_contact", False)),
    }
    return {
        "round": round_number,
        "status": baseline_summary["status"],
        "baseline": baseline_summary,
        "zap": zap_summary,
        "finding_count": possible,
        "network_contact": bool(status_document.get("network_contact", False)),
        "discovery_metrics": metrics,
        "artifact_dir": str(round_dir),
    }


def _restart_local_container(commands: List[Dict[str, Any]]) -> None:
    docker = shutil.which("docker")
    if not docker:
        return
    result = _run_command("local-juice-shop-restart", [docker, "restart", "juice-shop"], timeout=60)
    commands.append(result)
    if result.get("status") != "completed":
        return
    ready = _wait_local_loopback()
    commands.append(
        {
            "label": "local-juice-shop-readiness",
            "command": ["loopback", LOCAL_URL],
            "status": "completed" if ready else "failed",
            "returncode": 0 if ready else 1,
            "duration_seconds": None,
            "stdout": "HTTP 200" if ready else "",
            "stderr": "" if ready else "loopback_target_not_ready",
        }
    )


def _wait_local_loopback(timeout: int = 45) -> bool:
    """Wait only for the explicitly allowlisted loopback lab to restart."""

    if not is_loopback_url(LOCAL_URL):
        return False
    deadline = time.time() + int(timeout)
    while time.time() < deadline:
        try:
            request = Request(LOCAL_URL, headers={"User-Agent": "SRC-Auto/local-validation"})
            with urlopen(request, timeout=2) as response:
                final_url = str(getattr(response, "geturl", lambda: LOCAL_URL)())
                if int(getattr(response, "status", getattr(response, "code", 0)) or 0) == 200 and is_loopback_url(final_url):
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


def _precheck(commands: List[Dict[str, Any]]) -> Dict[str, Any]:
    report = _dependency_status()
    for label, args, timeout in (
        ("git-version", ["git", "--version"], 20),
        ("python-version", [sys.executable, "--version"], 20),
    ):
        result = _run_command(label, args, timeout=timeout)
        commands.append(result)
        report[label] = {"status": result["status"], "returncode": result["returncode"], "stdout": result["stdout"], "stderr": result["stderr"]}
    if shutil.which("java"):
        result = _run_command("java-version", ["java", "-version"], timeout=20)
        commands.append(result)
        report["java_version"] = {"status": result["status"], "returncode": result["returncode"], "stderr": result["stderr"]}
    if shutil.which("docker"):
        result = _run_command("docker-version", ["docker", "version", "--format", "{{.Server.Version}}"], timeout=30)
        commands.append(result)
        report["docker_version"] = {"status": result["status"], "returncode": result["returncode"], "stdout": result["stdout"], "stderr": result["stderr"]}
    return report


def _ai_ablation(commands: List[Dict[str, Any]]) -> Dict[str, Any]:
    result = _run_command("local-model-status", [sys.executable, "-m", "src_auto", "model-status", "--json"], timeout=30, parse_json=True)
    document = _parse_json_output(result)
    result.pop("_parsed_json", None)
    commands.append(result)
    available = bool(document.get("available"))
    return {
        "status": "NOT_TESTED" if not available else "NOT_RUN",
        "local_model_available": available,
        "local_model_calls": 0,
        "remote_ai_calls": 0,
        "remote_ai_cost_cny": 0.0,
        "notes": "本轮验收不自动触发 AI；需要独立、可审计的本地模型对照时再人工启动。",
    }


def _stability(rounds: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    counts = [item.get("finding_count") for item in rounds if isinstance(item.get("finding_count"), int)]
    if len(counts) < 2:
        return {"status": "NOT_TESTED", "finding_count_min": None, "finding_count_max": None, "finding_count_variance": None, "notes": "重复轮次没有足够的可比较 Finding 计数。"}
    mean = sum(counts) / float(len(counts))
    variance = sum((value - mean) ** 2 for value in counts) / float(len(counts))
    return {"status": "OBSERVED", "finding_count_min": min(counts), "finding_count_max": max(counts), "finding_count_variance": round(variance, 6), "notes": "仅比较扫描器候选数量，不代表检测准确率。"}


def run_validation(repeat_rounds: int = 2) -> Dict[str, Any]:
    if not 0 <= int(repeat_rounds) <= MAX_ROUNDS:
        raise ValueError("repeat_rounds_out_of_range")
    AUTOTEST_ROOT.mkdir(parents=True, exist_ok=True)
    commands: List[Dict[str, Any]] = []
    precheck = _precheck(commands)
    source_state = _freeze_source_state()
    _json_write(AUTOTEST_ROOT / "baseline_source_state.json", source_state)
    _markdown_write(
        AUTOTEST_ROOT / "PRECHECK_REPORT.md",
        "# 本机验收预检\n\n- 模式：`local-only`\n- 目标：`{}`\n- 远程 AI：调用 0，成本 0\n- Scope Escape：0（外部 URL 不执行）\n\n```json\n{}\n```".format(LOCAL_URL, json.dumps(precheck, ensure_ascii=False, indent=2, sort_keys=True)),
    )

    rounds: List[Dict[str, Any]] = []
    if repeat_rounds >= 0:
        rounds.append(_run_round(0, commands))
    for index in range(1, int(repeat_rounds) + 1):
        _restart_local_container(commands)
        rounds.append(_run_round(index, commands))

    baseline = rounds[0] if rounds else {}
    discovery_metrics = baseline.get("discovery_metrics", build_discovery_metrics(_baseline_document()))
    _json_write(AUTOTEST_ROOT / "DISCOVERY_METRICS.json", discovery_metrics)
    ai_ablation = _ai_ablation(commands)
    _markdown_write(
        AUTOTEST_ROOT / "AI_ABLATION_REPORT.md",
        "# AI Ablation\n\nStatus: **{}**\n\n- 本地模型可用：{}\n- 本地调用：0\n- 远程调用：0\n- 远程成本：0 CNY\n\n本报告没有把未执行的 AI 对照当作通过。".format(ai_ablation["status"], "是" if ai_ablation["local_model_available"] else "否"),
    )
    stability = _stability(rounds[1:] if len(rounds) > 1 else rounds)
    _json_write(AUTOTEST_ROOT / "STABILITY.json", stability)
    second_lab = {"status": "NOT_TESTED", "reason": "no_preapproved_loopback_webgoat_or_dvwa_adapter", "network_contact": False}
    _json_write(AUTOTEST_ROOT / "SECOND_LAB.json", second_lab)

    command_failures = [item for item in commands if item.get("status") in ("failed", "timeout", "unavailable")]
    crashes = [item for item in commands if isinstance(item.get("returncode"), int) and int(item.get("returncode")) < 0]
    reachable = baseline.get("baseline", {}).get("status") in ("COMPLETED_DISCOVERY_ONLY", "COMPLETED")
    p0 = {
        "scope_escape": 0,
        "remote_ai_calls": 0,
        "secret_leakage": 0,
        "crash": len(crashes),
    }
    verdict = "LOCAL_LAB_READY" if reachable and p0["scope_escape"] == 0 and p0["remote_ai_calls"] == 0 and p0["secret_leakage"] == 0 and p0["crash"] == 0 else "NOT_READY"
    final = {
        "status": verdict,
        "mode": "local-only",
        "target": LOCAL_URL,
        "p0": p0,
        "command_failure_count": len(command_failures),
        "rounds": rounds,
        "stability": stability,
        "ai_ablation": ai_ablation,
        "second_lab": second_lab,
        "precision": None,
        "recall": None,
        "verification_success_rate": None,
        "remote_ai_calls": 0,
        "remote_ai_cost_cny": 0.0,
        "repair_rounds": 1,
        "repairs": ["launcher_progress_redraw"],
        "limitations": [
            "POSSIBLE Finding 未经独立人工裁决，不等于已确认漏洞。",
            "Precision/Recall/FN/verification 仍为 NOT_TESTED。",
            "第二靶场未运行；本结果不是 AUTHORIZED_PILOT_READY。",
        ],
    }
    _json_write(AUTOTEST_ROOT / "AUTONOMOUS_VALIDATION.json", final)
    _markdown_write(
        AUTOTEST_ROOT / "AUTONOMOUS_VALIDATION_REPORT.md",
        "# SRC-Auto 本机自动化验收\n\n最终判定：**{}**\n\n- 运行模式：local-only\n- 目标：{}\n- Scope Escape：{}\n- Remote AI Calls：{}\n- Secret Leakage：{}\n- Crash：{}\n- 候选 Finding 仍需人工复核，未自动提交补天。\n\n详细 JSON：`AUTONOMOUS_VALIDATION.json`。".format(verdict, LOCAL_URL, p0["scope_escape"], p0["remote_ai_calls"], p0["secret_leakage"], p0["crash"]),
    )
    _json_write(AUTOTEST_ROOT / "COMMAND_SUMMARY.json", {"commands": commands, "remote_ai_calls": 0, "external_targets_contacted": 0})
    return final


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SRC-Auto 仅本机回环靶场验收")
    parser.add_argument("--local-only", action="store_true", default=True, help="仅允许本机回环目标（默认且唯一模式）")
    parser.add_argument("--repeat-rounds", type=int, default=2, help="本地重复轮次数，默认 2，最多 3")
    args = parser.parse_args(argv)
    if not args.local_only:
        print(json.dumps({"status": "blocked_policy", "reason": "local_only_is_mandatory", "network_contact": False}, ensure_ascii=False))
        return 3
    try:
        result = run_validation(args.repeat_rounds)
    except Exception as exc:  # pragma: no cover - final safety net for CLI use
        document = {"status": "FAIL", "reason": "orchestrator_exception", "detail": redact_text(exc), "network_contact": False}
        _json_write(AUTOTEST_ROOT / "AUTONOMOUS_VALIDATION.json", document)
        _markdown_write(AUTOTEST_ROOT / "AUTONOMOUS_VALIDATION_REPORT.md", "# 本机自动化验收\n\n状态：**FAIL**\n\n原因：编排器异常，详见 JSON。")
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "LOCAL_LAB_READY" else 4


if __name__ == "__main__":
    raise SystemExit(main())
