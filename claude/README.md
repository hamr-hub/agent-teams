# Claude Code — engineering-team agents

Claude Code has first-class custom agents (subagents). This directory installs the same team that
`mcode/` installs into MiniMax Code, generated from the shared [`team.yaml`](../team.yaml).

## What Claude Code supports

| Fact | Where |
|---|---|
| Subagents are markdown files with YAML frontmatter in `~/.claude/agents/` (user) or `.claude/agents/` (project) | `claude --help`, official docs |
| Frontmatter keys include `name`, `description`, `tools`, `model` | same |
| `--agent <name>` runs the whole session as that agent | `claude --agent architect -p "..."` |
| The Agent/Task tool delegates to a named `subagent_type` from the same roster | verified below |
| Ad-hoc agents can be injected per invocation with `--agents file.json` | `claude --agents ./agents.json` |
| `~/.claude/CLAUDE.md` is the user-scope instruction file | same |

There is no limitation to work around here — unlike MCode, Claude Code's subagent model is exactly
the shape this team needs.

## Install

```bash
./claude/install.sh              # -> ~/.claude/agents/*.md
./claude/install.sh --project    # -> ./.claude/agents/*.md (repo scope)
./claude/install.sh --dry-run
```

## Verify

```bash
# the main session runs as a specialist
claude --agent architect -p "state your role in one line"

# delegation to a named subagent
claude -p "Use the Task tool with subagent_type 'qa-engineer' to ask 'what do you own?' and report its reply verbatim."
```

Measured on this machine (Claude Code 2.1.302, model behind the local gateway):

```
$ claude --agent architect -p "State your role in one line."
I'm the Architect — module boundaries, interface/data contracts, state machines,
and technology trade-offs (decisions only, no code).

$ claude -p "Use the Task tool with subagent_type 'qa-engineer' ..."
The qa-engineer agent replied verbatim:
> I own test strategy and suites: turning acceptance criteria and interfaces into
  deterministic unit/integration tests, covering boundary, error, concurrency,
  idempotency, and permission edges — plus reproducing defects minimally, without
  quietly fixing product code to go green.
```

## Using a local gateway instead of an Anthropic subscription

Claude Code speaks only the Anthropic Messages API. If your models live behind an
OpenAI-compatible gateway (as this machine's `localhost:7863` does), run the shim in
[`proxy/`](../proxy/) and point Claude Code at it:

```bash
# terminal 1
UPSTREAM=http://localhost:7863 MODEL=cn:glm-5.3-flash \
UPSTREAM_API_KEY=<gateway key> PORT=8787 python3 proxy/claude_gateway_proxy.py

# terminal 2 — settings file, because env vars in settings.json win over the shell
cat > ~/.claude/team-gateway.settings.json <<'EOF'
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8787",
    "ANTHROPIC_AUTH_TOKEN": "<gateway key>",
    "ANTHROPIC_MODEL": "cn:glm-5.3-flash",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "cn:glm-5.3-flash",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "cn:glm-5.3-flash",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "cn:glm-5.3-flash",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": 1
  }
}
EOF

claude --settings ~/.claude/team-gateway.settings.json --agent architect -p "hello"
```

Pass the settings with `--settings` rather than exporting shell variables: an existing
`~/.claude/settings.json` `env` block takes precedence over the process environment, which
silently sends requests to the wrong provider.

## Notes and limits

- Subagent frontmatter has no per-agent sandbox or permission scope beyond `tools`; keep read-only
  roles genuinely read-only by omitting `Write`/`Edit`, as the generated files do.
- `model: inherit` keeps subagents on the session model. Pin a cheaper model per agent by editing
  `claude_models` in [`capabilities.yaml`](../capabilities.yaml) and regenerating.
- Regenerate after editing `team.yaml`: `python3 tools/generate.py`.
