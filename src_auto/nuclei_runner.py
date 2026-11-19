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
from typing import Iterable, List, Optional

from .models import ToolResult
from .redaction import decode_tool_bytes
from .scope import ScopeGuard

_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_IMAGE_REPO = "projectdiscovery/nuclei"


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

    def run(
        self,
        args: List[str],
        scope_guard: ScopeGuard,
        target_urls: Optional[Iterable[str]] = None,
        timeout: int = 600,
    ) -> ToolResult:
        if scope_guard.policy.target_type == "local_web":
            return ToolResult(self.name, "blocked", detail="local_scope_requires_guarded_adapter")
        for url in target_urls or []:
            decision = scope_guard.decide(url)
            if not decision.allowed:
                return ToolResult(self.name, "blocked", detail=decision.reason)
        docker = self._docker()
        if docker is None:
            return ToolResult(self.name, "blocked", detail="docker_binary_missing")
        if not self._trusted_docker(docker):
            return ToolResult(self.name, "blocked", detail="docker_cli_untrusted")
        image = self._pinned_image()
        if image is None:
            return ToolResult(self.name, "blocked", detail="image_digest_unpinned")
        digest = image.split("@", 1)[1]
        container = ""
        try:
            version = subprocess.run(self._args(docker, "version", "--format", "{{.Server.Version}}"), capture_output=True, timeout=15)
            if version.returncode != 0:
                return ToolResult(self.name, "blocked", detail="docker_not_ready")
            inspected = subprocess.run(self._args(docker, "image", "inspect", image), capture_output=True, timeout=15)
            if inspected.returncode != 0:
                return ToolResult(self.name, "blocked", detail="image_not_present")
            info = json.loads(inspected.stdout.decode("utf-8", "replace"))
            if len(info) != 1 or info[0].get("Id") != digest or image not in (info[0].get("RepoDigests") or []):
                return ToolResult(self.name, "blocked", detail="image_changed")
            name = "src-auto-nuclei-" + uuid.uuid4().hex[:16]
            created = subprocess.run(
                self._args(docker, "create", "--name", name, "--pull", "never", "--cap-drop", "ALL", image, *args),
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
                decode_tool_bytes(started.stdout),
                decode_tool_bytes(started.stderr),
            )
        except subprocess.TimeoutExpired as exc:
            return ToolResult(self.name, "timeout", detail=str(exc), stdout=decode_tool_bytes(exc.stdout), stderr=decode_tool_bytes(exc.stderr))
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            return ToolResult(self.name, "error", detail=str(exc)[:400])
        finally:
            if container:
                try:
                    subprocess.run(self._args(docker, "rm", "-f", container), capture_output=True, timeout=20)
                except (OSError, subprocess.SubprocessError):
                    pass