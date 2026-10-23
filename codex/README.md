# Codex — engineering-team agents

Codex has no per-agent definition files. Its extensibility is **multi-agent orchestration**: the main
agent can spawn sub-agents, and the delegated instructions are free text. This directory encodes the
same team from [`team.yaml`](../team.yaml) as one TOML file per role, plus an installer that registers
them with the local app-server so they are discoverable.

## What Codex actually supports

Checked against `codex-cli 0.163.0`:

| Fact | Where |
|---|---|
| No "agent directory". There is no `~/.codex/agents/`. | filesystem, `codex --help` |
| Multi-agent is a **feature flag**, on by default: `multi_agent` (stable) and `multi_agent_v2` | `codex features list` |
| The multi-agent surface is a tool set: `spawnAgent`, `sendInput`, `resumeAgent`, `wait`, `closeAgent`, `sendMessage`, `followupTask`, `interruptAgent`, `listAgents` | `codex app-server generate-json-schema --experimental` → `CollabAgentTool` |
| Delegation policy is configurable per thread: `explicitRequestOnly` \| `proactive` \| `{custom: "..."}` | schema `MultiAgentMode` |
| A spawned thread records `agentRole` and `agentNickname` | schema `Thread` |
| Per-session persona comes from instructions: `developer_instructions`, `AGENTS.md`, or the prompt | `codex debug prompt-input` |
| `wire_api = "chat"` was removed; providers must speak the Responses API | error from `codex exec` |

Consequence: the team is expressed as **role instructions**, not as registered agents. The lead reads
`codex/agents/index.md` to learn who exists, and passes `codex/agents/<name>.toml`'s `instructions.text`
verbatim when it spawns a sub-agent.

## Install

```bash
./codex/install.sh            # -> ~/.codex/team/agents/*.toml + a pointer block in ~/.codex/AGENTS.md
./codex/install.sh --dry-run
```

The installer never rewrites `~/.codex/config.toml`; it only appends a delimited pointer block to
`~/.codex/AGENTS.md` so the lead knows the roster and where the instructions live.

## Use it

Point a session at a role (one-shot):

```bash
python3 - <<'PY' > /tmp/role.txt
import tomllib
d = tomllib.load(open('/Users/hyx/.codex/team/agents/architect.toml','rb'))
print(d['instructions']['text'])
PY

codex exec -C /path/to/repo "$(cat /tmp/role.txt)
Task: split our TODO CLI into modules. Reply ROLE=architect."
```

Or let the lead spawn sub-agents itself (multi-agent is on by default):

```bash
codex -c 'multi_agent_mode="explicitRequestOnly"' \
  "Spawn an architect sub-agent with the instructions in ~/.codex/team/agents/architect.toml, ask it for a layering decision, then summarize."
```

## Notes and limits

- Codex's own prompt layer is a *developer message* the harness sends; role text passed in the user
  prompt is respected but competes with it. Put durable policy in `~/.codex/AGENTS.md` (user scope) or
  the repo's `AGENTS.md`, and keep role text about the specific deliverable.
- There is no `tools` allowlist per role. Read-only roles are enforced by instruction plus Codex's
  sandbox (`--sandbox read-only`) when you spawn them; set that on the sub-session.
- If your models live behind an OpenAI-compatible **Chat Completions** gateway, Codex cannot talk to
  it directly (it requires the Responses API). Use [`proxy/`](../proxy/), which exposes
  `/v1/responses` for exactly this case.
- Verification setup used here:

  ```bash
  export GATEWAY_API_KEY=<key>
  codex exec -c 'model="cn:glm-5.3-flash"' -c 'model_provider="gw"' \
    -c 'model_providers.gw={name="gateway",base_url="http://localhost:8787/v1",wire_api="responses",env_key="GATEWAY_API_KEY"}' \
    -C /tmp/scratch "Create hello.txt containing OK, then say DONE."
  # -> hello.txt created, tool calls round-tripped through the shim
  ```
