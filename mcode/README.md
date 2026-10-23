# MiniMax Code (MCode) — engineering-team agents

MCode ships four built-in agents (`mavis` + `explore`/`worker`/`verifier`). This directory adds the
team from [`team.yaml`](../team.yaml) as **Custom Agents** and rewrites the primary agent's coding
identity so it behaves as a Tech Lead.

Full design rationale and upstream evidence: [`docs/design-notes.md`](docs/design-notes.md).

## Install

```bash
./mcode/install.sh                 # -> ~/.minimax
./mcode/install.sh --data-dir DIR  # custom profile
./mcode/install.sh --dry-run
```

What it writes (all additive, all backed up first):

| Path | Contents |
|---|---|
| `<dataDir>/agents/<name>/agent.md` | 13 Custom Agents |
| `<dataDir>/agents/.builtin/mavis/agent.md` | Tech Lead overlay for the built-in primary |
| `<dataDir>/AGENTS.md` | Global team contract (strongest injection layer, shared by CLI + Desktop) |

Optional, to also align the npm-bundled prompt templates:

```bash
python3 mcode/patch-identity.py --apply
```

## Verify

```bash
mcode exec --prompt-mode tui "List the agent_names you can delegate to"
mcode exec --prompt-mode tui --permission full \
  "Call task once with agent_name='architect' and prompt 'One line: ROLE=architect.'"
```

## Migrating

Copy this repo to the new machine and run `./mcode/install.sh` after `mcode login`.
If you migrate the whole `~/.minimax` directory, nothing extra is needed — the Custom Agents and the
overlay already live inside it. Re-run the installer after every `npm i -g @minimax-ai/code` upgrade.
