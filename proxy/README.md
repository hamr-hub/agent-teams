# protocol shim — run Claude Code / Codex against an OpenAI-only gateway

Many self-hosted model gateways speak **OpenAI Chat Completions** and nothing else. The vendors'
CLIs do not:

| CLI | Speaks | Fails against a chat-only gateway with |
|---|---|---|
| Claude Code | Anthropic Messages (`/v1/messages`) | `404 page not found`, then `There's an issue with the selected model` |
| Codex | OpenAI Responses (`/v1/responses`) | `wire_api = "chat" is no longer supported`, or `404` on `/v1/responses` |

`claude_gateway_proxy.py` is a single-file, dependency-free bridge:

```
Claude Code --/v1/messages (Anthropic SSE)--┐
                                           ├─> proxy --/v1/chat/completions--> gateway
Codex       --/v1/responses (Responses SSE)┘
```

## Run

```bash
UPSTREAM=http://localhost:7863 \
MODEL=cn:glm-5.3-flash \
UPSTREAM_API_KEY=<gateway key> \
PORT=8787 \
python3 proxy/claude_gateway_proxy.py
```

`VERBOSE=1` logs the translated request shape and each upstream chunk; `DUMP_BODY=/tmp/bodies.jsonl`
appends every inbound request body for debugging.

## What is translated

- Anthropic `system` + `messages` → OpenAI `messages`, including `tool_use` / `tool_result` mapping in
  both directions (`stop_reason: tool_use` on the way back).
- Responses `input[]` → OpenAI `messages`: `type:"developer"` and `type:"summary"` items are treated as
  chat roles, `function_call` / `function_call_output` become `tool_calls` / `role:"tool"`.
- Streaming SSE for both dialects, with the event sequence each CLI expects:
  - Anthropic: `message_start` → `content_block_start/delta/stop` → `message_delta` → `message_stop`
  - Responses: `response.created` → `response.output_item.added` → `response.output_text.delta` /
    `response.function_call_arguments.delta` → `response.output_item.done` → `response.completed`
- Reasoning fields (`reasoning_content`, `reasoning`) are dropped from the text stream; neither CLI can
  round-trip an unsigned thinking block back to the provider.

## Two bugs that cost the most time

Both are recorded here because they present as "the model ignores everything and answers nonsense":

1. **Keep-alive framing on the SSE response.** With `connection: keep-alive` and no `content-length`,
   the CLI waits forever for a stream end and silently times out. The proxy sets
   `connection: close` and `close_connection = True`.
2. **`input_text` blocks were not counted as text.** Anthropic uses `{"type":"text"}` while Responses
   uses `{"type":"input_text"}` / `output_text`. Flattening only `text` produced *empty* messages, so the
   provider replied "your message came through empty". `TEXT_BLOCK_TYPES` now covers both.

A third, Codex-only: providers stream the tool name in the **first** delta and reuse index-only ids
afterwards. Keying tool accumulation on the id alone opened a second `output_item.added`, and Codex
rejected the arguments (`missing field 'cmd'`). Tool entries are now keyed by stream index.

## Verify

```bash
# Anthropic path
curl -s http://localhost:8787/v1/messages \
  -H "x-api-key: $KEY" -H "content-type: application/json" \
  -d '{"model":"m","max_tokens":64,"messages":[{"role":"user","content":"Say PROXY_OK"}]}'

# Responses path
curl -s http://localhost:8787/v1/responses \
  -H "authorization: Bearer $KEY" -H "content-type: application/json" \
  -d '{"model":"m","input":"Say RESP_OK","max_output_tokens":64}'
```

Measured end-to-end on this machine: Claude Code ran `--agent architect` and delegated to
`subagent_type: qa-engineer`; Codex created a file through tool calls. See each tool's README.
