# Design notes

Everything here was verified against the MiniMax Code source (`packages/local-runtime-v2`) and the
installed npm bundle, then confirmed by running the CLI. Pinned to the shipped behaviour of
`@minimax-ai/code` 0.6.x — re-check after major upgrades.

## Upstream facts

| Fact | Evidence |
|---|---|
| The built-in roster is a fixed list: `mavis`, `explore`, `worker`, `verifier`. Adding a *built-in* agent requires shipping assets, not configuration. | `packages/local-runtime-v2/assets/agents/builtin-agents.json` |
| Identity is composed from four layers: persona → core prompt → `_default` base (`prompt-base-all` / `prompt-base-worker`) → session layer (`prompt-session-root` / `prompt-session-branch`). | `_v2/AGENT_CONTEXT.md.hbs`, `_default/*`, `definitions.ts#toSurfaceRenderInput` |
| Global instructions are read from `<dataDir>/AGENTS.md` (32 KB cap) and injected with a preamble stating the instructions **OVERRIDE default behaviour**. | `static-prompt-reader.ts#readGlobalInstructions`, `prompt-blocks.ts#INSTRUCTIONS_CONTEXT_PREAMBLE` |
| Project instructions are read from the workspace, `CLAUDE.md` first, then `AGENTS.md` (32 KB cap). | `static-prompt-reader.ts#readProjectInstructions` |
| Custom Agents are the only extensible roster: one directory per agent under `<dataDir>/agents/`, containing `agent.md`. A directory only joins the roster if its `agent.md` parses. | `agent-files.ts#listCanonicalCustomAgents`, `agent.repository.ts#list` |
| Custom `agent.md` accepts `name`, `description`, `model`, `effort`, `tools`, `disallowedTools`, `mcpServers`, `skills`, `x-mavis`. Any other key becomes an `unsupported_agent_field` diagnostic and is dropped. | `canonical-agent-config.ts#KNOWN_FIELDS` |
| `features` (`mavis`/`delegation`/`webSearch`) and `builtinTools` are legal only in the runtime-owned `.builtin` mirror. | `BUILTIN_KNOWN_FIELDS` |
| `x-mavis` accepts `displayName`, `avatar`, `contextWindow`, `maxOutputTokens`, `defaultWorkspaceDir`, `extensionSkills`. | `KNOWN_MAVIS_FIELDS` |
| Omitting `tools` inherits the full inventory; `tools: []` disables everything; an override can only intersect, never add. | `agent-capabilities.ts#AgentCapabilityConfig`, `definitions.ts#resolveCanonicalCapabilities` |
| Only the three canonical sub-roles (`explore`/`worker`/`verifier`) run as task children without `mavis`; Custom Agents are unaffected. | `validation.ts#applyBuiltinSubagentTaskChildCeiling` |
| A Custom Agent may reuse a reserved name; `agent:<name>` selects it exactly. | `subagent-roles.ts#toAgentRequestRef` |
| Model/effort are per-agent overrides; an omitted model inherits. | `canonical-agent-config.ts`, `config-document.ts` |

## Decisions that follow

### 1. Specialists are Custom Agents, not built-ins

There is no supported way to add a built-in agent without shipping runtime assets, so each
specialist is a Custom Agent. This also means no upgrade can silently replace them.

### 2. No `features:` in the Custom Agent files

The first draft of this pack put `features: {mavis, delegation, webSearch}` in every Custom Agent.
That is a built-in-mirror-only key: for a Custom Agent it produces an `unsupported_agent_field`
diagnostic and is ignored. It was removed everywhere. Custom Agents already retain `mavis`
(including child-session messaging), which is what the roster needs.

### 3. The Tech Lead identity lives in the `.builtin` overlay

`<dataDir>/agents/.builtin/mavis/agent.md` is the shipped override mechanism for a built-in agent:
the runtime materialises its own canonical mirror there and preserves user edits. Only three bullets
are rewritten — the primary persona in each *coding* variant (`mode.coding`, `mode.tui`, and the
`persona.enabled` inline identity) — plus one inserted `# Your Engineering Team` section.

`mode.work` (the Desktop research/deliverable mode) is deliberately untouched. That persona is not
an engineering lead, and calling it one would produce confidently wrong routing in a mode that has
no code to route.

### 4. The operating contract lives in `<dataDir>/AGENTS.md`

It is the strongest injection layer, shared by CLI and Desktop, and inherited by every Agent including
delegated task children. That makes it the right home for the routing table and the seven delegation
rules — one place to change policy rather than fourteen `agent.md` files.

### 5. `Boundaries` is the load-bearing section

A role with only a duty description drifts into neighbouring work. Every specialist therefore carries
an explicit *must not* list (the `Must not` column and the `Boundaries` heading in each file), matching
the upstream convention that `explore` and `verifier` gate the deliverable type rather than the tool list.

### 6. Read-only roles get read-only tools

`architect`, `product-owner`, `security-engineer`, `performance-engineer` and `code-reviewer` receive
`read`/`grep`/`glob`/`bash` plus `task_*` control tools, never `write`/`edit`. This makes "decisions
only" mechanically true instead of merely requested — matching upstream's approach of encoding role
limits in capabilities rather than prose alone.

### 7. `patch-identity.py` is opt-in and idempotent

The npm bundle keeps two independent render paths (`assets/agents/mavis/system-prompt.md.hbs` and
`_v2/{coding,tui}/SYSTEM.md.hbs`). The overlay covers the data dir, but a user who wants the packaged
templates consistent can apply the same three sentence-level replacements with a script that backs up
every file, prints a dry run by default, and touches only the *coding* identity.

## Verification performed

- Team visibility: the primary agent self-describes as Tech Lead and enumerates all 17 delegatable teammates.
- Custom agent resolution: `task agent_name='architect'` previously failed with `Unknown agent: architect`;
  after install it returns `ROLE=architect` with a real design answer. `code-reviewer` likewise.
- Both prompt paths: `--prompt-mode tui` and `--prompt-mode coding` both show the Tech Lead identity.
- Two-lane parallel delegation: `backend-engineer` writing `api/spec.md` and `tech-writer` appending to
  `README.md` in one message, with disjoint ownership — both files byte-verified, no cross-lane writes.
- Fresh-profile drill: `install.sh --data-dir /tmp/<fresh>` produced 13 agent directories, the global
  contract, and the `.builtin` overlay.
- Field validation: all 13 files parse against the documented allowlist, `name` matches the directory,
  no `features` key present.

Not verified: the Desktop GUI itself (not launchable from the CLI on the authoring machine). The claim
that Desktop shares these agents rests on the shared data dir and the shared `.builtin`/`AGENTS.md`
resolver, not on a GUI test.

## Known limits

- Upgrades that rewrite the bundled data dir can reset the `.builtin` overlay; re-run `install.sh`.
- `npm i -g @minimax-ai/code` replaces packaged templates; re-run `patch-identity.py --apply` if used.
- Custom Agents cannot be given `features`, so behaviours gated by that flag (e.g. `delegation`-driven
  prompt sections) follow the runtime default rather than per-agent policy.
- Adding a specialist does not change the `task` tool's built-in role directory text; Custom Agents
  are discoverable by name and listed in `AGENTS.md`, which is how the Tech Lead routes to them.
