#!/usr/bin/env bash
# learnings.sh — Cross-skill institutional memory via JSONL
#
# Storage: ~/.gstack/projects/{slug}/learnings.jsonl
# Each line: {"ts","skill","type","key","insight","confidence","source","branch","commit","files":[]}
#
# Subcommands:
#   search [--type TYPE] [--limit N] [--key KEY] [--include-stale]
#                                                   Search learnings (latest per key+type;
#                                                   hides stale entries unless --include-stale)
#   log    '{"skill":...,"type":...,...}'           Append a learning
#   prune  [--dry-run]                              Flag stale entries (referenced files deleted)
#   path                                            Print the learnings file path
#   slug                                            Print the canonical project slug
set -euo pipefail

GSTACK_HOME="${GSTACK_HOME:-$HOME/.gstack}"

# --- Derive canonical project slug ---
# Prefer the SDD spec repo's directory basename when sdd_mode_detect.sh
# resolves IMMUTABLE_PRD_SPEC_CONFIG. Both spec and app sides of two-repo-app
# mode resolve to the same identity, so the learnings store is one shared
# per-project space rather than one per repo. Fall back to git toplevel
# basename for non-SDD invocations.
get_slug() {
  local spec_root=""

  if [ -n "${IMMUTABLE_PRD_SPEC_CONFIG:-}" ] && [ -f "$IMMUTABLE_PRD_SPEC_CONFIG" ]; then
    spec_root=$(dirname "$(dirname "$IMMUTABLE_PRD_SPEC_CONFIG")")
  elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -f "${CLAUDE_PLUGIN_ROOT}/scripts/sdd_mode_detect.sh" ]; then
    # Source under relaxed shell options in a subshell — extracts the var
    # only, sdd_mode_detect.sh stdout (diagnostic echoes) is suppressed.
    spec_root=$(
      set +eu
      # shellcheck disable=SC1091
      . "${CLAUDE_PLUGIN_ROOT}/scripts/sdd_mode_detect.sh" >/dev/null 2>&1
      if [ -n "${IMMUTABLE_PRD_SPEC_CONFIG:-}" ] && [ -f "$IMMUTABLE_PRD_SPEC_CONFIG" ]; then
        dirname "$(dirname "$IMMUTABLE_PRD_SPEC_CONFIG")"
      fi
    )
  fi

  if [ -n "$spec_root" ]; then
    basename "$spec_root" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g'
    return
  fi

  local toplevel
  toplevel=$(git rev-parse --show-toplevel 2>/dev/null || true)
  if [ -n "$toplevel" ]; then
    basename "$toplevel" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g'
  else
    basename "$PWD" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g'
  fi
}

get_learnings_file() {
  local slug
  slug=$(get_slug)
  echo "$GSTACK_HOME/projects/$slug/learnings.jsonl"
}

# =============================================================
# search — Query learnings, dedup by key+type (latest wins)
# =============================================================
cmd_search() {
  local limit=10
  local filter_type=""
  local filter_key=""
  local include_stale=false

  while [ $# -gt 0 ]; do
    case "$1" in
      --limit)         shift; limit="$1" ;;
      --type)          shift; filter_type="$1" ;;
      --key)           shift; filter_key="$1" ;;
      --include-stale) include_stale=true ;;
      *) echo "Unknown search arg: $1" >&2; exit 1 ;;
    esac
    shift
  done

  local file
  file=$(get_learnings_file)

  if [ ! -f "$file" ]; then
    echo "LEARNINGS: 0"
    exit 0
  fi

  # Dedup: for each key+type combo, keep the last (newest) entry
  # Then apply filters and limit
  local jq_filter='.'

  if [ -n "$filter_type" ]; then
    jq_filter="$jq_filter | select(.type == \"$filter_type\")"
  fi
  if [ -n "$filter_key" ]; then
    jq_filter="$jq_filter | select(.key | test(\"$filter_key\"; \"i\"))"
  fi

  # Stale filter runs BEFORE group_by so a stale row that is the newest in
  # its (key, type) bucket cannot mask an earlier active row via map(last).
  local stale_pred='select((.stale // false) == false)'
  [ "$include_stale" = true ] && stale_pred='.'

  # Read all lines, drop stale (unless --include-stale), group by key+type,
  # keep last of each group, apply filters
  jq -s "
    map($stale_pred)
    | group_by([.key, .type])
    | map(last)
    | map($jq_filter)
    | flatten
    | sort_by(.ts)
    | reverse
    | .[:$limit]
    | .[]
  " "$file" 2>/dev/null || echo "LEARNINGS: 0 (parse error)"
}

# =============================================================
# log — Append a learning entry
# =============================================================
cmd_log() {
  local entry="$1"

  # Validate JSON
  if ! printf '%s' "$entry" | jq -e . >/dev/null 2>&1; then
    echo "Invalid JSON: $entry" >&2
    exit 1
  fi

  local file
  file=$(get_learnings_file)
  mkdir -p "$(dirname "$file")"

  # Enrich with timestamp, branch, commit if not present
  local ts branch commit
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  branch=$(git branch --show-current 2>/dev/null || echo "unknown")
  commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

  # Merge defaults (entry values take precedence). files defaults to []
  # so prune can iterate uniformly even when the writer didn't pass --argjson files.
  local enriched
  enriched=$(printf '%s' "$entry" | jq \
    --arg ts "$ts" \
    --arg branch "$branch" \
    --arg commit "$commit" \
    '. + {ts: (.ts // $ts), branch: (.branch // $branch), commit: (.commit // $commit), files: (.files // [])}')

  # Validate required fields
  local missing=""
  for field in skill type key insight confidence; do
    if printf '%s' "$enriched" | jq -e ".$field == null" >/dev/null 2>&1; then
      missing="$missing $field"
    fi
  done

  if [ -n "$missing" ]; then
    echo "Missing required fields:$missing" >&2
    echo "Required: skill, type, key, insight, confidence" >&2
    exit 1
  fi

  # POSIX-atomic append: O_APPEND writes shorter than PIPE_BUF (4 KiB on
  # Linux, ≥512 by POSIX) are atomic against concurrent O_APPEND writers,
  # which is the workload here (parallel-pod cycles emit log entries
  # near-simultaneously per CHANGELOG v0.6.5). Entries are ~300-500 bytes,
  # well under PIPE_BUF. The previous cp→append→rename pattern was
  # kill-safe but introduced lost-update for concurrent writers — last
  # mv wins, earlier writer's entry silently dropped.
  printf '%s\n' "$enriched" | jq -c '.' >> "$file"

  local count
  count=$(wc -l < "$file" | tr -d ' ')
  echo "Logged learning: $(printf '%s' "$enriched" | jq -r '.key') (total: $count)"
}

# =============================================================
# prune — Check for stale entries (referenced files deleted)
# =============================================================
cmd_prune() {
  local dry_run=false
  [ "${1:-}" = "--dry-run" ] && dry_run=true

  local file
  file=$(get_learnings_file)

  if [ ! -f "$file" ]; then
    echo "No learnings file found."
    exit 0
  fi

  local total stale kept
  total=$(wc -l < "$file" | tr -d ' ')
  stale=0
  kept=0

  # Use global var so EXIT trap can access it after function scope ends
  _PRUNE_TMP=$(mktemp)
  trap 'rm -f "$_PRUNE_TMP"' EXIT
  local tmpfile="$_PRUNE_TMP"

  while IFS= read -r line; do
    # Extract files array
    local files_json
    files_json=$(printf '%s' "$line" | jq -r '.files // [] | .[]' 2>/dev/null)

    local is_stale=false
    if [ -n "$files_json" ]; then
      while IFS= read -r filepath; do
        if [ ! -e "$filepath" ]; then
          is_stale=true
          break
        fi
      done <<< "$files_json"
    fi

    if [ "$is_stale" = true ]; then
      stale=$((stale + 1))
      local key type_val
      key=$(printf '%s' "$line" | jq -r '.key // "?"')
      type_val=$(printf '%s' "$line" | jq -r '.type // "?"')
      echo "stale: $key ($type_val) — referenced file missing"
      if [ "$dry_run" = false ]; then
        # Mark as stale rather than deleting (append stale flag)
        printf '%s' "$line" | jq -c '. + {stale: true}' >> "$tmpfile"
      fi
    else
      kept=$((kept + 1))
      echo "$line" >> "$tmpfile"
    fi
  done < "$file"

  if [ "$dry_run" = true ]; then
    echo ""
    echo "prune: $stale stale / $total total (dry run, no changes)"
  else
    if [ "$stale" -gt 0 ]; then
      mv "$tmpfile" "$file"
    fi
    echo ""
    echo "prune: $stale marked stale, $kept active / $total total"
  fi
}

# =============================================================
# path — Print the learnings file path
# =============================================================
cmd_path() {
  get_learnings_file
}

# =============================================================
# Main dispatch
# =============================================================
case "${1:-help}" in
  search)  shift; cmd_search "$@" ;;
  log)     shift; cmd_log "${1:-}" ;;
  prune)   shift; cmd_prune "${1:-}" ;;
  path)    cmd_path ;;
  slug)    get_slug ;;
  help|--help|-h)
    echo "Usage: learnings.sh <command> [args]"
    echo ""
    echo "Commands:"
    echo "  search [--type TYPE] [--limit N] [--key KEY] [--include-stale]"
    echo "                                                  Query learnings (hides stale)"
    echo "  log    '{\"skill\":...,\"type\":...,...}'        Append a learning"
    echo "  prune  [--dry-run]                             Flag stale entries"
    echo "  path                                           Print learnings file path"
    echo "  slug                                           Print canonical project slug"
    ;;
  *)
    echo "Unknown command: $1" >&2
    echo "Run 'learnings.sh help' for usage." >&2
    exit 1
    ;;
esac
