"""Opt-in Ollama OpenAI-compatible tool roundtrip; no cloud or target traffic."""
import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src_auto.agent_actions import NoRedirect
from src_auto.agent_provider import configured_model
from src_auto.agent_resources import WindowsResources
from src_auto.config import load_mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    output.relative_to(ROOT)
    model = configured_model(ROOT, "local").provider
    resources = WindowsResources(load_mapping(ROOT / "config/policy.yaml"))
    opener = build_opener(ProxyHandler({}), NoRedirect())
    report = {"model": model.model, "scope": "local harmless function roundtrip only", "ok": False}
    started = time.monotonic()
    try:
        def chat(messages, tools=None):
            resource = resources.check()
            if not resource["allowed"] or (ROOT / "STOP").exists():
                raise RuntimeError("resource_or_stop_guard")
            payload = {"model": model.model, "messages": messages, "stream": False,
                       "reasoning_effort": "none", "temperature": 0, "max_tokens": 128}
            if tools is not None:
                payload["tools"] = tools
            request = Request("http://127.0.0.1:11434/v1/chat/completions",
                              data=json.dumps(payload).encode("utf-8"),
                              headers={"Content-Type": "application/json"}, method="POST")
            with opener.open(request, timeout=120) as response:
                return json.load(response)

        messages = [
            {"role": "system", "content": "You are a tool-calling assistant. Never invent a tool result. Use the provided function to read the requested probe. After a tool result, reply with only its status value."},
            {"role": "user", "content": "请用 get_local_status 查询 probe-20261005 的状态。状态只有工具知道，请先调用工具。"},
        ]
        tools = [{"type": "function", "function": {"name": "get_local_status",
                  "description": "读取固定本地测试状态；不访问文件、网络或系统",
                  "parameters": {"type": "object", "properties": {"probe": {"type": "string"}},
                                 "required": ["probe"], "additionalProperties": False}}}]
        first = chat(messages, tools)
        message = first["choices"][0]["message"]
        calls = message.get("tool_calls", [])
        report["first_response"] = {"finish_reason": first["choices"][0].get("finish_reason"),
                                    "content": message.get("content"), "tool_calls": calls,
                                    "has_reasoning": bool(message.get("reasoning_content")),
                                    "usage": first.get("usage")}
        if len(calls) != 1 or calls[0]["function"]["name"] != "get_local_status":
            raise RuntimeError("expected_one_local_tool_call")
        if json.loads(calls[0]["function"]["arguments"]) != {"probe": "probe-20261005"}:
            raise RuntimeError("unexpected_arguments")
        messages.extend([message, {"role": "tool", "tool_call_id": calls[0]["id"],
                                   "content": json.dumps({"status": "LOCAL_ONLY_OK"})}])
        # OpenCode / AI SDK retain the tool definitions on subsequent turns.
        second = chat(messages, tools)
        answer = second["choices"][0]["message"]
        report["second_response"] = {"finish_reason": second["choices"][0].get("finish_reason"),
                                     "content": answer.get("content"), "tool_calls": answer.get("tool_calls", []),
                                     "has_reasoning": bool(answer.get("reasoning_content"))}
        content = answer.get("content", "").strip()
        if answer.get("tool_calls") or "LOCAL_ONLY_OK" not in content:
            raise RuntimeError("tool_result_not_used")
        if content != "LOCAL_ONLY_OK":
            raise RuntimeError("output_format_mismatch")
        report.update(ok=True, tool="get_local_status", answer=answer["content"],
                      usage=[first.get("usage"), second.get("usage")])
    except Exception as exc:
        report["error"] = type(exc).__name__ + ":" + str(exc)[:200]
    finally:
        report["seconds"] = round(time.monotonic() - started, 3)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        model._request("/api/generate", {"model": model.model, "keep_alive": 0})
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
