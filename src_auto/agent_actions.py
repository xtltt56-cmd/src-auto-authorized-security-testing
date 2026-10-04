"""Program-owned, read-only recipes. The model never supplies URLs or headers."""
import hashlib
import json
import time
import re
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .agent_contracts import ACTIONS, CATALOG_VERSION
from .ai import sanitize_finding
from .config import load_mapping
from .local_discovery import discover_local_surface
from .runtime_policy import RuntimePolicy
from .store import Store


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


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

    def fetch(self, url, user="anonymous"):
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
                data = response.read(65537)
                if len(data) > 65536:
                    raise RuntimeError("response_too_large")
                return {"status_code": status, "body": data.decode("utf-8", errors="replace"),
                        "headers": {str(k).lower(): str(v) for k, v in response.headers.items()},
                        "url": url, "final_url": url, "content_type": response.headers.get("Content-Type", "")}
            finally:
                response.close()
        raise RuntimeError("scope_blocked")


class LocalActions:
    def __init__(self, root, manager, lab_id, limits, cancel, candidate=None):
        self.root, self.lab_id, self.candidate = root, lab_id, candidate
        spec = manager.spec(lab_id)
        policy_path = root / "config/validation/local_only.json"
        policy = RuntimePolicy.from_file(policy_path)
        self.entry = spec.health_url
        if not policy.decide_url(self.entry)[0]: raise RuntimeError("scope_blocked")
        self.client = GuardedHTTP(self.entry, limits, cancel, stop=lambda: (root / "STOP").exists())
        self.policy = RuntimePolicy.from_mapping(dict(policy.to_mapping(), allowed_hosts=["127.0.0.1"], allowed_ports=[spec.host_port]))
        self.references = ["entry"]
        self.permissions = None
        self.capabilities = sorted(ACTIONS - {"read_observation", "review_candidate", "inspect_api_schema", "compare_object_authorization"})
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
        if value.reference != "entry": raise RuntimeError("scope_blocked")
        if value.action == "inspect_headers":
            result = self.client.fetch(self.entry)
            if result["status_code"] >= 500: raise RuntimeError("target_unavailable")
            missing = [x for x in ("content-security-policy", "x-content-type-options", "x-frame-options") if not result["headers"].get(x)]
            return {"status": "ok", "summary": "响应头元数据检查；缺失项仅是加固建议，不自动计为漏洞", "httpStatus": result["status_code"], "missingHeaders": missing, "candidate": False}
        if value.action == "discover_surface":
            result = discover_local_surface(self.policy, self.entry, fetch_fn=self.client.fetch, max_scripts=2)
            if result.get("status") != "COMPLETED": raise RuntimeError("surface_discovery_failed")
            return {"status": "ok", "summary": "有限同源静态页面分析；未执行发现的API",
                    "endpoints": len(result.get("discovered_urls", [])), "api": len(result.get("api_urls", [])),
                    "excluded": len(result.get("external_urls_excluded", [])), "candidate": False}
        if value.action == "inspect_api_schema":
            result = self.client.fetch(self.client.origin + "/openapi.json")
            if result["status_code"] != 200: raise RuntimeError("schema_unavailable")
            document = json.loads(result["body"])
            return {"status": "ok", "summary": "仅读取规范；不解析远程引用、不自动访问规范中的URL",
                    "schemaVersion": str(document.get("openapi", document.get("swagger", "unknown")))[:20],
                    "pathCount": len(document.get("paths", {})), "candidate": False}
        raise RuntimeError("capability_unavailable")

    def persist_candidate(self, agent_id, value, observation):
        if self.lab_id != "business-api" or value.action != "compare_object_authorization":
            raise RuntimeError("capability_unavailable")
        store = Store(self.root / "data/src_auto.sqlite3")
        try:
            checkpoint = store.load_checkpoint(agent_id, "agent-standard-run")
            if checkpoint:
                run_id = checkpoint["run_id"]
            else:
                run_id = store.create_run("local-business-api", self.scope_hash, mode="agent-local")
                store.save_checkpoint(agent_id, "agent-standard-run", {"run_id": run_id})
            result = store.insert_finding({"run_id": run_id, "title": "合成对象授权异常（Agent 待复核候选）",
                    "url": self.client.origin + "/agent/cases/" + value.reference, "parameter": value.reference,
                    "severity": "high", "status": "candidate", "evidence": "所有者与同级合成账号得到等价对象；观察 {}。只保留状态与指纹，无正文。".format(observation["id"]),
                    "triage": {"confirmed": False, "submission_ready": False, "source": "controlled-agent", "agent_id": agent_id}})
            store.set_run_status(run_id, "candidate_review_required")
            return str(result.row_id)
        finally:
            store.close()

    def link_report(self, agent_id, path):
        relative = path.resolve().relative_to(self.root.resolve()).as_posix()
        store = Store(self.root / "data/src_auto.sqlite3")
        try:
            checkpoint = store.load_checkpoint(agent_id, "agent-standard-run")
            if checkpoint:
                store.save_report(checkpoint["run_id"], relative)
        finally: store.close()
