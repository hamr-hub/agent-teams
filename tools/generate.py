#!/usr/bin/env python3
"""Generate per-tool agent artefacts from team.yaml (single source of truth).

Targets
  mcode    → mcode/agents/<name>/agent.md     Custom Agent (frontmatter + body)
  claude   → claude/agents/<name>.md           Claude Code subagent
  codex    → codex/agents/<name>.toml          Codex agent role/persona

Usage
  python3 tools/generate.py            # write artefacts
  python3 tools/generate.py --check    # fail if artefacts are stale (CI)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

ROOT = Path(__file__).resolve().parents[1]
TEAM = yaml.safe_load((ROOT / "team.yaml").read_text(encoding="utf-8"))
CAPS = yaml.safe_load((ROOT / "capabilities.yaml").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# shared body: identical wording across tools so roles never drift
# --------------------------------------------------------------------------- #

def display(agent: dict) -> str:
    return agent["display"]


def summary(agent: dict) -> str:
    return agent["summary"]


def body_markdown(agent: dict, heading: str) -> str:
    owns = "\n".join(f"- {item}" for item in agent["owns"])
    boundaries = "\n".join(f"- {item}" for item in agent["boundaries"])
    deliverable = "\n".join(f"- {item}" for item in agent["deliverable"])
    return (
        f"{heading} {display(agent)}\n\n"
        f"{summary(agent)}.\n\n"
        f"## Duties\n{owns}\n\n"
        f"## Boundaries\n{boundaries}\n\n"
        f"## Deliverable\n{deliverable}\n"
    )


# --------------------------------------------------------------------------- #
# MCode: Custom Agent (agent.md)
# --------------------------------------------------------------------------- #

def mcode_tools(agent: dict) -> list[str]:
    tier = agent["tier"]
    tools = list(CAPS["tools"]["read"] if tier == "read" else CAPS["tools"]["write"])
    tools += CAPS["tools"]["control"]
    # Explore-style evidence roles benefit from fetching external docs.
    if tier == "read":
        tools += CAPS["tools"]["web"]
    seen, out = set(), []
    for tool in tools:
        if tool not in seen:
            seen.add(tool)
            out.append(tool)
    return out


def mcode_artefact(agent: dict) -> str:
    tools = "\n".join(f"  - {t}" for t in mcode_tools(agent))
    return (
        "---\n"
        f"name: {agent['name']}\n"
        f"description: {summary(agent)}\n"
        "tools:\n"
        f"{tools}\n"
        "skills: []\n"
        "x-mavis:\n"
        f"  displayName: {display(agent)}\n"
        "---\n\n"
        "{{#if persona.enabled}}\n"
        f"{agent['persona'] if 'persona' in agent else default_persona(agent)}\n"
        "{{/if}}\n\n"
        f"{body_markdown(agent, '# Role:')}"
    )


def default_persona(agent: dict) -> str:
    """Short, tool-agnostic 'how I work' line derived from the first duty."""
    return (
        f"You are the {display(agent)}. "
        f"{agent['owns'][0][0].upper() + agent['owns'][0][1:]}.\n"
        "State assumptions plainly; report what you verified versus what you assumed."
    )


# --------------------------------------------------------------------------- #
# Claude Code: subagent file (agents/<name>.md)
# --------------------------------------------------------------------------- #

def claude_artefact(agent: dict) -> str:
    tools = ", ".join(CAPS["claude_tools"]["read" if agent["tier"] == "read" else "write"])
    model = CAPS["claude_models"]["default"]
    prompt = body_markdown(agent, "# Role:")
    # Claude Code frontmatter is YAML; the prompt lives in the body.
    return (
        "---\n"
        f"name: {agent['name']}\n"
        f"description: {summary(agent)}. Use for {agent['role']} work; reports findings and deliverables back to the lead.\n"
        f"tools: {tools}\n"
        f"model: {model}\n"
        "---\n\n"
        f"{prompt}\n"
        "## Reporting\n"
        "Return to the calling agent: what you did, what you verified, and anything you deliberately left alone.\n"
        "Do not widen scope beyond the assignment; if the task needs another lane, say which one.\n"
    )


# --------------------------------------------------------------------------- #
# Codex: agent role/TOML
# --------------------------------------------------------------------------- #

def toml_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def codex_artefact(agent: dict) -> str:
    prompt = body_markdown(agent, "## Role:")
    lines = [
        "# Generated from team.yaml — do not hand-edit.",
        f"# Codex agent role: {agent['name']} ({display(agent)})",
        'name = "%s"' % agent["name"],
        'display = "%s"' % display(agent),
        'role = "%s"' % agent["role"],
        'tier = "%s"' % agent["tier"],
        'summary = "%s"' % toml_escape(summary(agent)),
        "",
        "[instructions]",
        '# Codex has no per-agent files; the coordinator pastes this as the role',
        "# instruction for a delegated session (`codex exec ... \"<instructions>\"`).",
        'text = """',
        prompt.rstrip(),
        '"""',
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #

GENERATORS = {
    "mcode": (ROOT / "mcode" / "agents", "agent.md", mcode_artefact),
    "claude": (ROOT / "claude" / "agents", None, claude_artefact),
    "codex": (ROOT / "codex" / "agents", None, codex_artefact),
}

CODEX_INDEX = ROOT / "codex" / "agents" / "index.md"


def codex_index() -> str:
    """Roster index the Codex lead reads to learn which roles exist."""
    rows = "\n".join(
        f"| `{a['name']}` | {display(a)} | {a['tier']} | {a['summary']} |" for a in TEAM["agents"]
    )
    return (
        "# Codex agent roster\n\n"
        "Generated from `team.yaml`. One TOML per role in this directory; the role text lives in\n"
        "`instructions.text`. Pass it verbatim when spawning a sub-agent.\n\n"
        "| agent | role | tier | owns |\n"
        "| --- | --- | --- | --- |\n"
        f"{rows}\n\n"
        "## Delegation contract\n\n"
        "1. Route by deliverable: code changes to the owning engineer, evidence to a read-only role,\n"
        "   verdicts to `code-reviewer`, documents to `tech-writer`.\n"
        "2. Do not delegate trivia.\n"
        "3. Every delegated brief is self-contained: objective, facts and ruled-out paths, file\n"
        "   ownership, out-of-scope actions, deliverable, acceptance criteria, output format.\n"
        "4. Parallel writers must own disjoint files.\n"
        "5. Fan-in and the final answer stay with the lead.\n"
        "6. Report what ran, what passed, and what is unverified.\n"
    )


def path_for(kind: str, out_dir: Path, name: str, fixed: str | None) -> Path:
    if fixed:
        return out_dir / name / fixed
    ext = "md" if kind == "claude" else "toml"
    return out_dir / f"{name}.{ext}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify artefacts are up to date")
    args = parser.parse_args()

    stale: list[Path] = []
    written = 0
    for kind, (out_dir, fixed, render) in GENERATORS.items():
        for agent in TEAM["agents"]:
            path = path_for(kind, out_dir, agent["name"], fixed)
            content = render(agent)
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current == content:
                continue
            if args.check:
                stale.append(path)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            written += 1
            print(f"wrote {path.relative_to(ROOT)}")

    index_path = CODEX_INDEX
    index_content = codex_index()
    current_index = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    if current_index != index_content:
        if args.check:
            stale.append(index_path)
        else:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(index_content, encoding="utf-8")
            written += 1
            print(f"wrote {index_path.relative_to(ROOT)}")

    if args.check:
        if stale:
            print("stale artefacts (run tools/generate.py):", file=sys.stderr)
            for path in stale:
                print(f"  {path.relative_to(ROOT)}", file=sys.stderr)
            return 1
        print("all artefacts up to date")
        return 0

    print(f"{written} file(s) written from team.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
