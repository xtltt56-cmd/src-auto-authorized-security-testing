"""Typed read-only recipes; never execute model-provided URLs, headers or argv."""

import hashlib
import http.client
import io
import json
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from .local_scope import LOCAL_WEB_TYPE, PASSIVE_PROFILE, safe_local_path, strict_boolean
from .scope import ScopeGuard, ScopePolicy


class LocalApplicationError(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class _InterruptibleReader(io.RawIOBase):
    """Keep stdlib HTTP parsing, but poll cancellation between socket reads.

    On Windows, shutting down a socket from another thread did not interrupt
    the timed receive in the regression test. Retrying recv here preserves the
    BufferedReader's partial headers; retrying HTTPResponse itself would not.
    """

    def __init__(self, transport, check):
        super().__init__()
        self.transport, self.check = transport, check
        self.reference = transport.makefile("rb", buffering=0)

    def readable(self):
        return True

    def readinto(self, buffer):
        while True:
            reason = self.check()
            if reason:
                raise LocalApplicationError(reason)
            try:
                return self.transport.recv_into(buffer)
            except socket.timeout:
                continue

    def close(self):
        try:
            self.reference.close()
        finally:
            super().close()


class _ReceivingSocket:
    def __init__(self, transport, check):
        self.transport, self.check = transport, check

    def __getattr__(self, name):
        return getattr(self.transport, name)

    def makefile(self, mode):
        if mode != "rb":
            raise ValueError("unsupported_response_stream")
        return io.BufferedReader(_InterruptibleReader(self.transport, self.check))


@dataclass(frozen=True)
class LocalReadOnlyRequest:
    request_id: str
    path: str
    method: str


@dataclass(frozen=True)
class LocalReadOnlyPlan:
    scope_digest: str
    requests: Tuple[LocalReadOnlyRequest, ...]
    manual_execution_confirmed: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], scope: ScopePolicy) -> "LocalReadOnlyPlan":
        if not isinstance(value, Mapping) or set(value) != {"plan_version", "scope_digest", "manual_execution_confirmed", "requests"}:
            raise ValueError("local_plan_fields_invalid")
        if type(value["plan_version"]) is not int or value["plan_version"] != 1:
            raise ValueError("local_plan_version_unsupported")
        if scope.target_type != LOCAL_WEB_TYPE or scope.local_web is None:
            raise ValueError("local_scope_required")
        if value["scope_digest"] != scope.digest():
            raise ValueError("scope_digest_mismatch")
        if not strict_boolean(value["manual_execution_confirmed"], "manual_execution_confirmed"):
            raise ValueError("manual_execution_confirmation_required")
        requests = value["requests"]
        if not isinstance(requests, list) or not 1 <= len(requests) <= min(64, scope.local_web.limits.request_limit):
            raise ValueError("local_requests_invalid")
        approved, seen = [], set()
        guard = ScopeGuard(scope)
        for index, item in enumerate(requests):
            if not isinstance(item, Mapping) or set(item) != {"path", "method"}:
                raise ValueError("local_request_fields_invalid")
            path, method = safe_local_path(item["path"]), item["method"]
            decision = guard.decide(scope.local_web.origin + path, method=method, now=scope.local_web.window_start)
            if not decision.allowed:
                raise ValueError(decision.reason)
            if (path, method) in seen:
                raise ValueError("duplicate_local_request")
            seen.add((path, method))
            approved.append(LocalReadOnlyRequest("request-{:03d}".format(index + 1), path, method))
        return cls(scope.digest(), tuple(approved))

    def canonical(self) -> Mapping[str, Any]:
        return {"plan_version": 1, "scope_digest": self.scope_digest,
                "manual_execution_confirmed": self.manual_execution_confirmed,
                "requests": [{"path": item.path, "method": item.method} for item in self.requests]}

    def digest(self) -> str:
        payload = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class LocalApplicationHTTP:
    """Direct connections with exact scope checks, cancellation and no body storage.

    http.client does not consult environment proxies, send a cookie jar, fetch
    page resources or follow redirects. Only this class can issue recipe URLs.
    """

    def __init__(self, scope_guard: ScopeGuard, plan: LocalReadOnlyPlan, cancel: threading.Event,
                 stop: Optional[Callable[[], bool]] = None, now_fn: Optional[Callable[[], datetime]] = None,
                 before_request: Optional[Callable[[], str]] = None, response_observer=None):
        scope = scope_guard.policy
        if scope.target_type != LOCAL_WEB_TYPE or scope.local_web is None or scope.digest() != plan.scope_digest:
            raise LocalApplicationError("scope_digest_mismatch")
        try:
            LocalReadOnlyPlan.from_mapping(plan.canonical(), scope)
        except ValueError as exc:
            raise LocalApplicationError(str(exc)) from None
        # Keep an immutable permission snapshot; also detect edits to the source
        # policy before connecting and while a request is in progress.
        self.source_policy = scope
        self.guard = ScopeGuard(ScopePolicy.from_mapping(scope.canonical()))
        self.plan = plan
        self.cancel, self.stop = cancel, stop or (lambda: False)
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.before_request = before_request or (lambda: "")
        if response_observer is not None and scope.local_web.profile_id != PASSIVE_PROFILE:
            raise LocalApplicationError("passive_profile_required")
        self.response_observer = response_observer
        self.limits = self.guard.policy.local_web.limits
        self.deadline = time.monotonic() + self.limits.task_timeout_seconds
        self.request_count = 0
        self.output_bytes = 0
        self._last_wall = None
        self._clock_lock, self._fetch_lock = threading.Lock(), threading.Lock()

    def _check(self, url: str, method: str) -> str:
        if self.cancel.is_set() or self.stop():
            return "cancelled"
        if time.monotonic() >= self.deadline:
            return "task_timeout"
        if self.source_policy.digest() != self.plan.scope_digest:
            return "scope_digest_mismatch"
        now = self.now_fn()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            return "invalid_current_time"
        now = now.astimezone(timezone.utc)
        with self._clock_lock:
            if self._last_wall is not None and now < self._last_wall:
                return "clock_rollback"
            self._last_wall = now
        decision = self.guard.decide(url, method=method, now=now)
        return "" if decision.allowed else decision.reason

    def fetch(self, request: LocalReadOnlyRequest) -> Mapping[str, Any]:
        if request not in self.plan.requests:
            raise LocalApplicationError("request_not_in_approved_plan")
        if not self._fetch_lock.acquire(blocking=False):
            raise LocalApplicationError("local_concurrency_limit")
        try:
            return self._fetch(request)
        finally:
            self._fetch_lock.release()

    def _fetch(self, request: LocalReadOnlyRequest) -> Mapping[str, Any]:
        url = self.guard.policy.local_web.origin + request.path
        for redirect_index in range(4):
            reason = self._check(url, request.method)
            if reason:
                raise LocalApplicationError(reason)
            if self.request_count >= self.limits.request_limit:
                raise LocalApplicationError("request_limit")
            reason = self.before_request()
            if reason:
                raise LocalApplicationError(reason)
            reason = self._check(url, request.method)
            if reason:
                raise LocalApplicationError(reason)
            parsed = urlsplit(url)
            timeout = min(self.limits.request_timeout_seconds, max(0.01, self.deadline - time.monotonic()))
            if parsed.scheme == "https":
                connection = http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=timeout,
                                                          context=ssl.create_default_context())
            else:
                connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
            request_deadline = time.monotonic() + timeout

            def check_receive():
                denial = self._check(url, request.method)
                if not denial and time.monotonic() >= request_deadline:
                    return "request_timeout"
                return denial

            response = None
            self.request_count += 1  # Includes attempts, redirects and connection failures; no retry loop.
            try:
                connection.connect()
                reason = check_receive()
                if reason:
                    raise LocalApplicationError(reason)
                connection.request(request.method, parsed.path or "/", headers={
                    "User-Agent": "SRC-Auto/local-readonly", "Accept-Encoding": "identity", "Connection": "close"})
                connection.sock.settimeout(min(0.1, timeout))
                connection.sock = _ReceivingSocket(connection.sock, check_receive)
                response = connection.getresponse()
                reason = check_receive()
                if reason:
                    raise LocalApplicationError(reason)
                if response.status in (301, 302, 303, 307, 308):
                    if redirect_index == 3:
                        raise LocalApplicationError("redirect_limit")
                    location = response.getheader("Location")
                    if not location:
                        raise LocalApplicationError("invalid_redirect")
                    decision = self.guard.check_redirect(url, location, method=request.method, now=self.now_fn())
                    if not decision.allowed:
                        raise LocalApplicationError(decision.reason)
                    url = decision.url
                    continue
                # Only byte counts and reviewed header PRESENCE survive the request.
                data = response.read(self.limits.response_limit_bytes + 1)
                reason = check_receive()
                if reason:
                    raise LocalApplicationError(reason)
                names = {name.lower() for name, _ in response.getheaders()}
                result = {"request_id": request.request_id, "method": request.method,
                          "path": parsed.path or "/", "status_code": response.status,
                          "response_bytes_read": len(data), "body_truncated": len(data) > self.limits.response_limit_bytes,
                          "raw_body_retained": False, "header_values_retained": False,
                          "redirects": redirect_index,
                          "header_presence": {name: name in names for name in (
                              "content-security-policy", "x-content-type-options", "x-frame-options",
                              "referrer-policy", "permissions-policy", "strict-transport-security")}}
                if self.response_observer is not None:
                    result.update(self.response_observer(url, request.method, response.status, response.getheaders(),
                                                       data, result['body_truncated']))
                data = b""
                size = len(json.dumps(result, sort_keys=True).encode("utf-8"))
                if self.output_bytes + size > self.limits.output_limit_bytes:
                    raise LocalApplicationError("output_limit")
                self.output_bytes += size
                return result
            except LocalApplicationError:
                raise
            except (OSError, http.client.HTTPException):
                raise LocalApplicationError(check_receive() or "request_failed") from None
            finally:
                if response is not None:
                    response.close()
                connection.close()
        raise LocalApplicationError("redirect_limit")
