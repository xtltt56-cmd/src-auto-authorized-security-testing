from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ScopeDecision:
    allowed: bool
    reason: str
    url: str = ""
    host: str = ""
    port: Optional[int] = None


@dataclass(frozen=True)
class InsertResult:
    inserted: bool
    fingerprint: str
    row_id: int


@dataclass(frozen=True)
class ToolResult:
    name: str
    status: str
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    detail: str = ""


def as_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "__dataclass_fields__"):
        return {key: getattr(value, key) for key in value.__dataclass_fields__}
    if isinstance(value, dict):
        return dict(value)
    raise TypeError("value cannot be converted to a dictionary")
