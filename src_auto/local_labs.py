"""Fail-closed local vulnerable-lab inventory and Docker command helpers.

This module does not contact a target by itself.  It validates a project-owned
inventory, creates fixed Docker Compose arguments, and translates inspect data
into an explicit lifecycle state.  Network contact is performed only by the
caller after the returned spec has passed these checks.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_SAFE_ACTIONS = frozenset({"up", "down", "stop", "start", "restart", "ps"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


def safe_lab_id(value: str) -> str:
    lab_id = str(value or "").strip().lower()
    if not _ID_RE.fullmatch(lab_id):
        raise ValueError("invalid_lab_id")
    return lab_id


@dataclass(frozen=True)
class LabSpec:
    lab_id: str
    service: str
    image: str
    digest: str
    container_port: int
    host: str
    host_port: int
    health_url: str

    @property
    def pinned_image(self) -> str:
        return "{}@{}".format(self.image, self.digest)

    @property
    def is_loopback_only(self) -> bool:
        return self.host.lower().rstrip(".") in _LOOPBACK_HOSTS

    def to_mapping(self) -> Dict[str, Any]:
        return {
            "lab_id": self.lab_id,
            "service": self.service,
            "image": self.image,
            "digest": self.digest,
            "pinned_image": self.pinned_image,
            "container_port": self.container_port,
            "host": self.host,
            "host_port": self.host_port,
            "health_url": self.health_url,
            "loopback_only": self.is_loopback_only,
        }


def _port(value: Any, field: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ValueError("{}_must_be_integer".format(field))
    if not 1 <= port <= 65535:
        raise ValueError("{}_out_of_range".format(field))
    return port


def _parse_spec(raw: Mapping[str, Any]) -> LabSpec:
    lab_id = safe_lab_id(raw.get("lab_id", ""))
    service = safe_lab_id(raw.get("service", ""))
    image = str(raw.get("image", "")).strip()
    digest = str(raw.get("digest", "")).strip().lower()
    host = str(raw.get("host", "")).strip().lower().rstrip(".")
    if not image or "@" in image or ":latest" in image.lower():
        raise ValueError("image_must_be_repository_without_tag")
    if not _DIGEST_RE.fullmatch(digest):
        raise ValueError("image_digest_required")
    if host not in _LOOPBACK_HOSTS:
        raise ValueError("lab_host_must_be_loopback")
    container_port = _port(raw.get("container_port"), "container_port")
    host_port = _port(raw.get("host_port"), "host_port")
    health_url = str(raw.get("health_url", "")).strip()
    parsed = urlsplit(health_url)
    expected_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in _LOOPBACK_HOSTS:
        raise ValueError("health_url_must_be_loopback_http")
    if expected_port != host_port:
        raise ValueError("health_url_port_mismatch")
    if parsed.username or parsed.password:
        raise ValueError("health_url_must_not_contain_credentials")
    if lab_id != service:
        raise ValueError("lab_id_service_mismatch")
    return LabSpec(
        lab_id=lab_id,
        service=service,
        image=image,
        digest=digest,
        container_port=container_port,
        host=host,
        host_port=host_port,
        health_url=health_url,
    )


def load_lab_specs(path: Path) -> List[LabSpec]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("lab_inventory_invalid: {}".format(exc))
    raw_labs = document.get("labs") if isinstance(document, Mapping) else None
    if not isinstance(raw_labs, list) or not raw_labs:
        raise ValueError("lab_inventory_requires_labs")
    specs: List[LabSpec] = []
    seen = set()
    ports = set()
    for raw in raw_labs:
        if not isinstance(raw, Mapping):
            raise ValueError("lab_entry_must_be_object")
        spec = _parse_spec(raw)
        if spec.lab_id in seen:
            raise ValueError("duplicate_lab_id")
        if spec.host_port in ports:
            raise ValueError("duplicate_lab_port")
        seen.add(spec.lab_id)
        ports.add(spec.host_port)
        specs.append(spec)
    return specs


def build_compose_command(compose_file: Path, spec: LabSpec, action: str) -> List[str]:
    action = str(action or "").strip().lower()
    if action not in _SAFE_ACTIONS:
        raise ValueError("unsupported_lab_action")
    compose = str(Path(compose_file).resolve())
    if action == "up":
        return ["docker", "compose", "-f", compose, "up", "-d", spec.service]
    if action == "ps":
        return ["docker", "compose", "-f", compose, "ps", "--format", "json", spec.service]
    if action == "down":
        return ["docker", "compose", "-f", compose, "down", "--remove-orphans"]
    return ["docker", "compose", "-f", compose, action, spec.service]


def parse_lab_status(spec: LabSpec, inspect: Mapping[str, Any]) -> Dict[str, Any]:
    state = str(inspect.get("State", "")).strip().lower()
    health = str(inspect.get("Health", "")).strip().lower()
    if state == "running" and health == "healthy":
        status = "READY"
    elif state == "running" and health == "starting":
        status = "STARTING"
    elif state == "running" and health in ("", "none", "unhealthy"):
        status = "BLOCKED_NO_HEALTH" if health in ("", "none") else "UNHEALTHY"
    elif state in ("exited", "dead", "created", ""):
        status = "STOPPED" if state in ("exited", "dead") else "NOT_FOUND"
    else:
        status = "NOT_READY"
    return {
        "lab_id": spec.lab_id,
        "service": spec.service,
        "status": status,
        "state": state or "unknown",
        "health": health or "none",
        "health_url": spec.health_url,
        "host": spec.host,
        "host_port": spec.host_port,
        "pinned_image": spec.pinned_image,
        "network_contact": False,
    }


def index_specs(specs: Iterable[LabSpec]) -> Dict[str, LabSpec]:
    result: Dict[str, LabSpec] = {}
    for spec in specs:
        if spec.lab_id in result:
            raise ValueError("duplicate_lab_id")
        result[spec.lab_id] = spec
    return result


class LocalLabManager:
    """Operate only on the project-owned, fixed local lab inventory."""

    def __init__(self, project_root: Path, inventory_path: Path, compose_file: Path):
        self.project_root = Path(project_root).resolve()
        self.inventory_path = Path(inventory_path).resolve()
        self.compose_file = Path(compose_file).resolve()
        for candidate in (self.inventory_path, self.compose_file):
            try:
                candidate.relative_to(self.project_root)
            except ValueError:
                raise ValueError("lab_control_file_outside_project")
        self.specs = index_specs(load_lab_specs(self.inventory_path))

    def spec(self, lab_id: str) -> LabSpec:
        wanted = safe_lab_id(lab_id)
        try:
            return self.specs[wanted]
        except KeyError:
            raise ValueError("unknown_lab_id")

    @staticmethod
    def container_name(spec: LabSpec) -> str:
        return "src-auto-{}".format(spec.lab_id)

    def command(self, action: str, lab_id: str) -> List[str]:
        spec = self.spec(lab_id)
        return build_compose_command(self.compose_file, spec, action)

    def _inspect(self, spec: LabSpec) -> Dict[str, Any]:
        command = [
            "docker",
            "inspect",
            "--format",
            "{{json .State}}",
            self.container_name(spec),
        ]
        result = subprocess.run(
            command,
            cwd=str(self.project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            shell=False,
            check=False,
        )
        if result.returncode != 0:
            return {}
        try:
            state = json.loads(result.stdout.strip())
        except (TypeError, ValueError):
            return {}
        if not isinstance(state, Mapping):
            return {}
        health = state.get("Health", {})
        health_status = health.get("Status", "none") if isinstance(health, Mapping) else "none"
        return {"State": state.get("Status", ""), "Health": health_status}

    def status(self, lab_id: str, inspect_fn=None) -> Dict[str, Any]:
        spec = self.spec(lab_id)
        raw = inspect_fn(self.container_name(spec)) if inspect_fn else self._inspect(spec)
        return parse_lab_status(spec, raw if isinstance(raw, Mapping) else {})

    @staticmethod
    def _run(command: Sequence[str], project_root: Path) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                list(command),
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"status": "FAILED", "reason": "docker_command_failed", "detail": str(exc)[:500], "returncode": None}
        return {
            "status": "COMPLETED" if result.returncode == 0 else "FAILED",
            "reason": "",
            "detail": (result.stderr or result.stdout or "")[-4000:],
            "returncode": result.returncode,
            "command": list(command),
            "network_contact": False,
        }

    def _wait_health(self, spec: LabSpec, timeout: int = 120) -> Dict[str, Any]:
        deadline = time.time() + max(1, int(timeout))
        last = self.status(spec.lab_id)
        while time.time() < deadline:
            try:
                request = Request(spec.health_url, headers={"User-Agent": "SRC-Auto/local-lab-health"})
                with urlopen(request, timeout=3) as response:
                    final_url = str(getattr(response, "geturl", lambda: spec.health_url)())
                    final = urlsplit(final_url)
                    status_code = int(getattr(response, "status", getattr(response, "code", 0)) or 0)
                    if (
                        status_code == 200
                        and final.hostname in _LOOPBACK_HOSTS
                        and (final.port or (443 if final.scheme == "https" else 80)) == spec.host_port
                    ):
                        result = self.status(spec.lab_id)
                        result["status"] = "READY"
                        result["network_contact"] = True
                        result["http_status"] = status_code
                        return result
            except (OSError, ValueError):
                pass
            last = self.status(spec.lab_id)
            if last["status"] in ("STOPPED", "NOT_FOUND", "UNHEALTHY"):
                break
            time.sleep(1)
        last["status"] = "BLOCKED_HEALTH_TIMEOUT"
        last["network_contact"] = False
        return last

    def operate(self, action: str, lab_id: str, wait: bool = True) -> Dict[str, Any]:
        action = str(action or "").strip().lower()
        requested_action = action
        spec = self.spec(lab_id)
        if action == "status":
            return self.status(spec.lab_id)
        if action == "reset":
            remove = ["docker", "compose", "-f", str(self.compose_file), "rm", "-sf", spec.service]
            removed = self._run(remove, self.project_root)
            if removed["status"] != "COMPLETED":
                return {"status": "FAILED", "reason": "lab_reset_remove_failed", "remove": removed, "network_contact": False}
            action = "up"
        elif action == "start":
            # ``docker compose start`` silently succeeds when the service has
            # never been created.  ``up -d`` is idempotent and handles both a
            # missing and an existing stopped container.
            action = "up"
        command = build_compose_command(self.compose_file, spec, action)
        result = self._run(command, self.project_root)
        if result["status"] != "COMPLETED":
            return {"lab_id": spec.lab_id, "action": action, **result}
        result.update({"lab_id": spec.lab_id, "action": requested_action, "pinned_image": spec.pinned_image})
        if action == "up" and wait:
            health = self._wait_health(spec)
            result["health"] = health
            result["status"] = "READY" if health.get("status") == "READY" else health.get("status", "BLOCKED")
            result["network_contact"] = bool(health.get("network_contact"))
        return result
