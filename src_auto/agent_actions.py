"""Program-owned, read-only recipes. The model never supplies URLs or headers."""
import hashlib
import json
import time
import re
import secrets
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .agent_contracts import ACTIONS, CATALOG_VERSION
from .ai import sanitize_finding
from .config import load_mapping
from .local_discovery import MAX_DISCOVERY_BODY, discover_local_surface
from .runtime_policy import RuntimePolicy
from .store import Store
from .local_regression import run_agent_regression, run_agent_dvwa_controls


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


MAX_GUARDED_RESPONSE_BYTES = 512 * 1024


class GuardedHTTP:
    def __init__(self, entry, limits, cancel, opener=None, stop=None):
        parsed = urlsplit(entry)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password:
            raise RuntimeError("scope_blocked")
        self.entry = entry
        self.origin = "http://127.0.0.1:{}".format(parsed.port or 80)
        self.limits, self.cancel, self.stop = limits, cancel, stop or (lambda: False)
        self.requests = 0
        self.deadline = time.monotonic() + limits.max_seconds
        # Explicitly ignore global proxies and all automatic redirects.
        self.opener = opener or build_opener(ProxyHandler({}), NoRedirect())

    def fetch(self, url, user="anonymous", max_response_bytes=65536, truncate_response=False):
        if (type(max_response_bytes) is not int or not 1 <= max_response_bytes <= MAX_GUARDED_RESPONSE_BYTES
                or type(truncate_response) is not bool):
            raise ValueError("invalid_response_limit")
        for _ in range(4):
            if self.cancel.is_set() or self.stop():
                raise RuntimeError("cancelled")
            parsed = urlsplit(url)
            if (parsed.scheme, parsed.hostname, parsed.port or 80) != ("http", "127.0.0.1", urlsplit(self.origin).port) or parsed.username or parsed.password or parsed.fragment or any(ord(x) < 32 for x in url):
                raise RuntimeError("scope_blocked")
            if self.requests >= self.limits.max_requests or time.monotonic() >= self.deadline:
                raise RuntimeError("request_limit")
            if user not in {"buyer-a", "buyer-b", "anonymous"}:
                raise RuntimeError("scope_blocked")
            headers = {"User-Agent": "SRC-Auto/controlled-agent", "Accept-Encoding": "identity"}
            if user != "anonymous": headers["X-Test-User"] = user
            self.requests += 1
            try:
                response = self.opener.open(Request(url, headers=headers, method="GET"), timeout=max(0.1, min(10, self.deadline - time.monotonic())))
            except HTTPError as exc:
                response = exc
            try:
                status = response.getcode()
                if status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location: raise RuntimeError("scope_blocked")
                    url = urljoin(url, location)
                    continue
                data = response.read(max_response_bytes + 1)
                truncated = len(data) > max_response_bytes
                if truncated and not truncate_response:
                    raise RuntimeError("response_too_large")
                if truncated:
                    data = data[:max_response_bytes]
                return {"status_code": status, "body": data.decode("utf-8", errors="replace"),
                        "headers": {str(k).lower(): str(v) for k, v in response.headers.items()},
                        "url": url, "final_url": url, "content_type": response.headers.get("Content-Type", ""),
                        "truncated": truncated}
            finally:
                response.close()
        raise RuntimeError("scope_blocked")


class LocalActions:
    def __init__(self, root, manager, lab_id, limits, cancel, candidate=None, mode="candidate-review"):
        self.root, self.lab_id, self.candidate = root, lab_id, candidate
        self.manager, self.mode = manager, mode
        spec = manager.spec(lab_id)
        policy_path = root / "config/validation/local_only.json"
        policy = RuntimePolicy.from_file(policy_path)
        self.entry = spec.health_url
        if not policy.decide_url(self.entry)[0]: raise RuntimeError("scope_blocked")
        self.client = GuardedHTTP(self.entry, limits, cancel, stop=lambda: (root / "STOP").exists())
        self.policy = RuntimePolicy.from_mapping(dict(policy.to_mapping(), allowed_hosts=["127.0.0.1"], allowed_ports=[spec.host_port]))
        self.references = ["entry"]
        self.permissions = None
        self.capabilities = sorted(ACTIONS - {"read_observation", "review_candidate", "inspect_api_schema",
                                              "compare_object_authorization", "run_local_regression",
                                              "validate_controlled_inputs", "compare_object_authorization_matrix"})
        if lab_id in {"vampi", "business-api"}: self.capabilities.append("inspect_api_schema")
        if lab_id == "business-api":
            self.permissions = load_mapping(root / "config/agent/permissions.json")
            private = self.permissions.get("private_objects", [])
            public = self.permissions.get("public_objects", [])
            if not isinstance(private, list) or not isinstance(public, list) or not private or not public:
                raise ValueError("invalid_permission_manifest")
            if any(not isinstance(x, str) or not re.fullmatch(r"case-(0[1-9]|1[0-9]|20)", x) for x in private + public) or len(set(private + public)) != len(private + public):
                raise ValueError("invalid_permission_manifest")
            if (self.permissions.get("owner"), self.permissions.get("peer"), self.permissions.get("anonymous")) != ("buyer-a", "buyer-b", "anonymous"):
                raise ValueError("invalid_permission_manifest")
            self.capabilities.append("compare_object_authorization")
            self.references += private + public
        if mode == "local-assessment":
            self.capabilities.append("run_local_regression")
            if lab_id == "dvwa":
                self.capabilities.append("validate_controlled_inputs")
            if lab_id == "business-api":
                self.capabilities.append("compare_object_authorization_matrix")
        if candidate:
            self.references.append("candidate")
            self.capabilities.append("review_candidate")
        self.scope_hash = hashlib.sha256(json.dumps({"lab": lab_id, "entry": self.entry, "policy": policy.to_mapping()}, sort_keys=True).encode()).hexdigest()
        # No secrets included in checkpoint digests or model inputs.
        config = load_mapping(root / "config/models.yaml")
        policy_config = load_mapping(root / "config/policy.yaml")
        self.config_hash = hashlib.sha256(json.dumps({"models": config, "catalog": CATALOG_VERSION,
                                                    "limits": policy_config, "permissions": self.permissions,
                                                    "candidate": sanitize_finding(candidate) if candidate else None}, sort_keys=True).encode()).hexdigest()

    @property
    def requests(self): return self.client.requests

    @requests.setter
    def requests(self, value): self.client.requests = value

    def execute(self, value):
        if value.action not in self.capabilities: raise RuntimeError("capability_unavailable")
        if value.action == "review_candidate":
            if value.reference != "candidate" or not self.candidate: raise RuntimeError("scope_blocked")
            return {"status": "ok", "summary": "已加载本任务关联的脱敏候选；仍需核对复现与影响", "finding": sanitize_finding(self.candidate), "candidate": False}
        if value.action == "compare_object_authorization":
            if self.lab_id != "business-api" or value.reference not in self.permissions["private_objects"] + self.permissions["public_objects"]: raise RuntimeError("scope_blocked")
            access = "public" if value.reference in self.permissions["public_objects"] else "private"
            snapshots = [self.client.fetch(self.client.origin + "/agent/cases/" + value.reference, user=x) for x in ("buyer-a", "buyer-b", "anonymous")]
            bodies = [json.loads(x["body"]) for x in snapshots]
            statuses = [x["status_code"] for x in snapshots]
            ownership = bodies[0].get("owner") == "buyer-a" and bodies[0].get("id") == value.reference
            equivalent = bodies[0] == bodies[1]
            candidate = access == "private" and ownership and statuses[0] == 200 and statuses[1] == 200 and equivalent
            return {"status": "ok", "summary": "合成账号对象比较完成；不保留对象正文", "access": access,
                    "statuses": statuses, "ownerVerified": ownership, "equivalentPeer": equivalent,
                    "fingerprints": [hashlib.sha256(x["body"].encode()).hexdigest() for x in snapshots],
                    "candidate": candidate, "confirmed": False}
        if value.action == "run_local_regression":
            if value.reference != "entry" or self.mode != "local-assessment": raise RuntimeError("scope_blocked")
            if self.manager.status(self.lab_id).get("status") != "READY": raise RuntimeError("target_unavailable")
            return run_agent_regression(self.root, self.lab_id, self.manager, before_request=self._reserve_request)
        if value.action == "validate_controlled_inputs":
            if value.reference != "entry" or self.mode != "local-assessment" or self.lab_id != "dvwa": raise RuntimeError("scope_blocked")
            if self.manager.status(self.lab_id).get("status") != "READY": raise RuntimeError("target_unavailable")
            return run_agent_dvwa_controls(self.root, self.manager, before_request=self._reserve_request)
        if value.action == "compare_object_authorization_matrix":
            if value.reference != "entry" or self.mode != "local-assessment" or self.lab_id != "business-api": raise RuntimeError("scope_blocked")
            if self.manager.status(self.lab_id).get("status") != "READY": raise RuntimeError("target_unavailable")
            return self._compare_authorization_matrix()
        if value.reference != "entry": raise RuntimeError("scope_blocked")
        if value.action == "inspect_headers":
            result = self.client.fetch(self.entry)
            if result["status_code"] >= 500: raise RuntimeError("target_unavailable")
            missing = [x for x in ("content-security-policy", "x-content-type-options", "x-frame-options") if not result["headers"].get(x)]
            return {"status": "ok", "summary": "响应头元数据检查；缺失项仅是加固建议，不自动计为漏洞", "httpStatus": result["status_code"], "missingHeaders": missing, "candidate": False}
        if value.action == "discover_surface":
            truncated = []
            def fetch_discovery(url):
                result = self.client.fetch(url, max_response_bytes=MAX_DISCOVERY_BODY, truncate_response=True)
                if result.get("truncated"):
                    truncated.append(url)
                return result
            result = discover_local_surface(self.policy, self.entry, fetch_fn=fetch_discovery, max_scripts=2)
            if result.get("status") != "COMPLETED": raise RuntimeError("surface_discovery_failed")
            return {"status": "ok", "summary": "有限同源静态页面分析；未执行发现的API",
                    "endpoints": len(result.get("discovered_urls", [])), "api": len(result.get("api_urls", [])),
                    "excluded": len(result.get("external_urls_excluded", [])), "candidate": False,
                    "truncated": bool(truncated), "degraded": bool(result.get("degraded", False) or truncated)}
        if value.action == "inspect_api_schema":
            result = self.client.fetch(self.client.origin + "/openapi.json")
            if result["status_code"] != 200: raise RuntimeError("schema_unavailable")
            document = json.loads(result["body"])
            return {"status": "ok", "summary": "仅读取规范；不解析远程引用、不自动访问规范中的URL",
                    "schemaVersion": str(document.get("openapi", document.get("swagger", "unknown")))[:20],
                    "pathCount": len(document.get("paths", {})), "candidate": False}
        raise RuntimeError("capability_unavailable")

    def _reserve_request(self):
        if self.client.cancel.is_set() or self.client.stop(): raise RuntimeError("cancelled")
        if self.requests >= self.client.limits.max_requests or time.monotonic() >= self.client.deadline:
            raise RuntimeError("request_limit")
        # Shared counter means normal Agent GETs, authentication fixtures and
        # matrix checks all consume the same per-task request budget.
        self.client.requests += 1

    def _compare_authorization_matrix(self):
        manifest = self.permissions
        private = list(manifest["private_objects"])
        public = list(manifest["public_objects"])
        expected = {"case-{:02d}".format(index) for index in range(1, 21)}
        if set(private + public) != expected or set(private) & set(public):
            raise RuntimeError("invalid_permission_manifest")
        records = []
        candidates = []
        for reference in private + public:
            path = self.client.origin + "/agent/cases/" + reference
            snapshots = [self.client.fetch(path, user=user) for user in ("buyer-a", "buyer-b", "anonymous")]
            statuses = [item["status_code"] for item in snapshots]
            bodies = [json.loads(item["body"]) for item in snapshots]
            ownership = bodies[0].get("owner") == "buyer-a" and bodies[0].get("id") == reference
            equivalent = bodies[0] == bodies[1]
            is_private = reference in private
            candidate = (is_private and ownership and statuses == [200, 200, 403] and equivalent)
            if candidate:
                candidates.append(reference)
            records.append({
                "reference": reference,
                "access": "private" if is_private else "public",
                "statuses": statuses,
                "owner_verified": ownership,
                "owner_peer_equivalent": equivalent,
                "candidate": candidate,
                "fingerprints": [hashlib.sha256(item["body"].encode("utf-8")).hexdigest() for item in snapshots],
            })
        artifact = self.root / "validation" / "agent-local-tests" / (secrets.token_hex(8) + "-business-api-matrix.json")
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps({
            "status": "COMPLETED", "mode": "local-only", "lab_id": "business-api",
            "target": self.client.origin, "objects_tested": len(records), "request_count": 3 * len(records),
            "candidate_count": len(candidates), "candidate_objects": candidates,
            "records": records, "confirmed": False, "submission_ready": False,
            "note": "仅合成对象、固定 GET 与测试身份；候选必须人工独立复核。",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {
            "status": "ok",
            "profileStatus": "COMPLETED",
            "summary": "20 个合成对象权限对照完成：{} 个私有对象候选；固定与公开负例均计入复核。".format(len(candidates)),
            "objectsTested": len(records),
            "requests": 3 * len(records),
            "candidate": bool(candidates),
            "candidateCount": len(candidates),
            "candidateKinds": ["horizontal-authorization"] if candidates else [],
            "candidateObjects": candidates,
            "confirmed": False,
            "submissionReady": False,
            "manualReviewRequired": True,
            "artifact": artifact.relative_to(self.root).as_posix(),
        }

    def persist_candidate(self, agent_id, value, observation):
        if value.action == "validate_controlled_inputs" and self.lab_id == "dvwa":
            title = "DVWA 受控 SQLi/XSS 指标（Agent 待复核候选）"
            url = self.client.origin + "/vulnerabilities/"
            parameter = ",".join(observation.get("candidateKinds", []))[:200]
            severity = "medium"
            evidence = "仅回环靶场固定布尔对照/惰性 HTML 标记；未验证脚本执行或真实业务影响。观察 {}。报告：{}".format(
                observation["id"], observation.get("artifact", ""))
        elif value.action == "compare_object_authorization_matrix" and self.lab_id == "business-api":
            title = "多个合成对象存在横向授权候选（Agent 待复核）"
            url = self.client.origin + "/agent/cases/"
            parameter = ",".join(observation.get("candidateObjects", []))[:200]
            severity = "high"
            evidence = "固定 20 项权限矩阵中 {} 个私有对象被同级合成账号读取；仅留状态/指纹。观察 {}。报告：{}".format(
                int(observation.get("candidateCount", 0)), observation["id"], observation.get("artifact", ""))
        elif self.lab_id == "business-api" and value.action == "compare_object_authorization":
            title = "合成对象授权异常（Agent 待复核候选）"
            url = self.client.origin + "/agent/cases/" + value.reference
            parameter = value.reference
            severity = "high"
            evidence = "所有者与同级合成账号得到等价对象；观察 {}。只保留状态与指纹，无正文。".format(observation["id"])
        else:
            raise RuntimeError("capability_unavailable")
        store = Store(self.root / "data/src_auto.sqlite3")
        try:
            checkpoint = store.load_checkpoint(agent_id, "agent-standard-run")
            if checkpoint:
                run_id = checkpoint["run_id"]
            else:
                run_id = store.create_run("local-business-api", self.scope_hash, mode="agent-local")
                store.save_checkpoint(agent_id, "agent-standard-run", {"run_id": run_id})
            result = store.insert_finding({"run_id": run_id, "title": title,
                    "url": url, "parameter": parameter,
                    "severity": severity, "status": "candidate", "evidence": evidence,
                    "triage": {"confirmed": False, "submission_ready": False, "source": "controlled-agent", "agent_id": agent_id}})
            store.set_run_status(run_id, "candidate_review_required")
            return str(result.row_id)
        finally:
            store.close()

    def persist_candidates(self, agent_id, value, observation):
        if value.action != "validate_controlled_inputs":
            return [self.persist_candidate(agent_id, value, observation)]
        count = int(observation.get("candidateCount", 0))
        if count <= 0:
            return []
        return [self.persist_candidate(agent_id, value, observation)]

    def link_report(self, agent_id, path):
        relative = path.resolve().relative_to(self.root.resolve()).as_posix()
        store = Store(self.root / "data/src_auto.sqlite3")
        try:
            checkpoint = store.load_checkpoint(agent_id, "agent-standard-run")
            if checkpoint:
                store.save_report(checkpoint["run_id"], relative)
        finally: store.close()
