"""Validation for an explicitly reviewed external-tool execution plan.

The module intentionally validates a small, boring data structure.  It does not
discover targets, infer commands, or turn a candidate scope into permission.
"""

import hashlib
import json
from typing import Any, Dict, Mapping


ALLOWED_TOOLS = ("bbot", "subfinder", "httpx", "katana", "nuclei", "zap", "reconftw")
_SHELL_MARKERS = ("\x00", "\r", "\n", ";", "&&", "||", "|", ">", "<", "`", "$(")
_DANGEROUS_MARKERS = (
    "--dos",
    "--delete",
    "--brute",
    "--password",
    "--wordlist",
    "--credential",
    "credential_stuffing",
    "destructive_write",
)


class LivePlanError(ValueError):
    """Raised when a human-authored live plan is incomplete or unsafe."""


def _text(value: Any, field: str, required: bool = True) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise LivePlanError(field + " is required")
    return result


def _string_list(value: Any, field: str, required: bool = True):
    if not isinstance(value, list):
        raise LivePlanError(field + " must be a list")
    if required and not value:
        raise LivePlanError(field + " must not be empty")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise LivePlanError("{}[{}] must be a non-empty string".format(field, index))
        result.append(item.strip())
    return result


def validate_live_plan(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a canonical, hashed plan or raise ``LivePlanError``.

    The plan is deliberately not sufficient authorization on its own.  The CLI
    separately checks the policy switch and ``ScopeGuard`` before any adapter is
    started.
    """
    if not isinstance(plan, Mapping):
        raise LivePlanError("plan root must be a mapping")
    name = _text(plan.get("name"), "name")
    operator = _text(plan.get("operator"), "operator")
    authorization_note = _text(plan.get("authorization_note"), "authorization_note")
    manual_execution_confirmed = plan.get("manual_execution_confirmed", False)
    if not isinstance(manual_execution_confirmed, bool):
        raise LivePlanError("manual_execution_confirmed must be boolean")
    target_urls = _string_list(plan.get("target_urls"), "target_urls")
    for index, url in enumerate(target_urls):
        if not (url.startswith("http://") or url.startswith("https://")):
            raise LivePlanError("target_urls[{}] must use http or https".format(index))

    sequence = _string_list(plan.get("sequence"), "sequence")
    if len(set(sequence)) != len(sequence):
        raise LivePlanError("sequence must not contain duplicates")
    unknown = [name for name in sequence if name not in ALLOWED_TOOLS]
    if unknown:
        raise LivePlanError("unsupported tool: " + ", ".join(unknown))

    commands = plan.get("commands")
    if not isinstance(commands, Mapping):
        raise LivePlanError("commands must be a mapping")
    canonical_commands: Dict[str, list] = {}
    for tool in sequence:
        args = commands.get(tool, [])
        if not isinstance(args, list):
            raise LivePlanError("commands.{} must be a list".format(tool))
        canonical_args = []
        for index, arg in enumerate(args):
            if not isinstance(arg, str):
                raise LivePlanError("commands.{}[{}] must be a string".format(tool, index))
            lower = arg.lower()
            if any(marker in arg for marker in _SHELL_MARKERS):
                raise LivePlanError("shell metacharacter in commands.{}[{}]".format(tool, index))
            if any(marker in lower for marker in _DANGEROUS_MARKERS):
                raise LivePlanError("prohibited operation marker in commands.{}[{}]".format(tool, index))
            canonical_args.append(arg)
        canonical_commands[tool] = canonical_args

    canonical = {
        "name": name,
        "operator": operator,
        "authorization_note": authorization_note,
        "manual_execution_confirmed": manual_execution_confirmed,
        "target_urls": target_urls,
        "sequence": sequence,
        "commands": canonical_commands,
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    canonical["plan_digest"] = hashlib.sha256(encoded).hexdigest()
    return canonical
