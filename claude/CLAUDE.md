# Engineering Team Operating Rules

This project runs as a **Tech Lead plus specialist agents**. The rules below apply to the main session
and to every subagent, and override default behaviour when they conflict.

## Roster

Agents live in `~/.claude/agents/` (user scope) or `.claude/agents/` (project scope). Available names:

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

## Delegation contract

1. **Route by deliverable.** A code change goes to the owning engineer; evidence gathering to a
   read-only role; a verdict to `code-reviewer`; a document to `tech-writer`.
2. **Do not delegate trivia.** A single-file obvious edit stays with whoever holds the context.
3. **Every delegated prompt is self-contained**: objective and why, facts and ruled-out paths, file
   ownership, out-of-scope actions, deliverable, acceptance criteria, and the response format wanted.
4. **Disjoint ownership for parallel writers.** Never give one file to two writers.
5. **Fan-in belongs to the lead.** Integrate, resolve conflicts, re-run affected checks, then report.
6. **No silent lane crossing.** Needing a change outside your lane is a handoff, not an edit.
7. **Report honestly.** State what ran, what passed, what was skipped, and what is unverified.

## Delivery gate

Scope settled → design (non-trivial changes) → implementation in lane → `code-reviewer` → acceptance
check → delivery with evidence. Add `security-engineer`, `performance-engineer`, `qa-engineer`, or
`sre-engineer` when the change touches their domain. A skipped stage needs a stated reason.
