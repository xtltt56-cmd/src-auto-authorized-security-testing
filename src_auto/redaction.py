"""Bounded, credential-safe rendering of external tool output (stdlib only).

External scanners print cookies, tokens and query values into stdout/stderr.
Nothing raw may reach the events table, reports or model context: every tool
output is redacted and truncated before it is persisted.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_TOOL_OUTPUT_CHARS = 16000
MAX_TOOL_OUTPUT_BYTES = 1048576

_SECRET_PATTERNS = (
    (
        re.compile(r"(?i)\b(authorization)\b\s*[:=]\s*(?:[A-Za-z][A-Za-z0-9_-]*\s+)?[^\s;&,]+"),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(set-cookie|cookie)\b\s*[:=]\s*[^\r\n;&,]+"),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(token|secret|password|api[_-]?key)\b\s*[:=]\s*[^\s;&,]+"),
        r"\1=[REDACTED]",
    ),
)
_URL = re.compile(r"https?://[^\s\"'<>]+")


def _mask_url(match):
    raw = match.group(0).rstrip(".,;:)]}")
    try:
        parsed = urlsplit(raw)
        if not parsed.hostname:
            return "[REDACTED_URL]"
        query = urlencode(
            [(key, "[REDACTED]") for key, _ in parse_qsl(parsed.query, keep_blank_values=True)],
            quote_via=lambda string, safe, encoding=None, errors=None: string,
        )
        netloc = parsed.hostname.lower()
        if parsed.port:
            netloc += ":{}".format(parsed.port)
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", query, ""))
    except ValueError:
        return "[REDACTED_URL]"


def redact_tool_output(value, limit=MAX_TOOL_OUTPUT_CHARS):
    """Mask credentials and URL query values, then bound the length."""
    text = str(value or "")
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    text = _URL.sub(_mask_url, text)
    if len(text) > limit:
        text = text[:limit] + "\n[TRUNCATED]"
    return text


def decode_tool_bytes(raw, cap=MAX_TOOL_OUTPUT_BYTES):
    """Decode tool output as UTF-8 with replacement, never the Windows locale.

    Scanners emit UTF-8; decoding with the system code page (GBK on zh-CN
    Windows) corrupts output or raises. Invalid bytes become U+FFFD and the
    stream is capped so a runaway tool cannot exhaust memory or disk.
    """
    data = raw or b""
    if not isinstance(data, bytes):
        data = str(data).encode("utf-8", "replace")
    if len(data) > cap:
        data = data[:cap] + b"\n[TRUNCATED]"
    return data.decode("utf-8", "replace")