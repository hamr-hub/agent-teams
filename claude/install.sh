#!/usr/bin/env bash
# Install the engineering-team agents into Claude Code.
#
#   ./claude/install.sh                  # install into ~/.claude (user scope)
#   ./claude/install.sh --project        # install into ./.claude (repo scope)
#   ./claude/install.sh --dry-run
#
# Idempotent and additive; every overwritten file is backed up.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "${HERE}")"
TARGET="${HOME}/.claude"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --project) TARGET="${PWD}/.claude"; shift ;;
    --data-dir|--claude-dir) TARGET="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${TARGET}/backup-team-agents-${STAMP}"
say() { printf '%s\n' "$*"; }
run() { if [ "${DRY_RUN}" -eq 1 ]; then say "  would: $*"; else eval "$@"; fi; }

mkdir -p "${TARGET}/agents"
say "claude dir : ${TARGET}"
say "backup     : ${BACKUP}"
say ""

for src in "${HERE}"/agents/*.md; do
  name="$(basename "${src}")"
  dst="${TARGET}/agents/${name}"
  [ -f "${dst}" ] && { run "mkdir -p '${BACKUP}'"; run "cp -p '${dst}' '${BACKUP}/${name}'"; }
  run "cp '${src}' '${dst}'"
  say "  agent    ${name%.md}"
done

# The lead's operating contract. Claude Code reads ~/.claude/CLAUDE.md at user
# scope; project-scope installs normally use the repo's own CLAUDE.md instead.
if [ -f "${HERE}/CLAUDE.md" ] && [ "${TARGET}" = "${HOME}/.claude" ]; then
  dst="${TARGET}/CLAUDE.md"
  if [ -f "${dst}" ]; then
    run "mkdir -p '${BACKUP}'"
    run "cp -p '${dst}' '${BACKUP}/CLAUDE.md'"
    say "  NOTE     ${dst} already exists — written as CLAUDE.team-agents.md instead"
    dst="${TARGET}/CLAUDE.team-agents.md"
  fi
  run "cp '${HERE}/CLAUDE.md' '${dst}'"
  say "  contract  ${dst}"
fi

say ""
count=$(ls -1 "${HERE}"/agents/*.md 2>/dev/null | wc -l | tr -d ' ')
say "agents: ${count}"
say "verify: claude --agent architect -p 'state your role'"
say "        claude -p 'use the Task tool with subagent_type=qa-engineer and report its reply'"
[ "${DRY_RUN}" -eq 1 ] && say "(dry run: nothing written)"
exit 0
