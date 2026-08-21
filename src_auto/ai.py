import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .controls import BudgetGovernor


@dataclass(frozen=True)
class Route:
    lane: str
    provider: str
    model: str
    estimated_cost: float
    endpoint: str = ""
    timeout_seconds: int = 30
    enabled: bool = True


def _redact(value: Any, limit: int = 1600) -> str:
    text = str(value or "")
    text = re.sub(
        r"(?i)(token|secret|password|authorization|cookie|api[_-]?key)\s*[:=]\s*[^\s;&,]+",
        r"\1=[REDACTED]",
        text,
    )
    return text[:limit]


def _safe_url(value: Any) -> str:
    try:
        parsed = urlsplit(str(value or ""))
        if not parsed.scheme or not parsed.hostname:
            return _redact(value, 600)
        host = parsed.hostname
        port = ""
        try:
            if parsed.port:
                port = ":{}".format(parsed.port)
        except ValueError:
            port = ""
        return "{}://{}{}{}".format(parsed.scheme, host, port, parsed.path or "/")[:800]
    except ValueError:
        return _redact(value, 600)


def sanitize_finding(finding: Mapping[str, Any]) -> Dict[str, str]:
    """Keep only minimal Finding fields before sending anything to a local model."""
    return {
        "title": _redact(finding.get("title"), 300),
        "url": _safe_url(finding.get("url")),
        "parameter": _redact(finding.get("parameter"), 200),
        "severity": _redact(finding.get("severity"), 40),
        "evidence": _redact(finding.get("evidence"), 1200),
    }


class OllamaProvider:
    def __init__(
        self,
        endpoint: str,
        model: str,
        timeout_seconds: int = 30,
        urlopen_fn: Optional[Callable[..., Any]] = None,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout_seconds = int(timeout_seconds)
        self.urlopen_fn = urlopen_fn or urlopen

    def _request(self, path: str, payload: Optional[Mapping[str, Any]] = None) -> Mapping[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.endpoint + path, data=data, headers=headers, method="POST" if data else "GET")
        with self.urlopen_fn(request, timeout=self.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Ollama response must be an object")
        return value

    def health(self) -> bool:
        try:
            response = self._request("/api/tags")
            models = response.get("models", [])
            names = {str(item.get("name", "")) for item in models if isinstance(item, dict)}
            return self.model in names
        except (OSError, HTTPError, URLError, ValueError, KeyError, TypeError):
            return False

    @staticmethod
    def _parse_content(content: Any) -> Dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            raise ValueError("empty model triage response")
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise
            value = json.loads(text[start : end + 1])
        if not isinstance(value, dict):
            raise ValueError("model triage must be a JSON object")
        disposition = str(value.get("disposition", "manual_review"))
        allowed = {"candidate", "manual_review", "needs_manual_validation", "false_positive"}
        if disposition not in allowed:
            disposition = "manual_review"
        try:
            confidence = max(0.0, min(1.0, float(value.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        return {
            "disposition": disposition,
            "confidence": confidence,
            "reason": _redact(value.get("reason", "model_observation"), 400),
        }

    def triage(self, finding: Mapping[str, Any]) -> Dict[str, Any]:
        safe = sanitize_finding(finding)
        prompt = (
            "你是安全分诊助手。只根据最小观察信息输出严格 JSON，不扩展授权范围，"
            "不声称已利用成功。字段必须是 disposition、confidence、reason。\n"
            + json.dumps(safe, ensure_ascii=False, sort_keys=True)
        )
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "think": False,
            "options": {"temperature": 0, "num_predict": 128},
            "prompt": prompt,
        }
        response = self._request("/api/generate", payload)
        content = response.get("response")
        if not content:
            message = response.get("message", {})
            content = message.get("content") if isinstance(message, dict) else None
        result = self._parse_content(content)
        result["provider"] = "ollama"
        result["model"] = self.model
        return result


class ModelRouter:
    """Select a lane and instantiate a local provider only when configured."""

    def __init__(self, config: Optional[Mapping[str, Any]] = None, urlopen_fn: Optional[Callable[..., Any]] = None):
        config = config or {}
        self.default_lane = str(config.get("default_lane", "primary"))
        self.lanes = dict(config.get("lanes", {}))
        self.urlopen_fn = urlopen_fn

    def route(self, task: str, complexity: str = "normal") -> Route:
        lane = "expert" if complexity == "high" else ("bulk" if complexity == "low" else self.default_lane)
        lane_cfg = self.lanes.get(lane, {})
        return Route(
            lane=lane,
            provider=str(lane_cfg.get("provider", "local")),
            model=str(lane_cfg.get("model", "heuristic-v1")),
            estimated_cost=float(lane_cfg.get("estimated_cost", 0.0)),
            endpoint=str(lane_cfg.get("endpoint", "http://127.0.0.1:11434")),
            timeout_seconds=int(lane_cfg.get("timeout_seconds", 30)),
            enabled=bool(lane_cfg.get("enabled", True)),
        )

    def provider_for(self, route: Route) -> Optional[OllamaProvider]:
        if route.provider.lower() != "ollama" or not route.enabled:
            return None
        return OllamaProvider(route.endpoint, route.model, route.timeout_seconds, self.urlopen_fn)


class AITriage:
    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        budget: Optional[BudgetGovernor] = None,
        spend_callback: Optional[Callable[[float, str], None]] = None,
    ):
        self.router = router or ModelRouter()
        self.budget = budget
        self.spend_callback = spend_callback

    def _fallback(self, finding: Mapping[str, Any], route: Route, reason: str) -> Dict[str, Any]:
        severity = str(finding.get("severity", "info")).lower()
        evidence = str(finding.get("evidence", ""))
        if severity in ("high", "critical"):
            disposition = "needs_manual_validation"
            confidence = 0.72
        elif evidence:
            disposition = "candidate"
            confidence = 0.62
        else:
            disposition = "needs_manual_validation"
            confidence = 0.35
        return {
            "disposition": disposition,
            "confidence": confidence,
            "reason": reason,
            "route": route.__dict__,
        }

    def classify(self, finding: Mapping[str, Any]) -> Dict[str, Any]:
        severity = str(finding.get("severity", "info")).lower()
        route = self.router.route("triage", "high" if severity in ("high", "critical") else "normal")
        if self.budget is not None and route.estimated_cost:
            if not self.budget.can_spend(route.estimated_cost):
                return {
                    "disposition": "manual_review",
                    "confidence": 0.0,
                    "reason": "budget_limit_exceeded",
                    "route": route.__dict__,
                }
            self.budget.record(route.estimated_cost, "ai_triage")
            if self.spend_callback:
                self.spend_callback(route.estimated_cost, "ai_triage")
        provider = self.router.provider_for(route)
        if provider is not None:
            try:
                result = provider.triage(finding)
                result["route"] = route.__dict__
                return result
            except (OSError, HTTPError, URLError, ValueError, KeyError, TypeError, TimeoutError):
                return self._fallback(finding, route, "ollama_fallback")
        return self._fallback(finding, route, "deterministic_local_triage")
