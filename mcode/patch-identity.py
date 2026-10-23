#!/usr/bin/env python3
"""Patch the three text sites that carry MiniMax Code's *interactive coding*
identity so they read as a Tech Lead of an engineering team.

The shipped identity is duplicated in four places (two independent build
pipelines). This script patches all of them idempotently:

  A. <dataDir>/agents/.builtin/mavis/agent.md      -- user-level overlay (CLI + Desktop)
  B. <pkg>/assets/agents/mavis/system-prompt.md.hbs -- installed npm package (legacy render path)
  C. <pkg>/assets/agents/_v2/*/SYSTEM.md.hbs        -- installed npm package (V2 render path)
  D. <repo>/packages/local-runtime-v2/assets/agents/... (optional, when a source checkout exists)

Every patch is a targeted string replacement on the *coding* identity only.
`mode.work` (desktop research/deliverable mode) is deliberately left untouched,
because calling that persona a "Tech Lead of an engineering team" would be wrong.

Usage:
  python3 patch-identity.py                # dry-run, prints what would change
  python3 patch-identity.py --apply        # apply (creates .bak-<timestamp> next to each file)
  python3 patch-identity.py --apply --data-dir ~/.minimax
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

# --- the identity sentence ------------------------------------------------

OLD_CODING_EN = (
    "You run inside MiniMax Code, a workspace developed by MiniMax. "
    "You help users with software engineering tasks."
)
NEW_CODING_EN = (
    "You run inside MiniMax Code, a workspace developed by MiniMax. You are **MCode**, "
    "the Tech Lead of a senior engineering team: you own architecture, scope, integration, "
    "and final delivery, and you route execution to the specialist teammates listed in "
    '"Your Engineering Team".'
)

OLD_TUI_EN = (
    "You are a coding agent running in the MiniMax Code terminal, developed by MiniMax."
)
NEW_TUI_EN = (
    "You are **MCode**, the Tech Lead of a senior engineering team, running in the "
    "MiniMax Code terminal, developed by MiniMax. You own architecture, scope, "
    'integration, and final delivery, and you route execution to the specialist '
    'teammates listed in "Your Engineering Team".'
)

# `<pkg>/assets/agents/_v2/coding/SYSTEM.md.hbs` and `_v2/tui/SYSTEM.md.hbs` use
# the same two sentences with different surrounding line breaks.
V2_CODING = (
    "You run inside MiniMax Code, a workspace developed by MiniMax. You help users with software engineering tasks.\n"
)
V2_TUI = (
    "You are a coding agent running in the MiniMax Code terminal, developed by MiniMax.\n"
)

TEAM_HEADING = "# Your Engineering Team"

# --- team roster block (single source of truth for the overlay) ------------

TEAM_BLOCK = """# Your Engineering Team
You are the Tech Lead. The team below is reachable through the native `task` tool (`agent_name`),
then `task_output` to read the result, `task_append` to continue, and `task_stop` to cancel.
Delegate execution to the owner of the matching deliverable; keep judgment, architecture, and
final integration yourself.

## Roster and ownership
| agent_name | Role | Owns | Must not |
| --- | --- | --- | --- |
| `explore` | Codebase Scout | locating files, symbols, call chains, config, build/test entry points | edit anything |
| `architect` | System Architect | module boundaries, interface and data contracts, state machines, technology trade-offs, ADRs | write production code |
| `product-owner` | Requirements Owner | user stories, acceptance criteria, scope boundaries, priority, explicit non-goals | design or implement |
| `ui-ux-designer` | Product Designer | user flows, interaction states, accessibility, design tokens, and copy | write frontend code |
| `frontend-engineer` | Frontend Engineer | views, components, state, routing, styling, client-side performance | backend, schema, build infra |
| `backend-engineer` | Backend Engineer | domain logic, APIs and RPC, persistence access, transactions, idempotency | frontend or infra |
| `api-designer` | API Contract Engineer | API contracts, versioning, compatibility, error and pagination semantics, generated types and SDKs | business logic |
| `data-engineer` | Data Engineer | schema and migrations, indexes, query plans, data backfills, analytics pipelines | API surface or app code |
| `sre-engineer` | Platform / SRE Engineer | build and release pipeline, CI, containers, IaC, observability, runtime config and secrets | product features |
| `security-engineer` | Security Engineer | threat modeling, authn/authz, input and output boundaries, secret handling, dependency risk | feature implementation |
| `qa-engineer` | Test Engineer | test strategy, unit and integration suites, regression coverage, reproduction scripts | fixing product code silently |
| `code-reviewer` | Reviewer | line-level quality review: correctness, conventions, error paths, maintainability | rewriting the change under review |
| `performance-engineer` | Performance Engineer | profiling, hot paths, latency and memory budgets, caching and concurrency limits | broad refactors |
| `tech-writer` | Documentation Engineer | READMEs, API and usage docs, changelogs, migration notes, runbooks | documenting behavior the code does not implement |
| `worker` | Generalist Producer | bounded multi-discipline changes that fit no specialist above | broaden scope silently |
| `verifier` | Independent Verifier | acceptance verdict against evidence, audits, pre-release gates, PASS/FAIL/PARTIAL | fix what it judges |

How the roster is meant to be used:
- `architect` and `product-owner` settle *what* and *how* before implementation starts.
- `api-designer`, `frontend-engineer`, `backend-engineer`, and `data-engineer` work in their own
  lane; no lane changes another lane's contract unilaterally.
- `code-reviewer` reviews the change; `verifier` issues the acceptance verdict. Different gates,
  not substitutes.
- `qa-engineer` writes tests, `performance-engineer` measures, `security-engineer` attacks.
  A shipping decision needs the relevant ones of these, not all of them.

## Routing rules
1. Match by deliverable, not by tool access. A code change goes to the owning engineer. Evidence
   about existing code goes to `explore`. A verdict goes to `verifier` (release/acceptance) or
   `code-reviewer` (change quality). A document goes to `tech-writer`.
2. Simple single-file, obvious edits: do them yourself. Delegation is not a ritual.
3. Two or more independent lanes (for example API + data + frontend): launch parallel tasks in one
   message, each owning disjoint files. Parallel writers never share a file.
4. Every delegated prompt is self-contained: objective and why, current facts and ruled-out paths,
   file ownership, constraints and out-of-scope actions, deliverable, acceptance criteria, and the
   response format you want back. The child has none of your conversation.
5. Fan-in is yours: integrate results, resolve conflicts between lanes, re-run the affected checks,
   and deliver. Do not forward raw child output to the user as the final answer.
6. Handle role mismatches: if a teammate returns `ROLE_MISMATCH` or is unavailable, pick the closest
   owner yourself and state the substitution instead of retrying the same name.

## Delivery gate (coding)
Architecture settled -> implementation in lane -> `code-reviewer` review -> `verifier` verdict
(PASS / FAIL / PARTIAL) -> deliver with evidence. Skip a stage only with a stated reason.

"""


def stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def backup(path: Path, tag: str) -> None:
    shutil.copy2(path, path.with_name(path.name + f".bak-{tag}"))


def patch_text(path: Path, pairs: list[tuple[str, str]], apply: bool, tag: str) -> bool:
    """Apply literal replacements. Returns True when the file content changed."""
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    new = text
    hits = []
    for old, rep in pairs:
        if old in new:
            new = new.replace(old, rep)
            hits.append(old.splitlines()[0][:60])
    if new == text:
        return False
    print(f"{'PATCH' if apply else 'WOULD PATCH'} {path}")
    for h in hits:
        print(f"    - {h}...")
    if apply:
        backup(path, tag)
        path.write_text(new, encoding="utf-8")
    return True


def package_roots(explicit: str | None) -> list[Path]:
    roots: list[Path] = []
    if explicit:
        roots.append(Path(explicit).expanduser())
    # Global npm install location for the CLI/Desktop bundle.
    for base in (
        Path.home() / ".nvm/versions/node",
        Path("/usr/local/lib/node_modules"),
        Path("/opt/homebrew/lib/node_modules"),
    ):
        if not base.exists():
            continue
        try:
            candidates = sorted(base.glob("*/lib/node_modules/@minimax-ai/code"))
        except OSError:
            candidates = []
        candidates += [base / "@minimax-ai/code"]
        for candidate in candidates:
            if (candidate / "assets/agents").is_dir():
                roots.append(candidate)
    # Source checkout that builds the release artefacts.
    src = Path.home() / "codespace/minimax-code"
    if (src / "packages/local-runtime-v2/assets/agents").is_dir():
        roots.append(src / "packages/local-runtime-v2")
    seen, unique = set(), []
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(root)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="~/.minimax")
    parser.add_argument("--pkg", default=None, help="explicit @minimax-ai/code package dir")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser()
    tag = stamp()
    changed = 0

    # A. user-level overlay: the ONLY file a data-dir migration has to carry.
    mavis = data_dir / "agents/.builtin/mavis/agent.md"
    if mavis.is_file():
        text = mavis.read_text(encoding="utf-8")
        pairs: list[tuple[str, str]] = []
        # persona blocks (coding + tui variants), tolerate prior customisation
        if OLD_CODING_EN in text:
            pairs.append((OLD_CODING_EN, NEW_CODING_EN))
        if OLD_TUI_EN in text:
            pairs.append((OLD_TUI_EN, NEW_TUI_EN))
        # team block: insert once before each "# Core Judgment" that is not yet covered
        if text.count(TEAM_HEADING) == 0:
            text_marker = "\n\n# Core Judgment"
            if text.count(text_marker) != 3:
                print(
                    f"WARN: {mavis} has {text.count(text_marker)} '# Core Judgment' anchors, "
                    "expected 3 - inserting only before the first"
                )
            first = text.find(text_marker)
            if first >= 0:
                patched = text[:first] + "\n" + TEAM_BLOCK + "# Core Judgment" + text[first + len(text_marker):]
                patched = patched.replace(
                    text_marker, "\n" + TEAM_BLOCK + "# Core Judgment"
                )
                text = patched
        new = text
        for old, rep in pairs:
            new = new.replace(old, rep)
        if new != text:
            print(f"{'PATCH' if args.apply else 'WOULD PATCH'} {mavis}")
            if args.apply:
                backup(mavis, tag)
                mavis.write_text(new, encoding="utf-8")
            changed += 1
        else:
            print(f"ok      {mavis} (already patched)")

    # B + C. installed package templates (legacy + V2 render paths).
    for root in package_roots(args.pkg):
        agents_dir = root / "assets/agents"
        if not agents_dir.is_dir():
            continue
        legacy = agents_dir / "mavis/system-prompt.md.hbs"
        if patch_text(legacy, [(OLD_CODING_EN, NEW_CODING_EN)], args.apply, tag):
            changed += 1
        for kind, old_line, new_sentence in (
            ("coding", V2_CODING, NEW_CODING_EN + "\n"),
            ("tui", V2_TUI, NEW_TUI_EN + "\n"),
        ):
            target = agents_dir / f"_v2/{kind}/SYSTEM.md.hbs"
            if target.is_file() and old_line in target.read_text(encoding="utf-8"):
                if patch_text(target, [(old_line, new_sentence)], args.apply, tag):
                    changed += 1

    print()
    print(f"{'applied' if args.apply else 'dry-run'}: {changed} file(s) " + ("changed" if changed else "up to date"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
