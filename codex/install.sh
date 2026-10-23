#!/usr/bin/env bash
# Install the engineering-team agent roles for Codex.
#
#   ./codex/install.sh                # -> ~/.codex/team/agents/*.toml + AGENTS.md pointer
#   ./codex/install.sh --codex-home D # custom CODEX_HOME
#   ./codex/install.sh --dry-run
#
# Codex has no agent registry; this installs the role instruction files and a
# delimited pointer block in <CODEX_HOME>/AGENTS.md. config.toml is never touched.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_HOME_DIR="${CODEX_HOME:-${HOME}/.codex}"
DRY_RUN=0
BEGIN_MARK="<!-- team-agents:begin -->"
END_MARK="<!-- team-agents:end -->"

while [ $# -gt 0 ]; do
  case "$1" in
    --codex-home) CODEX_HOME_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${CODEX_HOME_DIR}/backup-team-agents-${STAMP}"
DEST="${CODEX_HOME_DIR}/team/agents"
say() { printf '%s\n' "$*"; }
run() { if [ "${DRY_RUN}" -eq 1 ]; then say "  would: $*"; else eval "$@"; fi; }

[ -d "${CODEX_HOME_DIR}" ] || { say "error: ${CODEX_HOME_DIR} not found (run codex login first)"; exit 1; }

say "codex home : ${CODEX_HOME_DIR}"
say "roles      : ${DEST}"
say ""

run "mkdir -p '${DEST}'"
for src in "${HERE}"/agents/*.toml "${HERE}"/agents/index.md; do
  [ -f "${src}" ] || continue
  base="$(basename "${src}")"
  dst="${DEST}/${base}"
  if [ -f "${dst}" ]; then
    run "mkdir -p '${BACKUP}'"
    run "cp -p '${dst}' '${BACKUP}/${base}'"
  fi
  run "cp '${src}' '${dst}'"
  say "  role     ${base}"
done

# Register the roster in the user-scope instruction file the lead always reads.
AGENTS_FILE="${CODEX_HOME_DIR}/AGENTS.md"
BLOCK_FILE="$(mktemp)"
{
  echo "${BEGIN_MARK}"
  echo "## Engineering team (managed by agent-teams)"
  echo ""
  echo "Specialist roles are installed at \`${DEST}\`. Each TOML has the role text under"
  echo "\`instructions.text\`; pass it verbatim when spawning a sub-agent via the multi-agent"
  echo "tools (spawnAgent/sendInput/wait/closeAgent). Roster index: \`${DEST}/index.md\`."
  echo ""
  echo "Route by deliverable: code changes go to the owning engineer, evidence to a read-only"
  echo "role, verdicts to code-reviewer, documents to tech-writer. Parallel writers must own"
  echo "disjoint files. Fan-in and the final answer stay with the lead."
  echo "${END_MARK}"
} > "${BLOCK_FILE}"

if [ -f "${AGENTS_FILE}" ]; then
  if grep -qF "${BEGIN_MARK}" "${AGENTS_FILE}" 2>/dev/null; then
    say "  note     ${AGENTS_FILE} already has a team block — left untouched"
  else
    run "mkdir -p '${BACKUP}'"
    run "cp -p '${AGENTS_FILE}' '${BACKUP}/AGENTS.md'"
    if [ "${DRY_RUN}" -eq 1 ]; then
      say "  would: append team block to ${AGENTS_FILE}"
    else
      { echo ""; cat "${BLOCK_FILE}"; } >> "${AGENTS_FILE}"
      say "  updated  ${AGENTS_FILE} (team block appended)"
    fi
  fi
else
  run "cp '${BLOCK_FILE}' '${AGENTS_FILE}'"
  say "  created  ${AGENTS_FILE}"
fi
rm -f "${BLOCK_FILE}"

say ""
say "roles installed: $(ls -1 "${HERE}"/agents/*.toml 2>/dev/null | wc -l | tr -d ' ')"
say "verify: codex exec -C /tmp/scratch \"\$(python3 -c \"import tomllib;print(tomllib.load(open('${DEST}/architect.toml','rb'))['instructions']['text'])\")\nTask: state your role. Reply ROLE=architect.\""
[ "${DRY_RUN}" -eq 1 ] && say "(dry run: nothing written)"
exit 0
