"""Fail-closed nuclei Docker runner (L2).

Native nuclei on this host is blocked by endpoint security (WinError 225); the
project deliberately does NOT bypass it. This runner uses the pinned image
digest from tools.lock.yaml and the hash-pinned Docker CLI already used by the
passive ZAP lane. Every precondition fails closed: no binary, hash mismatch,
daemon down, image drift -> blocked, no container is ever started.
"""
import hashlib
import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, NamedTuple, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

from .models import ToolResult
from .redaction import decode_tool_bytes
from .scope import ScopeGuard

_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_TEMPLATE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_IMAGE_REPO = "projectdiscovery/nuclei"
_VALUE_FLAGS = {"-u", "-tags", "-pt", "-id", "-rl", "-c", "-bs", "-timeout", "-retries"}
_BOOL_FLAGS = {"-no-interactsh", "-disable-unsigned-templates", "-jsonl"}
_SAFE_TAGS = {"ssl", "misconfig", "exposure"}
_SAFE_PROTOCOLS = {"http", "ssl", "dns"}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_HOST_GATEWAY = "host.docker.internal"
_REQUEST_BUDGET = 1000
_UNKNOWN_REQUEST_COST = 3
_MAX_ID_ARGUMENT_CHARS = 12000
_MAX_CATALOG_BYTES = 64 * 1024 * 1024
_TEMPLATE_BOOTSTRAP = 'nuclei -ut -nc && nuclei -tl -nc >/dev/null && exec nuclei "$@"'


class TemplateSpec(NamedTuple):
    template_id: str
    path: str
    max_request: Optional[int]


def _canonical_url(value: str) -> Optional[str]:
    try:
        parsed = urlsplit(str(value))
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return None
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        host = parsed.hostname.lower()
        if ":" in host and not host.startswith("["):
            host = "[{}]".format(host)
        query = "?" + parsed.query if parsed.query else ""
        return "{}://{}:{}{}{}".format(parsed.scheme.lower(), host, port, parsed.path or "/", query)
    except (TypeError, ValueError):
        return None


def _container_url(value: str) -> str:
    """Adapt a loopback target so the container reaches the host's loopback service.

    Scope validation already ran against the original URL; this only rewrites the
    address used inside the container. Non-loopback targets and credential-bearing
    URLs are returned unchanged, so no additional scope is granted.
    """
    try:
        parsed = urlsplit(str(value))
    except ValueError:
        return str(value)
    if (parsed.hostname or "").lower() not in _LOOPBACK_HOSTS:
        return str(value)
    if parsed.username or parsed.password:
        return str(value)
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    netloc = "{}:{}".format(_HOST_GATEWAY, port)
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _container_args(args: List[str]) -> List[str]:
    """Rewrite only the ``-u`` target values for in-container loopback reachability."""
    result: List[str] = []
    index = 0
    while index < len(args):
        raw = str(args[index])
        flag, equals, inline = raw.partition("=")
        if flag.lower() == "-u":
            if equals:
                result.append("-u=" + _container_url(inline))
                index += 1
                continue
            result.append(raw)
            if index + 1 < len(args):
                result.append(_container_url(str(args[index + 1])))
                index += 2
            else:
                index += 1
            continue
        result.append(raw)
        index += 1
    return result


def _restore_loopback(text: str, target_urls) -> str:
    """Map the in-container gateway host back to the logical loopback target.

    The runner rewrites loopback targets to host.docker.internal for reachability,
    and nuclei reports that gateway host in its output. Restore the original
    loopback host so downstream ingest scope checks match the confirmed scope.
    """
    if not text or _HOST_GATEWAY not in text:
        return text
    loopback = []
    for url in target_urls or []:
        try:
            parsed = urlsplit(str(url))
        except ValueError:
            continue
        host = (parsed.hostname or "").lower()
        if host in _LOOPBACK_HOSTS:
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
            loopback.append((host, port))
    if not loopback:
        return text
    result = text
    for host, port in loopback:
        result = result.replace("{}:{}".format(_HOST_GATEWAY, port), "{}:{}".format(host, port))
    return result.replace(_HOST_GATEWAY, loopback[0][0])


def _template_ids_from_args(args: List[str]) -> List[str]:
    """Read literal ``-id`` values without interpreting paths or wildcards."""
    result: List[str] = []
    index = 0
    while index < len(args):
        flag, equals, inline = str(args[index]).partition("=")
        if flag.lower() != "-id":
            index += 1
            continue
        if equals:
            value = inline
            index += 1
        else:
            if index + 1 >= len(args):
                raise ValueError("template_id_missing")
            value = str(args[index + 1])
            index += 2
        for template_id in value.split(","):
            if not _TEMPLATE_ID.fullmatch(template_id):
                raise ValueError("template_id_invalid")
            if template_id not in result:
                result.append(template_id)
    return result


def _parse_template_catalog(text: str) -> List[TemplateSpec]:
    """Parse ``nuclei -tl -td -nc`` into verified IDs and request estimates."""
    specs: List[TemplateSpec] = []
    seen = set()
    path = ""
    ids: List[str] = []
    costs: List[int] = []

    def flush() -> None:
        if not path:
            return
        if len(ids) != 1 or len(costs) > 1:
            raise ValueError("template_catalog_invalid")
        template_id = ids[0]
        if template_id in seen:
            raise ValueError("template_catalog_duplicate_id")
        seen.add(template_id)
        specs.append(TemplateSpec(template_id, path, costs[0] if costs else None))

    for line in str(text).splitlines():
        if line.startswith("Template: "):
            flush()
            candidate = line[len("Template: "):].strip()
            parts = candidate.split("/")
            if (
                len(candidate) > 1024
                or not candidate.startswith("/root/nuclei-templates/")
                or not candidate.endswith(".yaml")
                or "\\" in candidate
                or ".." in parts
            ):
                raise ValueError("template_catalog_path_invalid")
            path, ids, costs = candidate, [], []
            continue
        if not path:
            continue
        match = re.match(r"^id:\s*(\S+)\s*$", line)
        if match:
            template_id = match.group(1)
            if not _TEMPLATE_ID.fullmatch(template_id):
                raise ValueError("template_catalog_id_invalid")
            ids.append(template_id)
            continue
        match = re.match(r"^\s+max-request:\s*(\d{1,6})\s*$", line)
        if match:
            costs.append(int(match.group(1)))
    flush()
    if not specs:
        raise ValueError("template_catalog_empty")
    return specs


def _request_cost(spec: TemplateSpec, unknown_request_cost: int) -> int:
    return max(1, spec.max_request if spec.max_request is not None else unknown_request_cost)


def _plan_template_batches(
    specs: List[TemplateSpec],
    request_budget: int = _REQUEST_BUDGET,
    unknown_request_cost: int = _UNKNOWN_REQUEST_COST,
    max_id_chars: int = _MAX_ID_ARGUMENT_CHARS,
    target_count: int = 1,
) -> List[List[TemplateSpec]]:
    """Pack deterministically; an individually heavy template remains fail-closed."""
    if request_budget < 1 or unknown_request_cost < 1 or max_id_chars < 1 or target_count < 1:
        raise ValueError("template_batch_budget_invalid")
    per_target_budget = max(1, request_budget // target_count)
    batches: List[List[TemplateSpec]] = []
    current: List[TemplateSpec] = []
    current_cost = 0
    current_chars = 0
    for spec in specs:
        cost = _request_cost(spec, unknown_request_cost)
        chars = len(spec.template_id)
        if chars > max_id_chars:
            raise ValueError("template_id_too_long")
        added_chars = chars + (1 if current else 0)
        if current and (current_cost + cost > per_target_budget or current_chars + added_chars > max_id_chars):
            batches.append(current)
            current, current_cost, current_chars = [], 0, 0
            added_chars = chars
        current.append(spec)
        current_cost += cost
        current_chars += added_chars
    if current:
        batches.append(current)
    return batches


def _args_with_template_ids(args: List[str], template_ids: List[str]) -> List[str]:
    result: List[str] = []
    index = 0
    while index < len(args):
        raw = str(args[index])
        flag, equals, _ = raw.partition("=")
        if flag.lower() == "-id":
            index += 1 if equals else 2
            continue
        result.append(raw)
        index += 1
    result.extend(["-id", ",".join(template_ids)])
    return result


def _catalog_filter_args(args: List[str]) -> List[str]:
    """Keep only reviewed template filters; never pass a target to catalog listing."""
    result: List[str] = []
    index = 0
    while index < len(args):
        raw = str(args[index])
        flag, equals, _ = raw.partition("=")
        flag = flag.lower()
        if flag in ("-tags", "-pt"):
            result.append(raw)
            if not equals and index + 1 < len(args):
                result.append(str(args[index + 1]))
            index += 1 if equals else 2
            continue
        if flag in ("-no-interactsh", "-disable-unsigned-templates") and not equals:
            result.append(raw)
        index += 1
    return result


def _validate_scan_args(args: List[str], scope_guard: ScopeGuard, target_urls: List[str]) -> str:
    """Keep nuclei argv bound to the reviewed URLs and a small bounded option set."""
    reviewed = {_canonical_url(url) for url in target_urls}
    if not reviewed or None in reviewed:
        return "target_argument_mismatch"
    if any(not scope_guard.decide(url).allowed for url in target_urls):
        return "target_argument_mismatch"

    selected = set()
    values = {}
    index = 0
    while index < len(args):
        raw = str(args[index])
        flag, equals, inline_value = raw.partition("=")
        flag = flag.lower()
        if flag in _BOOL_FLAGS:
            if equals:
                return "unsupported_or_unbounded_arguments"
            index += 1
            continue
        if flag not in _VALUE_FLAGS or (equals and not inline_value):
            return "unsupported_or_unbounded_arguments"
        if equals:
            value = inline_value
            index += 1
        else:
            if index + 1 >= len(args):
                return "unsupported_or_unbounded_arguments"
            value = str(args[index + 1])
            index += 2
        if not value or "\x00" in value or "\r" in value or "\n" in value or value.startswith("-"):
            return "unsupported_or_unbounded_arguments"
        values.setdefault(flag, []).append(value)

    for value in values.get("-u", []):
        canonical = _canonical_url(value)
        if canonical is None or canonical not in reviewed or not scope_guard.decide(value).allowed:
            return "target_argument_mismatch"
        selected.add(canonical)
    if selected != reviewed:
        return "target_argument_mismatch"
    for value in values.get("-tags", []):
        tags = {tag.strip().lower() for tag in value.split(",") if tag.strip()}
        if not tags or not tags <= _SAFE_TAGS:
            return "unsupported_or_unbounded_arguments"
    for value in values.get("-pt", []):
        protocols = {protocol.strip().lower() for protocol in value.split(",") if protocol.strip()}
        if not protocols or not protocols <= _SAFE_PROTOCOLS:
            return "unsupported_or_unbounded_arguments"
    id_count = 0
    id_chars = 0
    for value in values.get("-id", []):
        ids = value.split(",")
        if any(not _TEMPLATE_ID.fullmatch(template_id) for template_id in ids):
            return "unsupported_or_unbounded_arguments"
        id_count += len(ids)
        id_chars += len(value)
    if id_count > 2000 or id_chars > _MAX_ID_ARGUMENT_CHARS:
        return "unsupported_or_unbounded_arguments"
    limits = {"-rl": 2, "-c": 1, "-bs": 1, "-timeout": 5, "-retries": 1}
    for flag, maximum in limits.items():
        for value in values.get(flag, []):
            try:
                number = int(value)
            except ValueError:
                return "unsupported_or_unbounded_arguments"
            minimum = 0 if flag == "-retries" else 1
            if not minimum <= number <= maximum:
                return "unsupported_or_unbounded_arguments"
    return ""


class NucleiDockerRunner:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.name = "nuclei"

    def _docker(self) -> Optional[Path]:
        binary = self.root / "vendor" / "bin" / ("docker.exe" if os.name == "nt" else "docker")
        return binary if binary.is_file() else None

    def _args(self, docker: Path, *args: str) -> List[str]:
        endpoint = ["--host", "npipe:////./pipe/dockerDesktopLinuxEngine"] if os.name == "nt" else []
        return [str(docker)] + endpoint + list(args)

    def _pinned_image(self) -> Optional[str]:
        try:
            lock = json.loads((self.root / "tools.lock.yaml").read_text(encoding="utf-8"))
            digest = str(lock["tools"]["nuclei"]["image_digest"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not _DIGEST.match(digest):
            return None
        return "{}@{}".format(_IMAGE_REPO, digest)

    def _trusted_docker(self, docker: Path) -> bool:
        try:
            config = json.loads((self.root / "config" / "integrations" / "passive_scanners.json").read_text(encoding="utf-8"))
            return hashlib.sha256(docker.read_bytes()).hexdigest() == config["docker_sha256"]
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def _ready_docker(self) -> Tuple[Optional[Path], Optional[str], str]:
        docker = self._docker()
        if docker is None:
            return None, None, "docker_binary_missing"
        if not self._trusted_docker(docker):
            return None, None, "docker_cli_untrusted"
        image = self._pinned_image()
        if image is None:
            return None, None, "image_digest_unpinned"
        digest = image.split("@", 1)[1]
        version = subprocess.run(
            self._args(docker, "version", "--format", "{{.Server.Version}}"), capture_output=True, timeout=15
        )
        if version.returncode != 0:
            return None, None, "docker_not_ready"
        inspected = subprocess.run(self._args(docker, "image", "inspect", image), capture_output=True, timeout=15)
        if inspected.returncode != 0:
            return None, None, "image_not_present"
        info = json.loads(inspected.stdout.decode("utf-8", "replace"))
        if len(info) != 1 or info[0].get("Id") != digest or image not in (info[0].get("RepoDigests") or []):
            return None, None, "image_changed"
        return docker, image, ""

    def _catalog_templates(self, args: List[str]) -> Tuple[List[TemplateSpec], Optional[ToolResult]]:
        """List signed template metadata without contacting a reviewed target."""
        try:
            docker, image, reason = self._ready_docker()
            if reason:
                return [], ToolResult(self.name, "blocked", detail=reason)
            completed = subprocess.run(
                self._args(
                    docker,
                    "run",
                    "--rm",
                    "--pull",
                    "never",
                    "--cap-drop",
                    "ALL",
                    "--entrypoint",
                    "/bin/sh",
                    str(image),
                    "-c",
                    _TEMPLATE_BOOTSTRAP,
                    "nuclei",
                    "-tl",
                    "-td",
                    "-nc",
                    *_catalog_filter_args(args),
                ),
                capture_output=True,
                timeout=120,
            )
            if completed.returncode != 0:
                return [], ToolResult(
                    self.name,
                    "error",
                    detail="template_catalog_failed",
                    stderr=decode_tool_bytes(completed.stderr)[:2000],
                )
            if len(completed.stdout) + len(completed.stderr) > _MAX_CATALOG_BYTES:
                return [], ToolResult(self.name, "error", detail="template_catalog_too_large")
            try:
                specs = _parse_template_catalog(completed.stdout.decode("utf-8", "replace"))
            except ValueError:
                return [], ToolResult(self.name, "error", detail="template_catalog_invalid")
            return specs, None
        except subprocess.TimeoutExpired:
            return [], ToolResult(self.name, "timeout", detail="template_catalog_timeout")
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            return [], ToolResult(self.name, "error", detail=str(exc)[:400])

    def run(
        self,
        args: List[str],
        scope_guard: ScopeGuard,
        target_urls: Optional[Iterable[str]] = None,
        timeout: int = 600,
    ) -> ToolResult:
        if scope_guard.policy.target_type == "local_web":
            return ToolResult(self.name, "blocked", detail="local_scope_requires_guarded_adapter")
        reviewed_urls = list(target_urls or [])
        for url in reviewed_urls:
            decision = scope_guard.decide(url)
            if not decision.allowed:
                return ToolResult(self.name, "blocked", detail=decision.reason)
        reason = _validate_scan_args(list(args), scope_guard, reviewed_urls)
        if reason:
            return ToolResult(self.name, "blocked", detail=reason)
        docker: Optional[Path] = None
        container = ""
        try:
            docker, image, reason = self._ready_docker()
            if reason:
                return ToolResult(self.name, "blocked", detail=reason)
            container_args = _container_args(list(args))
            name = "src-auto-nuclei-" + uuid.uuid4().hex[:16]
            created = subprocess.run(
                self._args(
                    docker, "create", "--name", name, "--pull", "never", "--cap-drop", "ALL",
                    "--add-host", _HOST_GATEWAY + ":host-gateway",
                    "--entrypoint", "/bin/sh", image,
                    "-c", _TEMPLATE_BOOTSTRAP, "nuclei", *container_args,
                ),
                capture_output=True,
                timeout=30,
            )
            if created.returncode != 0:
                return ToolResult(self.name, "error", detail="container_create_failed", stderr=decode_tool_bytes(created.stderr))
            container = created.stdout.decode("utf-8", "replace").strip()
            started = subprocess.run(self._args(docker, "start", "-a", container), capture_output=True, timeout=timeout)
            state = subprocess.run(self._args(docker, "inspect", container), capture_output=True, timeout=15)
            exit_code = 1
            if state.returncode == 0:
                detail = json.loads(state.stdout.decode("utf-8", "replace"))
                exit_code = int(detail[0].get("State", {}).get("ExitCode", 1))
            return ToolResult(
                self.name,
                "completed" if exit_code == 0 else "error",
                exit_code,
                _restore_loopback(decode_tool_bytes(started.stdout), reviewed_urls),
                _restore_loopback(decode_tool_bytes(started.stderr), reviewed_urls),
            )
        except subprocess.TimeoutExpired as exc:
            return ToolResult(
                self.name,
                "timeout",
                detail=str(exc),
                stdout=_restore_loopback(decode_tool_bytes(exc.stdout), reviewed_urls),
                stderr=_restore_loopback(decode_tool_bytes(exc.stderr), reviewed_urls),
            )
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            return ToolResult(self.name, "error", detail=str(exc)[:400])
        finally:
            if container:
                try:
                    subprocess.run(self._args(docker, "rm", "-f", container), capture_output=True, timeout=20)
                except (OSError, subprocess.SubprocessError):
                    pass

    def run_batches(
        self,
        args: List[str],
        scope_guard: ScopeGuard,
        target_urls: Optional[Iterable[str]] = None,
        timeout: int = 600,
    ) -> Iterator[Dict[str, Any]]:
        """Yield each attempt so the pipeline can ingest completed batches promptly."""
        reviewed_urls = list(target_urls or [])
        if scope_guard.policy.target_type == "local_web":
            yield {
                "result": ToolResult(self.name, "blocked", detail="local_scope_requires_guarded_adapter"),
                "batch": {},
            }
            return
        for url in reviewed_urls:
            decision = scope_guard.decide(url)
            if not decision.allowed:
                yield {"result": ToolResult(self.name, "blocked", detail=decision.reason), "batch": {}}
                return
        reason = _validate_scan_args(list(args), scope_guard, reviewed_urls)
        if reason:
            yield {"result": ToolResult(self.name, "blocked", detail=reason), "batch": {}}
            return
        try:
            explicit_ids = _template_ids_from_args(list(args))
            if explicit_ids:
                specs = [TemplateSpec(template_id, "", None) for template_id in explicit_ids]
                error = None
            else:
                specs, error = self._catalog_templates(list(args))
            if error is not None:
                yield {"result": error, "batch": {}}
                return
            batches = _plan_template_batches(specs, target_count=len(reviewed_urls))
        except (OSError, ValueError, TypeError) as exc:
            yield {"result": ToolResult(self.name, "error", detail=str(exc)[:400]), "batch": {}}
            return
        if not batches:
            yield {"result": ToolResult(self.name, "error", detail="template_catalog_empty"), "batch": {}}
            return

        initial_batch_count = len(batches)

        def execute(batch: List[TemplateSpec], batch_id: str) -> Iterator[Dict[str, Any]]:
            template_ids = [item.template_id for item in batch]
            batch_args = _args_with_template_ids(list(args), template_ids)
            result = self.run(batch_args, scope_guard, reviewed_urls, timeout=timeout)
            metadata = {
                "batch_id": batch_id,
                "initial_batch_count": initial_batch_count,
                "template_count": len(batch),
                "estimated_requests": sum(_request_cost(item, _UNKNOWN_REQUEST_COST) for item in batch) * len(reviewed_urls),
                "ids_sha256": hashlib.sha256("\n".join(template_ids).encode("utf-8")).hexdigest(),
                "split": False,
            }
            if result.status == "timeout" and len(batch) > 1:
                metadata["split"] = True
                yield {"result": result, "batch": metadata}
                midpoint = len(batch) // 2
                for child_index, child in enumerate((batch[:midpoint], batch[midpoint:]), 1):
                    child_completed = yield from execute(child, "{}.{}".format(batch_id, child_index))
                    if not child_completed:
                        return False
                return True
            yield {"result": result, "batch": metadata}
            return result.status == "completed"

        for index, batch in enumerate(batches, 1):
            completed = yield from execute(batch, str(index))
            if not completed:
                return
