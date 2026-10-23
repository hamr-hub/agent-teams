#!/usr/bin/env python3
"""OpenAI-Chat -> Anthropic-Messages shim for MCode-style local gateways.

Claude Code only speaks the Anthropic Messages API. Home-grown gateways usually
expose OpenAI Chat Completions only. This proxy translates one to the other, so
agents defined the Claude Code way can run against any OpenAI-compatible model.

    claude  --(Anthropic /v1/messages)------>  this proxy  --(OpenAI /v1/chat/completions)-->  gateway
    codex   --(OpenAI /v1/responses)-------->  this proxy  --(OpenAI /v1/chat/completions)-->  gateway

Run:
    UPSTREAM=http://localhost:7863 MODEL=cn:glm-5.3 python3 claude_gateway_proxy.py
    # then: ANTHROPIC_BASE_URL=http://localhost:8787 claude ...

Design notes
- Streaming (SSE) is implemented because Claude Code streams by default.
- `tool_use` / `tool_result` are mapped both ways; without that the agent
  framework cannot call tools and the model appears to "do nothing".
- `reasoning_content` / `reasoning` from OpenAI-style reasoning models is
  dropped from the Anthropic text stream (Claude Code shows thinking separately
  and a provider without a signature block cannot round-trip it).
- Only the pieces Claude Code actually sends are translated. Unknown fields are
  ignored rather than rejected, so newer clients keep working.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterable

UPSTREAM = os.environ.get("UPSTREAM", "http://localhost:7863").rstrip("/")
API_KEY = os.environ.get("UPSTREAM_API_KEY") or os.environ.get("GATEWAY_API_KEY", "")
DEFAULT_MODEL = os.environ.get("MODEL", "cn:glm-5.3")
FAST_MODEL = os.environ.get("FAST_MODEL", DEFAULT_MODEL)
PORT = int(os.environ.get("PORT", "8787"))
VERBOSE = os.environ.get("VERBOSE", "") not in ("", "0", "false")


def log(*args: Any) -> None:
    if VERBOSE:
        print("[proxy]", *args, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# request translation: Anthropic -> OpenAI
# --------------------------------------------------------------------------- #

TEXT_BLOCK_TYPES = frozenset(
    {"text", "input_text", "output_text", "summary_text", "reasoning_text"}
)


def _text_of(content: Any) -> str:
    """Flatten a content block list (Anthropic *or* OpenAI Responses) to text."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind in TEXT_BLOCK_TYPES or (kind is None and "text" in block):
            parts.append(block.get("text", ""))
        elif kind == "tool_result":
            parts.append(_text_of(block.get("content")))
    return "\n".join(p for p in parts if p)


def _image_parts(content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, list):
        return []
    out = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "image":
            src = block.get("source") or {}
            if src.get("type") == "base64":
                out.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{src.get('media_type', 'image/png')};base64,{src.get('data', '')}"
                        },
                    }
                )
    return out


def anthropic_to_openai(body: dict[str, Any]) -> dict[str, Any]:
    model = body.get("model") or DEFAULT_MODEL
    if model in ("haiku", "sonnet", "opus", "default", "ark-code-latest"):
        model = DEFAULT_MODEL
    messages: list[dict[str, Any]] = []

    system = body.get("system")
    if system:
        messages.append({"role": "system", "content": _text_of(system)})

    for msg in body.get("messages") or []:
        role = msg.get("role")
        content = msg.get("content")

        if role == "user":
            tool_results = [
                b for b in content or [] if isinstance(b, dict) and b.get("type") == "tool_result"
            ] if isinstance(content, list) else []
            # Anthropic puts tool results in user turns; OpenAI wants role=tool.
            for tr in tool_results:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tr.get("tool_use_id", ""),
                        "content": _text_of(tr.get("content")) or "(no output)",
                    }
                )
            text = _text_of(
                [b for b in content if not (isinstance(b, dict) and b.get("type") == "tool_result")]
                if isinstance(content, list)
                else content
            )
            images = _image_parts(content)
            if text or images:
                if images:
                    messages.append(
                        {"role": "user", "content": [{"type": "text", "text": text}, *images]}
                    )
                else:
                    messages.append({"role": "user", "content": text})

        elif role == "assistant":
            blocks = content if isinstance(content, list) else []
            text = _text_of(blocks)
            tool_calls = [
                {
                    "id": b.get("id", f"call_{uuid.uuid4().hex[:12]}"),
                    "type": "function",
                    "function": {
                        "name": b.get("name", ""),
                        "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False),
                    },
                }
                for b in blocks
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": text or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            if entry["content"] is None and not tool_calls:
                entry["content"] = ""
            messages.append(entry)

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": body.get("max_tokens") or 8192,
        "stream": bool(body.get("stream")),
    }
    if body.get("temperature") is not None:
        payload["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        payload["top_p"] = body["top_p"]
    if body.get("stop_sequences"):
        payload["stop"] = body["stop_sequences"]

    tools = body.get("tools") or []
    if tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
            for t in tools
            if isinstance(t, dict)
        ]
        choice = body.get("tool_choice") or {}
        ctype = choice.get("type") if isinstance(choice, dict) else None
        if ctype == "tool":
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": choice.get("name", "")},
            }
        elif ctype == "any":
            payload["tool_choice"] = "required"
        elif ctype == "auto":
            payload["tool_choice"] = "auto"
    return payload


# --------------------------------------------------------------------------- #
# response translation: OpenAI -> Anthropic
# --------------------------------------------------------------------------- #

def _map_stop(reason: str | None, has_tool: bool) -> str:
    if has_tool:
        return "tool_use"
    if reason == "length":
        return "max_tokens"
    if reason in ("tool_calls", "function_call"):
        return "tool_use"
    return "end_turn"


def openai_to_anthropic(data: dict[str, Any], model: str) -> dict[str, Any]:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    blocks: list[dict[str, Any]] = []
    text = message.get("content")
    if isinstance(text, list):
        text = _text_of(text)
    if text:
        blocks.append({"type": "text", "text": text})
    tool_calls = message.get("tool_calls") or []
    for call in tool_calls:
        fn = call.get("function") or {}
        raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            args = {"_raw": raw}
        blocks.append(
            {
                "type": "tool_use",
                "id": call.get("id") or f"toolu_{uuid.uuid4().hex[:16]}",
                "name": fn.get("name", ""),
                "input": args,
            }
        )
    if not blocks:
        blocks.append({"type": "text", "text": ""})
    usage = data.get("usage") or {}
    return {
        "id": data.get("id") or f"msg_{uuid.uuid4().hex[:20]}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": blocks,
        "stop_reason": _map_stop(choice.get("finish_reason"), bool(tool_calls)),
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


class StreamState:
    """Accumulates OpenAI deltas and emits Anthropic SSE events."""

    def __init__(self, model: str, writer) -> None:
        self.model = model
        self.write = writer
        self.index = 0
        self.block_open = False
        self.tools: dict[int, dict[str, Any]] = {}
        self.tool_index_by_key: dict[str, int] = {}
        self.text_parts: list[str] = []
        self.finish: str | None = None
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.started_tools: set[int] = set()

    def start(self) -> None:
        self.emit(
            "message_start",
            {
                "message": {
                    "id": f"msg_{uuid.uuid4().hex[:20]}",
                    "type": "message",
                    "role": "assistant",
                    "model": self.model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                }
            },
        )

    def emit(self, event: str, data: dict[str, Any]) -> None:
        self.write(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n")

    def text(self, delta: str) -> None:
        if not delta:
            return
        if not self.block_open:
            self.emit(
                "content_block_start",
                {"index": self.index, "content_block": {"type": "text", "text": ""}},
            )
            self.block_open = True
        self.text_parts.append(delta)
        self.emit(
            "content_block_delta",
            {"index": self.index, "delta": {"type": "text_delta", "text": delta}},
        )

    def close_text(self) -> None:
        if self.block_open:
            self.emit("content_block_stop", {"index": self.index})
            self.block_open = False
            self.index += 1

    def tool_delta(self, call: dict[str, Any]) -> None:
        key = call.get("id") or f"_anon_{call.get('index', 0)}"
        fn = call.get("function") or {}
        if key not in self.tool_index_by_key:
            self.close_text()
            idx = self.index
            self.tool_index_by_key[key] = idx
            self.tools[idx] = {"id": key, "name": fn.get("name", ""), "args": ""}
            self.emit(
                "content_block_start",
                {
                    "index": idx,
                    "content_block": {"type": "tool_use", "id": key, "name": fn.get("name", ""), "input": {}},
                },
            )
            self.started_tools.add(idx)
            self.index += 1
        idx = self.tool_index_by_key[key]
        if fn.get("name") and not self.tools[idx]["name"]:
            self.tools[idx]["name"] = fn["name"]
        chunk = fn.get("arguments") or ""
        if chunk:
            self.tools[idx]["args"] += chunk
            self.emit(
                "content_block_delta",
                {
                    "index": idx,
                    "delta": {"type": "input_json_delta", "partial_json": chunk},
                },
            )

    def finish_stream(self) -> None:
        self.close_text()
        for idx in sorted(self.started_tools):
            self.emit("content_block_stop", {"index": idx})
        stop = _map_stop(self.finish, bool(self.started_tools))
        self.emit(
            "message_delta",
            {"delta": {"stop_reason": stop, "stop_sequence": None}, "usage": self.usage},
        )
        self.emit("message_stop", {})

    def feed(self, chunk: dict[str, Any]) -> None:
        usage = chunk.get("usage")
        if usage:
            self.usage["input_tokens"] = usage.get("prompt_tokens", self.usage["input_tokens"])
            self.usage["output_tokens"] = usage.get("completion_tokens", self.usage["output_tokens"])
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                self.text(delta["content"])
            for call in delta.get("tool_calls") or []:
                self.tool_delta(call)
            if choice.get("finish_reason"):
                self.finish = choice["finish_reason"]


# --------------------------------------------------------------------------- #
# Responses API -> Chat Completions (for Codex, which dropped wire_api="chat")
# --------------------------------------------------------------------------- #

def responses_tools_to_openai(tools: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for tool in tools or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        )
    return out


def responses_input_to_messages(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    instructions = body.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": instructions})

    raw = body.get("input")
    if isinstance(raw, str):
        messages.append({"role": "user", "content": raw})
        return messages

    # Codex emits `type="message"` for prompts and history, but the harness
    # identity arrives as `type="developer"`. Both are ordinary chat roles.
    ROLE_TYPES = {"developer", "system", "user", "assistant", "tool"}
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") in ROLE_TYPES:
            item = {**item, "type": "message", "role": item["type"] if not item.get("role") else item["role"]}
        kind = item.get("type") or ("message" if "role" in item else None)
        if kind == "message":
            role = item.get("role", "user")
            raw_content = item.get("content")
            text = _text_of(raw_content)
            if not text and isinstance(raw_content, str):
                text = raw_content  # Codex may send a plain string
            if role == "assistant":
                messages.append({"role": "assistant", "content": text})
            else:
                messages.append({"role": role, "content": text})
        elif kind == "function_call":
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                            "type": "function",
                            "function": {
                                "name": item.get("name", ""),
                                "arguments": item.get("arguments") or "{}",
                            },
                        }
                    ],
                }
            )
        elif kind == "function_call_output":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.get("call_id", ""),
                    "content": str(item.get("output", "")),
                }
            )
        elif kind == "reasoning":
            continue  # provider reasoning cannot be round-tripped through chat
    return messages


def responses_to_openai(body: dict[str, Any]) -> dict[str, Any]:
    model = body.get("model") or DEFAULT_MODEL
    payload: dict[str, Any] = {
        "model": model,
        "messages": responses_input_to_messages(body),
        "max_tokens": body.get("max_output_tokens") or 8192,
        "stream": bool(body.get("stream")),
    }
    if body.get("temperature") is not None:
        payload["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        payload["top_p"] = body["top_p"]
    tools = responses_tools_to_openai(body.get("tools") or [])
    if tools:
        payload["tools"] = tools
        choice = body.get("tool_choice")
        if choice == "required":
            payload["tool_choice"] = "required"
        elif choice == "auto" or choice is None:
            payload["tool_choice"] = "auto"
        elif isinstance(choice, dict) and choice.get("name"):
            payload["tool_choice"] = {"type": "function", "function": {"name": choice["name"]}}
    return payload


class ResponsesStreamState:
    """Emits the event sequence Codex expects from /v1/responses."""

    def __init__(self, model: str, write) -> None:
        self.model = model
        self.write = write
        self.response_id = f"resp_{uuid.uuid4().hex[:20]}"
        self.created_at = int(time.time())
        self.output_index = 0
        self.text_item: str | None = None
        self.text = ""
        self.tools: dict[str, dict[str, Any]] = {}
        self.tool_order: list[str] = []
        self._tool_by_index: dict[int, str] = {}
        self.finish: str | None = None
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.seq = 0

    def emit(self, kind: str, data: dict[str, Any]) -> None:
        self.seq += 1
        payload = {"type": kind, "sequence_number": self.seq, **data}
        self.write(f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n")

    def start(self) -> None:
        self.emit(
            "response.created",
            {"response": {"id": self.response_id, "object": "response", "created_at": self.created_at, "model": self.model, "status": "in_progress", "output": []}},
        )
        self.emit("response.in_progress", {"response": {"id": self.response_id, "object": "response", "created_at": self.created_at, "model": self.model, "status": "in_progress"}})

    def text_delta(self, delta: str) -> None:
        if self.text_item is None:
            self.text_item = f"msg_{uuid.uuid4().hex[:16]}"
            self.emit(
                "response.output_item.added",
                {
                    "output_index": self.output_index,
                    "item": {"type": "message", "id": self.text_item, "role": "assistant", "content": [], "status": "in_progress"},
                },
            )
            self.emit(
                "response.content_part.added",
                {
                    "item_id": self.text_item,
                    "output_index": self.output_index,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                },
            )
        self.text += delta
        self.emit(
            "response.output_text.delta",
            {"item_id": self.text_item, "output_index": self.output_index, "content_index": 0, "delta": delta},
        )

    def close_text(self) -> None:
        if self.text_item is None:
            return
        self.emit(
            "response.output_text.done",
            {"item_id": self.text_item, "output_index": self.output_index, "content_index": 0, "text": self.text},
        )
        self.emit(
            "response.content_part.done",
            {"item_id": self.text_item, "output_index": self.output_index, "content_index": 0, "part": {"type": "output_text", "text": self.text, "annotations": []}},
        )
        self.emit(
            "response.output_item.done",
            {
                "output_index": self.output_index,
                "item": {
                    "type": "message",
                    "id": self.text_item,
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": self.text, "annotations": []}],
                },
            },
        )
        self.text_item = None
        self.output_index += 1

    def tool_delta(self, call: dict[str, Any]) -> None:
        # Some providers stream the tool name in the FIRST delta and reuse
        # index-only ids afterwards; keying on the id alone would open a second
        # `output_item.added` and Codex would reject the arguments.
        fn = call.get("function") or {}
        raw_index = call.get("index", 0)
        key = call.get("id") or f"_idx_{raw_index}"
        if key not in self.tools and raw_index is not None:
            existing = self._tool_by_index.get(raw_index)
            if existing:
                key = existing
        item_id = f"fc_{uuid.uuid4().hex[:16]}"
        if key not in self.tools:
            self.close_text()
            self.tools[key] = {"item_id": item_id, "index": self.output_index, "name": fn.get("name", ""), "args": ""}
            self._tool_by_index[raw_index] = key
            self.tool_order.append(key)
            self.output_index += 1
            self.emit(
                "response.output_item.added",
                {
                    "output_index": self.tools[key]["index"],
                    "item": {
                        "type": "function_call",
                        "id": item_id,
                        "call_id": key,
                        "name": fn.get("name", ""),
                        "arguments": "",
                        "status": "in_progress",
                    },
                },
            )
        entry = self.tools[key]
        if fn.get("name") and not entry["name"]:
            entry["name"] = fn["name"]
        chunk = fn.get("arguments") or ""
        if chunk:
            entry["args"] += chunk
            self.emit(
                "response.function_call_arguments.delta",
                {"item_id": entry["item_id"], "output_index": entry["index"], "delta": chunk},
            )

    def finish_stream(self) -> None:
        self.close_text()
        output = []
        for key in self.tool_order:
            entry = self.tools[key]
            self.emit(
                "response.function_call_arguments.done",
                {"item_id": entry["item_id"], "output_index": entry["index"], "arguments": entry["args"]},
            )
            item = {
                "type": "function_call",
                "id": entry["item_id"],
                "call_id": key,
                "name": entry["name"],
                "arguments": entry["args"],
                "status": "completed",
            }
            self.emit("response.output_item.done", {"output_index": entry["index"], "item": item})
            output.append(item)
        self.emit(
            "response.completed",
            {
                "response": {
                    "id": self.response_id,
                    "object": "response",
                    "created_at": self.created_at,
                    "model": self.model,
                    "status": "completed",
                    "output": output,
                    "usage": {
                        "input_tokens": self.usage["input_tokens"],
                        "output_tokens": self.usage["output_tokens"],
                        "total_tokens": self.usage["input_tokens"] + self.usage["output_tokens"],
                    },
                }
            },
        )

    def feed(self, chunk: dict[str, Any]) -> None:
        usage = chunk.get("usage")
        if usage:
            self.usage["input_tokens"] = usage.get("prompt_tokens", self.usage["input_tokens"])
            self.usage["output_tokens"] = usage.get("completion_tokens", self.usage["output_tokens"])
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                self.text_delta(delta["content"])
            for call in delta.get("tool_calls") or []:
                self.tool_delta(call)
            if choice.get("finish_reason"):
                self.finish = choice["finish_reason"]


# --------------------------------------------------------------------------- #
# HTTP plumbing
# --------------------------------------------------------------------------- #

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter default
        log(fmt % args)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self) -> str:
        key = self.headers.get("x-api-key") or ""
        if not key:
            auth = self.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                key = auth[7:]
        return key or API_KEY

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            # Claude Code validates the endpoint but tolerates a synthetic list.
            self._json(
                200,
                {
                    "data": [
                        {"id": DEFAULT_MODEL, "type": "model", "display_name": DEFAULT_MODEL},
                        {"id": FAST_MODEL, "type": "model", "display_name": FAST_MODEL},
                    ]
                },
            )
            return
        self._json(200, {"ok": True, "upstream": UPSTREAM})

    def do_POST(self) -> None:  # noqa: N802
        if "/responses" in self.path:
            self.handle_responses()
            return
        if "/messages" not in self.path and "/count_tokens" not in self.path:
            self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "unknown path"}})
            return
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            self._json(400, {"type": "error", "error": {"type": "invalid_request_error", "message": str(exc)}})
            return

        if "/count_tokens" in self.path:
            # Rough estimate is enough for Claude Code's budgeting.
            approx = len(json.dumps(body)) // 4
            self._json(200, {"input_tokens": approx})
            return

        payload = anthropic_to_openai(body)
        stream = payload.get("stream")
        log(
            "->",
            payload.get("model"),
            f"msgs={len(payload['messages'])}",
            f"tools={len(payload.get('tools') or [])}",
            f"stream={stream}",
            "beta_header=" + (self.headers.get("anthropic-beta") or "-"),
        )

        req = urllib.request.Request(
            f"{UPSTREAM}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self._auth()}",
                "accept": "text/event-stream" if stream else "application/json",
            },
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=int(os.environ.get("UPSTREAM_TIMEOUT", "600")))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:2000]
            log("upstream error", exc.code, detail)
            self._json(
                exc.code,
                {"type": "error", "error": {"type": "api_error", "message": f"upstream {exc.code}: {detail}"}},
            )
            return
        except Exception as exc:  # noqa: BLE001
            log("upstream failure", exc)
            self._json(502, {"type": "error", "error": {"type": "api_error", "message": str(exc)}})
            return

        if not stream:
            data = json.loads(resp.read().decode() or "{}")
            self._json(200, openai_to_anthropic(data, payload["model"]))
            return

        # No content-length and no keep-alive framing: Claude Code reads until
        # the connection closes, so the stream must be self-delimiting.
        self.close_connection = True
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("x-accel-buffering", "no")
        self.send_header("connection", "close")
        self.end_headers()

        def write(chunk: str) -> None:
            self.wfile.write(chunk.encode())
            self.wfile.flush()

        state = StreamState(payload["model"], write)
        state.start()
        try:
            for line in resp:
                line = line.decode(errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data in ("", "[DONE]"):
                    continue
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if VERBOSE:
                    log("chunk", json.dumps(chunk)[:300])
                state.feed(chunk)
        except Exception as exc:  # noqa: BLE001
            log("stream read failed", exc)
        finally:
            state.finish_stream()


    # ------------------------------------------------------------------ #
    # Codex / OpenAI Responses API
    # ------------------------------------------------------------------ #

    def handle_responses(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            self._json(400, {"error": {"message": str(exc), "type": "invalid_request_error"}})
            return

        if os.environ.get("DUMP_BODY"):
            with open(os.environ["DUMP_BODY"], "a", encoding="utf-8") as fh:
                fh.write(json.dumps(body) + "\n")
        payload = responses_to_openai(body)
        stream = payload.get("stream")
        log(
            "responses ->",
            payload.get("model"),
            f"msgs={len(payload['messages'])}",
            f"tools={len(payload.get('tools') or [])}",
            f"stream={stream}",
        )
        req = urllib.request.Request(
            f"{UPSTREAM}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self._auth()}",
                "accept": "text/event-stream" if stream else "application/json",
            },
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=int(os.environ.get("UPSTREAM_TIMEOUT", "600")))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:2000]
            log("upstream error", exc.code, detail)
            self._json(exc.code, {"error": {"message": f"upstream {exc.code}: {detail}", "type": "api_error"}})
            return
        except Exception as exc:  # noqa: BLE001
            self._json(502, {"error": {"message": str(exc), "type": "api_error"}})
            return

        if not stream:
            data = json.loads(resp.read().decode() or "{}")
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            output = []
            text = message.get("content")
            if text:
                output.append(
                    {
                        "type": "message",
                        "id": f"msg_{uuid.uuid4().hex[:16]}",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": text, "annotations": []}],
                    }
                )
            for call in message.get("tool_calls") or []:
                fn = call.get("function") or {}
                output.append(
                    {
                        "type": "function_call",
                        "id": f"fc_{uuid.uuid4().hex[:16]}",
                        "call_id": call.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                        "name": fn.get("name", ""),
                        "arguments": fn.get("arguments") or "{}",
                        "status": "completed",
                    }
                )
            usage = data.get("usage") or {}
            self._json(
                200,
                {
                    "id": data.get("id") or f"resp_{uuid.uuid4().hex[:20]}",
                    "object": "response",
                    "created_at": int(time.time()),
                    "model": payload["model"],
                    "status": "completed",
                    "output": output,
                    "usage": {
                        "input_tokens": usage.get("prompt_tokens", 0),
                        "output_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                },
            )
            return

        self.close_connection = True
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("connection", "close")
        self.end_headers()

        def write(chunk: str) -> None:
            self.wfile.write(chunk.encode())
            self.wfile.flush()

        state = ResponsesStreamState(payload["model"], write)
        state.start()
        try:
            for line in resp:
                text = line.decode(errors="replace").strip()
                if not text.startswith("data:"):
                    continue
                data = text[5:].strip()
                if data in ("", "[DONE]"):
                    continue
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                state.feed(chunk)
        except Exception as exc:  # noqa: BLE001
            log("responses stream read failed", exc)
        finally:
            state.finish_stream()


def main() -> int:
    if not DEFAULT_MODEL:
        print("MODEL is required (e.g. MODEL=cn:glm-5.3)", file=sys.stderr)
        return 2
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"anthropic-shim listening on http://127.0.0.1:{PORT} -> {UPSTREAM} (model {DEFAULT_MODEL})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
