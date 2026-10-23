# Codex agent roster

Generated from `team.yaml`. One TOML per role in this directory; the role text lives in
`instructions.text`. Pass it verbatim when spawning a sub-agent.

| agent | role | tier | owns |
| --- | --- | --- | --- |
| `architect` | Architect | read | System architect for module boundaries, interface and data contracts, state machines, and technology trade-offs; decisions only, no code |
| `product-owner` | Product Owner | read | Requirements owner for user stories, acceptance criteria, scope boundaries, and priority; no design or implementation |
| `ui-ux-designer` | UI/UX Designer | read | Product designer for user flows, interaction states, accessibility, design tokens, and copy; no frontend code |
| `frontend-engineer` | Frontend Engineer | write | Frontend engineer for views, components, state, routing, styling, and client-side performance |
| `backend-engineer` | Backend Engineer | write | Backend engineer for domain logic, APIs, persistence access, transactions, and idempotency |
| `api-designer` | API Designer | write | API contract engineer for request/response schemas, versioning, compatibility, error model, and generated types |
| `data-engineer` | Data Engineer | write | Data engineer for schema and migrations, indexes, query plans, backfills, and analytics pipelines |
| `sre-engineer` | SRE Engineer | write | Platform/SRE engineer for build and release pipeline, CI, containers, IaC, observability, and runtime config |
| `security-engineer` | Security Engineer | read | Security engineer for threat modeling, authn/authz, input boundaries, secret handling, and dependency risk |
| `qa-engineer` | QA Engineer | write | Test engineer for test strategy, unit and integration suites, regression coverage, and defect reproduction |
| `code-reviewer` | Code Reviewer | read | Code reviewer for correctness, conventions, error paths, and maintainability of a change; findings only, no fixes |
| `performance-engineer` | Performance Engineer | read | Performance engineer for profiling, hot paths, latency and memory budgets, caching, and concurrency limits |
| `tech-writer` | Tech Writer | write | Documentation engineer for READMEs, API and usage docs, changelogs, migration notes, and runbooks |

## Delegation contract

1. Route by deliverable: code changes to the owning engineer, evidence to a read-only role,
   verdicts to `code-reviewer`, documents to `tech-writer`.
2. Do not delegate trivia.
3. Every delegated brief is self-contained: objective, facts and ruled-out paths, file
   ownership, out-of-scope actions, deliverable, acceptance criteria, output format.
4. Parallel writers must own disjoint files.
5. Fan-in and the final answer stay with the lead.
6. Report what ran, what passed, and what is unverified.
