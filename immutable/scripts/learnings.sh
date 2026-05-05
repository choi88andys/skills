#!/usr/bin/env bash
# learnings.sh — Cross-skill institutional memory via JSONL
#
# Storage: ~/.gstack/projects/{slug}/learnings.jsonl
# Each line: {"ts","skill","type","key","insight","confidence","source","branch","commit","files":[]}
#
# Subcommands:
#   search [--type TYPE] [--limit N] [--key KEY]   Search learnings (latest per key+type)
#   log    '{"skill":...,"type":...,...}'           Append a learning
#   prune  [--dry-run]                              Flag stale entries (referenced files deleted)
#   path                                            Print the learnings file path
set -euo pipefail

GSTACK_HOME="${GSTACK_HOME:-$HOME/.gstack}"

# --- Derive project slug from git repo or cwd ---
get_slug() {
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

  while [ $# -gt 0 ]; do
    case "$1" in
      --limit)  shift; limit="$1" ;;
      --type)   shift; filter_type="$1" ;;
      --key)    shift; filter_key="$1" ;;
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

  # Read all lines, group by key+type, keep last of each group, apply filters
  jq -s "
    group_by([.key, .type])
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

  # Merge defaults (entry values take precedence)
  local enriched
  enriched=$(printf '%s' "$entry" | jq \
    --arg ts "$ts" \
    --arg branch "$branch" \
    --arg commit "$commit" \
    '. + {ts: (.ts // $ts), branch: (.branch // $branch), commit: (.commit // $commit)}')

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

  # Atomic append: copy → append → rename (prevents corruption on kill)
  local tmpfile="$file.tmp.$$"
  if [ -f "$file" ]; then
    cp "$file" "$tmpfile"
  fi
  printf '%s\n' "$enriched" | jq -c '.' >> "$tmpfile"
  mv -f "$tmpfile" "$file"

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
  help|--help|-h)
    echo "Usage: learnings.sh <command> [args]"
    echo ""
    echo "Commands:"
    echo "  search [--type TYPE] [--limit N] [--key KEY]  Query learnings"
    echo "  log    '{\"skill\":...,\"type\":...,...}'        Append a learning"
    echo "  prune  [--dry-run]                             Flag stale entries"
    echo "  path                                           Print learnings file path"
    ;;
  *)
    echo "Unknown command: $1" >&2
    echo "Run 'learnings.sh help' for usage." >&2
    exit 1
    ;;
esac
