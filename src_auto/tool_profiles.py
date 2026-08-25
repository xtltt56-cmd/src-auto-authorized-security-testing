import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class ToolProfile:
    name: str
    role: str
    command: str
    source: str
    allowed_modes: Tuple[str, ...]
    is_vulnerability_scanner: bool = False
    optional: bool = True


def load_tool_profiles(path: Path) -> Dict[str, ToolProfile]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_profiles = document.get("tools", {})
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise ValueError("tool_profiles_missing")
    result = {}
    for name, raw in raw_profiles.items():
        if not isinstance(raw, dict):
            raise ValueError("tool_profile_invalid: {}".format(name))
        command = str(raw.get("command", "")).strip()
        source = str(raw.get("source", "")).strip()
        modes = tuple(str(value) for value in raw.get("allowed_modes", []) if str(value).strip())
        if not command or Path(command).is_absolute() or ".." in Path(command).parts:
            raise ValueError("tool_profile_command_outside_project: {}".format(name))
        if not source.startswith("https://") or not modes:
            raise ValueError("tool_profile_metadata_missing: {}".format(name))
        result[name] = ToolProfile(
            name=name,
            role=str(raw.get("role", "utility")),
            command=command,
            source=source,
            allowed_modes=modes,
            is_vulnerability_scanner=bool(raw.get("is_vulnerability_scanner", False)),
            optional=bool(raw.get("optional", True)),
        )
    return result


def project_tool_search_paths(project_root: Path) -> Tuple[Path, ...]:
    root = Path(project_root)
    return (
        root / "vendor" / "bin",
        root / "vendor" / "pytools" / "bbot" / "Scripts",
        root / "vendor" / "pytools" / "schemathesis" / "Scripts",
        root / "vendor" / "zap" / "ZAP_2.17.0",
    )


def profile_names(profiles: Iterable[ToolProfile]) -> Tuple[str, ...]:
    return tuple(profile.name for profile in profiles)
