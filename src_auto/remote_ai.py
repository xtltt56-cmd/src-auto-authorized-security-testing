"""Manually invoked remote AI reviewers.

Remote reviewers are intentionally separate from the automatic local Ollama
path.  This module never discovers targets, calls tools, retries a request, or
stores credentials.
"""

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .ai import _redact, sanitize_finding


ALLOWED_DISPOSITIONS = {"candidate", "manual_review", "needs_manual_validation", "false_positive"}
REMOTE_AI_CONSENT_ENV = "SRC_AUTO_REMOTE_AI_CONSENT"


def _truthy_consent(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "enabled", "enable", "是", "启用"}


def remote_session_consent_enabled(provider: str, consent_env: str = "") -> bool:
    """Return whether the current startup session explicitly enabled a provider.

    Consent is process-scoped and defaults to denied.  A provider-specific
    variable, when present, overrides the generic remote-AI consent variable.
    This lets the launcher enable DeepSeek without implicitly enabling OpenAI.
    """

    name = str(provider or "").strip().lower()
    configured = str(consent_env or "").strip()
    if not configured:
        configured = "SRC_AUTO_{}_CONSENT".format(re.sub(r"[^A-Za-z0-9]+", "_", name).upper())
    if configured in os.environ:
        return _truthy_consent(os.environ.get(configured))
    return _truthy_consent(os.environ.get(REMOTE_AI_CONSENT_ENV))


class RemoteProviderError(RuntimeError):
    """A remote provider failed closed without exposing secret material."""


@dataclass(frozen=True)
class RemoteReviewRequest:
    payload: Dict[str, Any]
    digest: str

    @classmethod
    def from_finding(cls, finding: Mapping[str, Any]) -> "RemoteReviewRequest":
        safe = sanitize_finding(finding)
        payload = {
            "observation_status": "unconfirmed",
            "title": safe["title"],
            "url": safe["url"],
            "parameter": safe["parameter"],
            "severity": safe["severity"],
            "evidence": safe["evidence"],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return cls(payload, hashlib.sha256(encoded).hexdigest())


def _parse_json_text(value: Any) -> Dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        raise RemoteProviderError("empty_remote_response")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise RemoteProviderError("remote_response_not_json")
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            raise RemoteProviderError("remote_response_not_json")
    if not isinstance(parsed, dict):
        raise RemoteProviderError("remote_response_not_object")
    return parsed


def _safe_reason(value: Any, limit: int = 800) -> str:
    return _redact(value, limit)


def _usage_value(usage: Mapping[str, Any], *names: str) -> int:
    for name in names:
        value = usage.get(name)
        try:
            if value is not None:
                return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def _normalize_review(
    value: Mapping[str, Any], provider: str, model: str, usage: Mapping[str, Any], input_rate: float, output_rate: float
) -> Dict[str, Any]:
    disposition = str(value.get("disposition", "manual_review"))
    if disposition not in ALLOWED_DISPOSITIONS:
        raise RemoteProviderError("invalid_remote_disposition")
    try:
        confidence = max(0.0, min(1.0, float(value.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    checks = value.get("suggested_checks", [])
    if not isinstance(checks, list):
        checks = []
    suggested_checks = [_safe_reason(item, 240) for item in checks[:8] if str(item or "").strip()]
    input_tokens = _usage_value(usage, "prompt_tokens", "input_tokens")
    output_tokens = _usage_value(usage, "completion_tokens", "output_tokens")
    estimated_cost_usd = (input_tokens / 1000000.0) * float(input_rate) + (output_tokens / 1000000.0) * float(output_rate)
    return {
        "disposition": disposition,
        "confidence": confidence,
        "reason": _safe_reason(value.get("reason", "manual_review_required")),
        "suggested_checks": suggested_checks,
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": round(estimated_cost_usd, 10),
    }


class _RemoteProvider:
    provider_name = "remote"

    def __init__(
        self,
        endpoint: str,
        model: str,
        key_env: str,
        timeout_seconds: int = 60,
        max_input_tokens: int = 2000,
        max_output_tokens: int = 256,
        input_usd_per_million: float = 0.0,
        output_usd_per_million: float = 0.0,
        enabled: bool = True,
        manual_only: bool = True,
        allow_remote_llm: bool = False,
        consent_env: str = "",
        urlopen_fn: Optional[Callable[..., Any]] = None,
    ):
        parsed_endpoint = urlsplit(str(endpoint))
        if (
            parsed_endpoint.scheme.lower() != "https"
            or not parsed_endpoint.hostname
            or parsed_endpoint.username
            or parsed_endpoint.password
            or parsed_endpoint.query
            or parsed_endpoint.fragment
        ):
            raise ValueError("remote endpoint must use https")
        try:
            parsed_endpoint.port
        except ValueError:
            raise ValueError("remote endpoint port is invalid")
        self.endpoint = str(endpoint)
        self.model = str(model)
        self.key_env = str(key_env)
        self.timeout_seconds = int(timeout_seconds)
        self.max_input_tokens = int(max_input_tokens)
        self.max_output_tokens = int(max_output_tokens)
        self.input_usd_per_million = float(input_usd_per_million)
        self.output_usd_per_million = float(output_usd_per_million)
        self.enabled = bool(enabled)
        self.manual_only = bool(manual_only)
        self.allow_remote_llm = bool(allow_remote_llm)
        self.consent_env = str(consent_env or "").strip()
        self.urlopen_fn = urlopen_fn or urlopen

    def _key(self) -> str:
        if not remote_session_consent_enabled(self.provider_name, self.consent_env):
            raise RemoteProviderError("remote_ai_disabled_for_session")
        if not self.enabled:
            raise RemoteProviderError("provider_disabled")
        if not self.manual_only:
            raise RemoteProviderError("manual_only_required")
        if not self.allow_remote_llm:
            raise RemoteProviderError("remote_llm_disabled_by_runtime")
        key = os.environ.get(self.key_env, "").strip()
        if not key:
            raise RemoteProviderError("provider_key_missing")
        return key

    def _payload_text(self, finding: Mapping[str, Any]) -> str:
        request = RemoteReviewRequest.from_finding(finding)
        text = json.dumps(request.payload, ensure_ascii=False, sort_keys=True)
        estimated_tokens = max(1, int(math.ceil(len(text) / 4.0)))
        if estimated_tokens > self.max_input_tokens:
            raise RemoteProviderError("remote_input_token_limit_exceeded")
        return text

    def _post(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        key = self._key()
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
            },
            method="POST",
        )
        try:
            with self.urlopen_fn(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
            value = json.loads(raw)
        except HTTPError as exc:
            raise RemoteProviderError("remote_http_{}".format(getattr(exc, "code", "error")))
        except (OSError, URLError, ValueError, UnicodeError):
            raise RemoteProviderError("remote_request_failed")
        if not isinstance(value, dict):
            raise RemoteProviderError("remote_response_not_object")
        return value

    def review(self, finding: Mapping[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def _normalize(self, value: Mapping[str, Any], usage: Mapping[str, Any]) -> Dict[str, Any]:
        result = _normalize_review(
            value,
            self.provider_name,
            self.model,
            usage,
            self.input_usd_per_million,
            self.output_usd_per_million,
        )
        if result["output_tokens"] > self.max_output_tokens:
            raise RemoteProviderError("remote_output_token_limit_exceeded")
        return result


class DeepSeekProvider(_RemoteProvider):
    provider_name = "deepseek"

    def review(self, finding: Mapping[str, Any]) -> Dict[str, Any]:
        text = self._payload_text(finding)
        response = self._post(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Review only this unconfirmed observation. Do not claim exploitation success, expand scope, or suggest destructive actions. Return JSON with disposition, confidence, reason, suggested_checks.",
                    },
                    {"role": "user", "content": text},
                ],
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
                "max_tokens": self.max_output_tokens,
                "stream": False,
            }
        )
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise RemoteProviderError("deepseek_response_missing_choices")
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        usage = response.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        return self._normalize(_parse_json_text(content), usage)


class OpenRouterProvider(_RemoteProvider):
    provider_name = "openrouter"

    def review(self, finding: Mapping[str, Any]) -> Dict[str, Any]:
        text = self._payload_text(finding)
        response = self._post(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Review only this redacted, unconfirmed observation. Do not claim exploitation success, expand scope, request secrets, or suggest destructive actions. Return JSON with disposition, confidence, reason, suggested_checks.",
                    },
                    {"role": "user", "content": text},
                ],
                "provider": {
                    "data_collection": "deny",
                    "allow_fallbacks": False,
                },
                "reasoning": {"effort": "low"},
                "response_format": {"type": "json_object"},
                "max_tokens": self.max_output_tokens,
                "stream": False,
            }
        )
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise RemoteProviderError("openrouter_response_missing_choices")
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        usage = response.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        value = _parse_json_text(content)
        if str(value.get("disposition", "")) not in ALLOWED_DISPOSITIONS:
            value = dict(value)
            value["disposition"] = "manual_review"
        return self._normalize(value, usage)


class OpenAIProvider(_RemoteProvider):
    provider_name = "openai"

    _schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "disposition": {"type": "string", "enum": sorted(ALLOWED_DISPOSITIONS)},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
            "suggested_checks": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["disposition", "confidence", "reason", "suggested_checks"],
    }

    def review(self, finding: Mapping[str, Any]) -> Dict[str, Any]:
        text = self._payload_text(finding)
        response = self._post(
            {
                "model": self.model,
                "instructions": "Review only this unconfirmed observation. Do not claim exploitation success, expand scope, or suggest destructive actions.",
                "input": [{"role": "user", "content": [{"type": "input_text", "text": text}]}],
                "store": False,
                "tools": [],
                "max_output_tokens": self.max_output_tokens,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "finding_review",
                        "strict": True,
                        "schema": self._schema,
                    }
                },
            }
        )
        content = response.get("output_text")
        if not content:
            output = response.get("output", [])
            if isinstance(output, list):
                for item in output:
                    if not isinstance(item, dict) or item.get("type") != "message":
                        continue
                    for part in item.get("content", []):
                        if isinstance(part, dict) and part.get("type") == "output_text":
                            content = part.get("text")
                            break
                    if content:
                        break
        usage = response.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        return self._normalize(_parse_json_text(content), usage)
