#!/usr/bin/env bash
# Install the MCode engineering-team pack into a MiniMax Code data dir.
#
#   ./install.sh                 # install into ~/.minimax
#   ./install.sh --data-dir DIR  # install into another profile
#   ./install.sh --dry-run       # show what would happen
#
# Idempotent and additive: files are only created or overwritten, never deleted.
# Every overwritten file is first copied into <dataDir>/backup-team-agents-<ts>/.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${HOME}/.minimax"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --data-dir) DATA_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

DATA_DIR="${DATA_DIR/#\~/$HOME}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${DATA_DIR}/backup-team-agents-${STAMP}"
AGENTS_SRC="${HERE}/agents"

say() { printf '%s\n' "$*"; }
run() { if [ "${DRY_RUN}" -eq 1 ]; then say "    would: $*"; else eval "$@"; fi; }

[ -d "${DATA_DIR}" ] || { say "error: data dir not found: ${DATA_DIR}"; exit 1; }
[ -d "${AGENTS_SRC}" ] || { say "error: agents/ missing next to install.sh"; exit 1; }

TEAM_ROSTER=(architect product-owner ui-ux-designer frontend-engineer backend-engineer
             api-designer data-engineer sre-engineer security-engineer qa-engineer
             code-reviewer performance-engineer tech-writer)

say "data dir : ${DATA_DIR}"
say "pack     : ${HERE}"
say "backup   : ${BACKUP}"
say ""

# 1. Global operating contract (strongest injection layer, shared by CLI + Desktop).
if [ -f "${HERE}/payload/AGENTS.md" ]; then
  target="${DATA_DIR}/AGENTS.md"
  if [ -f "${target}" ]; then
    run "mkdir -p '${BACKUP}'"
    run "cp -p '${target}' '${BACKUP}/AGENTS.md'"
    say "  updated  ${target}  (previous copy in backup)"
  else
    say "  create   ${target}"
  fi
  run "mkdir -p '$(dirname "${target}")'"
  run "cp '${HERE}/payload/AGENTS.md' '${target}'"
else
  say "  skip     payload/AGENTS.md not found"
fi

# 2. Tech Lead identity overlay for the built-in primary Agent.
if [ -f "${HERE}/payload/mavis-agent.md" ]; then
  target="${DATA_DIR}/agents/.builtin/mavis/agent.md"
  if [ -f "${target}" ]; then
    run "mkdir -p '${BACKUP}/mavis'"
    run "cp -p '${target}' '${BACKUP}/mavis/agent.md'"
  fi
  run "mkdir -p '${DATA_DIR}/agents/.builtin/mavis'"
  run "cp '${HERE}/payload/mavis-agent.md' '${target}'"
  say "  updated  ${target}"
else
  say "  skip     payload/mavis-agent.md not found"
fi

# 3. Custom Agents. One directory per agent, each with a single agent.md.
for name in "${TEAM_ROSTER[@]}"; do
  src="${AGENTS_SRC}/${name}/agent.md"
  [ -f "${src}" ] || { say "  MISSING  ${src}"; continue; }
  target_dir="${DATA_DIR}/agents/${name}"
  target="${target_dir}/agent.md"
  if [ -f "${target}" ]; then
    run "mkdir -p '${BACKUP}/${name}'"
    run "cp -p '${target}' '${BACKUP}/${name}/agent.md'"
  fi
  run "mkdir -p '${target_dir}'"
  run "cp '${src}' '${target}'"
  say "  install  ${name}"
done

say ""
count=$(ls -1d "${DATA_DIR}/agents"/*/ 2>/dev/null | wc -l | tr -d ' ')
say "done. ${count} directories under ${DATA_DIR}/agents"
say "verify: mcode exec --prompt-mode tui 'List the agent_names you can delegate to'"
if [ "${DRY_RUN}" -eq 1 ]; then say "(dry run: nothing was written)"; fi
