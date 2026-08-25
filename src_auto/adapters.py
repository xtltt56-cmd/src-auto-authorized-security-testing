import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

from .models import ToolResult
from .scope import ScopeGuard


DEFAULT_TOOLS = [
    "bbot",
    "subfinder",
    "httpx",
    "katana",
    "nuclei",
    "reconftw",
    "zap",
    "schemathesis",
    "testssl",
]


class ToolRegistry:
    def __init__(self, commands: Optional[Mapping[str, str]] = None, search_paths: Optional[Iterable[Path]] = None):
        self.commands = dict(commands or {})
        self.search_paths = [Path(value) for value in (search_paths or [])]

    def command_for(self, name: str) -> Optional[str]:
        configured = self.commands.get(name)
        if configured:
            return configured
        discovered = shutil.which(name)
        if discovered:
            return discovered
        for directory in self.search_paths:
            for candidate in (
                directory / name,
                directory / (name + ".exe"),
                directory / (name + ".bat"),
                directory / (name + ".cmd"),
            ):
                if candidate.is_file():
                    return str(candidate)
        return None

    def status(self, names: Iterable[str] = DEFAULT_TOOLS) -> Dict[str, Dict[str, str]]:
        result = {}
        for name in names:
            command = self.command_for(name)
            result[name] = {"status": "available" if command else "unavailable", "command": command or ""}
        return result

    def verify(self, name: str) -> ToolResult:
        command = self.command_for(name)
        if not command:
            return ToolResult(name, "unavailable", detail="binary_not_found")
        try:
            verify_cwd = None
            args = ["-version"] if name == "zap" else ["--version"]
            if name == "zap" and command.lower().endswith((".bat", ".cmd")):
                verify_cwd = Path(command).parent
                data_dir = verify_cwd / "data"
                data_dir.mkdir(parents=True, exist_ok=True)
                args = ["-dir", str(data_dir), "-version"]
            invocation = [command] + args
            if command.lower().endswith((".bat", ".cmd")):
                invocation = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", command] + args
            completed = subprocess.run(invocation, capture_output=True, text=True, timeout=30, cwd=str(verify_cwd) if verify_cwd else None)
            output = (completed.stdout or completed.stderr or "").strip()
            return ToolResult(name, "available" if completed.returncode == 0 else "error", completed.returncode, output, completed.stderr or "")
        except (OSError, subprocess.SubprocessError) as exc:
            return ToolResult(name, "error", detail=str(exc))


class SafeToolAdapter:
    def __init__(self, name: str, registry: ToolRegistry):
        self.name = name
        self.registry = registry

    def run(
        self,
        args: List[str],
        scope_guard: ScopeGuard,
        target_urls: Optional[Iterable[str]] = None,
        timeout: int = 120,
        cwd: Optional[Path] = None,
    ) -> ToolResult:
        for url in target_urls or []:
            decision = scope_guard.decide(url)
            if not decision.allowed:
                return ToolResult(self.name, "blocked", detail=decision.reason)
        command = self.registry.command_for(self.name)
        if not command:
            return ToolResult(self.name, "unavailable", detail="binary_not_found")
        try:
            invocation = [command] + list(args)
            if command.lower().endswith((".bat", ".cmd")):
                invocation = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", command] + list(args)
            completed = subprocess.run(invocation, capture_output=True, text=True, timeout=timeout, cwd=str(cwd) if cwd else None)
            status = "completed" if completed.returncode == 0 else "error"
            return ToolResult(self.name, status, completed.returncode, completed.stdout or "", completed.stderr or "")
        except subprocess.TimeoutExpired as exc:
            return ToolResult(self.name, "timeout", detail=str(exc))
        except OSError as exc:
            return ToolResult(self.name, "error", detail=str(exc))


class ToolSuite:
    def __init__(self, registry: Optional[ToolRegistry] = None):
        self.registry = registry or ToolRegistry()

    def verify_all(self) -> Dict[str, ToolResult]:
        return {name: self.registry.verify(name) for name in DEFAULT_TOOLS}
