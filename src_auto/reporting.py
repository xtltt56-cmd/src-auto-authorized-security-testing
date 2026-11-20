import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from .store import Store


def _under(root: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class EvidencePackager:
    def __init__(self, root: Path, store: Store):
        self.root = Path(root)
        self.store = store
        self.evidence_root = self.root / "evidence"
        self.evidence_root.mkdir(parents=True, exist_ok=True)

    def package(self, run_id: str, finding: Mapping[str, Any]) -> Path:
        fingerprint = str(finding["fingerprint"])
        path = self.evidence_root / run_id / (fingerprint + ".json")
        if not _under(self.root, path):
            raise ValueError("evidence path escaped project root")
        path.parent.mkdir(parents=True, exist_ok=True)
        minimal = {
            "run_id": run_id,
            "finding_fingerprint": fingerprint,
            "title": str(finding.get("title", "")),
            "url": str(finding.get("url", "")),
            "severity": str(finding.get("severity", "info")),
            "observation": str(finding.get("evidence", "")),
            "safety_note": "仅保留最小非破坏性观察；未保存凭据、用户数据或攻击载荷。",
        }
        path.write_text(json.dumps(minimal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.store.add_evidence(fingerprint, path, "minimal local-lab evidence")
        return path


class ButianReportGenerator:
    def __init__(self, root: Path, store: Store):
        self.root = Path(root)
        self.store = store
        self.report_root = self.root / "reports"
        self.report_root.mkdir(parents=True, exist_ok=True)

    _SEVERITIES = ("critical", "high", "medium", "low", "info")
    _QUEUE_STATES = ("candidate", "triaged", "confirmed", "submission_ready", "submitted", "rejected")

    @staticmethod
    def _sources(finding: Mapping[str, Any]) -> str:
        raw = finding.get("sources_json") or finding.get("sources")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = []
        items: List[str] = []
        if isinstance(raw, list):
            for source in raw:
                if isinstance(source, Mapping):
                    scanner = str(source.get("scanner", "")).strip()
                    template = str(source.get("template_id", "")).strip()
                    if scanner:
                        items.append(scanner + ("({})".format(template) if template else ""))
        if not items:
            scanner = str(finding.get("scanner", "")).strip()
            if scanner:
                items.append(scanner)
        return "; ".join(items) if items else "未记录"

    def generate(self, run_id: str, scope_hash: str, findings: Iterable[Mapping[str, Any]]) -> Path:
        findings = list(findings)
        path = self.report_root / (run_id + ".md")
        severity_counts: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        for finding in findings:
            severity = str(finding.get("severity", "info")).lower()
            status = str(finding.get("status", "candidate")).lower()
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            status_counts[status] = status_counts.get(status, 0) + 1
        lines: List[str] = [
            "# 补天 SRC 候选漏洞报告（人工复核草稿）",
            "",
            "> 本文件仅为候选报告草稿，不会自动提交补天；提交前必须由人确认授权范围、复现步骤和影响。",
            "",
            "## 工作流信息",
            "",
            "- Run ID: `{}`".format(run_id),
            "- Scope hash: `{}`".format(scope_hash),
            "- Evidence policy: 最小、非破坏性、无凭据/用户数据",
            "",
            "## 概览",
            "",
            "- 候选总数: {}".format(len(findings)),
            "- 严重性分布: " + ", ".join("{}={}".format(s, severity_counts.get(s, 0)) for s in self._SEVERITIES),
            "- 队列状态分布: " + ", ".join("{}={}".format(s, status_counts.get(s, 0)) for s in self._QUEUE_STATES),
            "",
            "## 候选 Finding",
            "",
        ]
        if not findings:
            lines.append("本次运行没有候选 Finding。")
        for index, finding in enumerate(findings, 1):
            triage = finding.get("triage") or {}
            if not isinstance(triage, Mapping):
                triage = {}
            cvss = finding.get("cvss")
            cwe = str(finding.get("cwe", "")).strip()
            parameter = str(finding.get("parameter", "")).strip()
            reproduction = str(finding.get("reproduction") or triage.get("reproduction") or "").strip()
            remediation = str(finding.get("remediation") or triage.get("remediation") or "").strip()
            lines.extend(
                [
                    "### {}. {}".format(index, finding.get("title", "未命名")),
                    "",
                    "- 漏洞类型: `{}`".format(finding.get("vuln_type") or "unspecified"),
                    "- 严重性: `{}`（CVSS: {}）".format(finding.get("severity", "info"), cvss if cvss is not None else "待评估"),
                    "- CWE: `{}`".format(cwe or "待映射"),
                    "- URL: `{}`".format(finding.get("url", "")),
                    "- 参数: `{}`".format(parameter or "无"),
                    "- 置信度: {}".format(finding.get("confidence", 0)),
                    "- 指纹: `{}`".format(finding.get("fingerprint", "")),
                    "- 来源: {}".format(self._sources(finding)),
                    "- 队列状态: `{}`".format(finding.get("status", "candidate")),
                    "- 观察: {}".format(finding.get("evidence", "")),
                    "- 复现步骤: {}".format(reproduction or "待人工补充最小复现步骤"),
                    "- 修复建议: {}".format(remediation or "待人工评估修复建议"),
                    "",
                    "人工复核要点：确认目标仍在授权范围内；只使用平台允许的最小复现；不要进行写入、删除、越权或拒绝服务测试。",
                    "",
                ]
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.store.save_report(run_id, path)
        return path
