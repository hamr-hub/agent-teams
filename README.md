# agent-teams

> One engineering team, three CLIs. A Tech Lead plus 12 specialist agents with non-overlapping
> ownership, generated from a single YAML for **MiniMax Code (MCode)**, **Claude Code**, and **Codex**.

[中文说明](README.zh-CN.md) · MIT

```
$ mcode exec "state your role"
I'm MCode, the Tech Lead of a senior engineering team; 17 teammates are delegatable.

$ claude --agent architect -p "state your role"
I'm the Architect — module boundaries, contracts, state machines, trade-offs (decisions only).

$ codex exec "$(role architect)" "state your role"
ROLE=architect
```

## Why

All three CLIs ship a generalist default. That is fine until work spans disciplines: architecture,
API contracts, schema design, security, performance, and test strategy collapse into one role with one
set of instincts, and nobody owns "must not".

This repo adds the missing specializations, and it does so *natively* per tool — MCode Custom Agents,
Claude Code subagents, Codex role instructions — instead of pretending one file format fits all three.

## The team

| agent | Role | Owns | Must not |
|---|---|---|---|
| `architect` | Architect | module boundaries, contracts, state machines, trade-offs | write production code |
| `product-owner` | Product Owner | user stories, acceptance criteria, scope, priority | design or implement |
| `ui-ux-designer` | UI/UX Designer | flows, interaction states, accessibility, copy | write frontend code |
| `frontend-engineer` | Frontend Engineer | views, components, state, routing, styling | backend, schema, build infra |
| `backend-engineer` | Backend Engineer | domain logic, APIs, persistence, transactions | frontend or infra |
| `api-designer` | API Designer | contracts, versioning, compatibility, error model | business logic |
| `data-engineer` | Data Engineer | schema, migrations, indexes, backfills | API surface or app code |
| `sre-engineer` | SRE Engineer | build, release, CI, IaC, observability | product features |
| `security-engineer` | Security Engineer | threat model, authn/authz, secrets, dependencies | feature implementation |
| `qa-engineer` | QA Engineer | test strategy, suites, regression, reproduction | fixing product code quietly |
| `code-reviewer` | Code Reviewer | correctness, conventions, error paths, maintainability | rewriting the change |
| `performance-engineer` | Performance Engineer | profiling, budgets, caching, concurrency | broad refactors |
| `tech-writer` | Tech Writer | READMEs, API docs, changelogs, runbooks | documenting unimplemented behaviour |

Every role carries an explicit **Boundaries** section. That is the part that keeps lanes from colliding;
a duty list alone drifts.

## Layout

```
team.yaml            # single source of truth: roster, duties, boundaries, deliverables
capabilities.yaml    # tool mapping per tier (read / write) per tool
tools/generate.py    # regenerates all three artefact sets; --check for CI
mcode/               # MiniMax Code: Custom Agents + .builtin overlay + installer
claude/              # Claude Code: subagents + installer + gateway settings
codex/               # Codex: role TOMLs + roster index + installer
proxy/               # single-file bridge: Anthropic Messages + Responses -> Chat Completions
```

| Tool | It gets | Native mechanism |
|---|---|---|
| MCode | `~/.minimax/agents/<name>/agent.md` (13 Custom Agents) + a Tech Lead overlay in `.builtin` | Custom Agent roster + built-in override |
| Claude Code | `~/.claude/agents/<name>.md` (13 subagents) | `--agent` / Agent tool `subagent_type` |
| Codex | `~/.codex/team/agents/<name>.toml` + roster block in `~/.codex/AGENTS.md` | multi-agent tools with role instructions |

## Install

```bash
git clone https://github.com/hamr-hub/agent-teams.git
cd agent-teams

./mcode/install.sh      # MiniMax Code
./claude/install.sh     # Claude Code
./codex/install.sh      # Codex
```

Each installer is idempotent, additive, and backs up whatever it overwrites
(`<dir>/backup-team-agents-<timestamp>/`). All accept `--dry-run`.

## Local gateway (no vendor subscription)

If your models sit behind an OpenAI-compatible gateway, start the shim and point the CLIs at it:

```bash
UPSTREAM=http://localhost:7863 MODEL=cn:glm-5.3-flash \
UPSTREAM_API_KEY=<key> PORT=8787 python3 proxy/claude_gateway_proxy.py
```

Claude Code → `ANTHROPIC_BASE_URL=http://localhost:8787`; Codex → a provider with
`base_url="http://localhost:8787/v1"`, `wire_api="responses"`. Details in [`proxy/README.md`](proxy/README.md).

## Customize

Edit `team.yaml`, then:

```bash
python3 tools/generate.py           # regenerate mcode/, claude/, codex/
python3 tools/generate.py --check   # fail if artefacts drifted (use in CI)
```

Add an agent by appending one block to `team.yaml`; it appears in all three tools on the next run.

## Verified

| Check | Result |
|---|---|
| MCode — roster visible | lead self-describes as Tech Lead, lists all delegates |
| MCode — Custom Agent call | `task agent_name='architect'` → `ROLE=architect` (was `Unknown agent`) |
| MCode — parallel lanes | `backend-engineer` → `api/spec.md`, `tech-writer` → `README.md`, disjoint writes |
| MCode — both prompt paths | `--prompt-mode tui` and `coding` both show the Tech Lead identity |
| Claude Code — agent | `claude --agent architect -p ...` → `ROLE=architect` |
| Claude Code — delegation | Agent tool `subagent_type: qa-engineer` returned its own answer |
| Codex — role text | `codex exec "<architect role>"` → `ROLE=architect` |
| Codex — tool calls | created `hello.txt` through `apply_patch` over the shim |
| Shim — both dialects | non-stream and stream verified for Messages and Responses |

## Known limits

- **Codex has no agent registry.** Roles are instruction text passed at spawn time; enforcement is
  instruction + sandbox, not a declared tool allowlist.
- **MCode prohibits `features:` in Custom Agents** (built-in-mirror-only key). The generator omits it.
- **Upgrades reset vendor files.** Re-run the relevant installer after `npm i -g @minimax-ai/code`, a
  Claude Code update, or a Codex update.
- **Claude Code settings win over the shell.** A `~/.claude/settings.json` `env` block overrides
  exported variables; pass `--settings` for the gateway profile.
- The proxy is a compatibility bridge, not a production gateway: no auth, no rate limiting, no retries.

## License

MIT — see [LICENSE](LICENSE). Unofficial community customization. MiniMax Code, Claude Code, and Codex
are their vendors' products; `proxy/` and the generators here are original code.
