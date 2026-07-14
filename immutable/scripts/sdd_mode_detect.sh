#!/usr/bin/env bash
# sdd_mode_detect.sh — locate `.immutable-prd/config.yml` and resolve the cross-paired
# spec / app config (when applicable). Single source of truth for `immutable-prd`
# detection; replaces the ~200-line block previously duplicated across sprint skills.
#
# USAGE
#   This script is intended to be SOURCED by a SKILL.md bash block, not executed
#   directly:
#       source "${CLAUDE_PLUGIN_ROOT}/scripts/sdd_mode_detect.sh"
#   After sourcing, the variables below are set in the caller's shell.
#
# EXPORTED VARIABLES
#   SDD_MODE                    "immutable-prd" or "legacy". v0.6.0 immutable
#                               plugin only operates in "immutable-prd"; new
#                               skills MUST refuse when SDD_MODE=legacy.
#   IMMUTABLE_PRD_CONFIG        Absolute path to the primary config.yml. The
#                               "primary" config is the one walk-up finds from
#                               PWD (i.e. the repo the user is standing in).
#                               Empty when detection fails.
#   IMMUTABLE_PRD_SPEC_CONFIG   Path to the spec repo's config (has
#                               `pitches_path:`). Equal to IMMUTABLE_PRD_CONFIG
#                               in single-repo mode. Empty when no spec config
#                               can be paired with the primary.
#   IMMUTABLE_PRD_APP_CONFIG    Path to the app repo's config (has `adr_path:`).
#                               Equal to IMMUTABLE_PRD_CONFIG in single-repo
#                               mode. Empty when no app config can be paired.
#   IMMUTABLE_PRD_REPO_MODE     Value of primary config's `repo_mode:` —
#                               "two-repo", "two-repo-app", "two-repo-spec",
#                               or "single-repo". Empty in legacy mode.
#   SDD_AMBIGUITY_FLAG          "1" when the reverse-config scan found multiple
#                               sibling app configs claiming this spec; "0"
#                               otherwise. Caller should surface this to the
#                               user and prompt for `.claude/sdd-mode`
#                               disambiguation.
#
# RESOLUTION ORDER
#   1. Walk-up from PWD to repo root (`.git` boundary), looking for
#      `.immutable-prd/config.yml`. Catches single-repo and either side of a
#      two-repo pair when called from inside one of them.
#   2. Explicit pointer at `$PWD/.claude/sdd-mode` containing
#      `immutable-prd:<repo-path>` — escape hatch for non-standard layouts.
#   3. Sibling `-app` / `-spec` suffix convention — last-resort bootstrap fallback.
#
#   For the secondary (cross-paired) config:
#     - PWD == app repo: resolve spec via app's `spec_repo_path:` (preferred,
#       relative-path-safe); fall back to suffix-sibling.
#     - PWD == spec repo: reverse-scan siblings for an app config whose
#       `spec_repo_path:` resolves back to this spec root (naming-agnostic).
#       Fall back to suffix-sibling on no match. Set SDD_AMBIGUITY_FLAG=1
#       on >1 matches.
#     - PWD == single repo: spec and app point at the same config.
#
# DESIGN NOTES
#   - This script does NOT call `set -u` / `set -e`; sourcing it must not change
#     the caller's shell options.
#   - All helper function names are prefixed with `_sdd_` to avoid colliding
#     with caller scope.
#   - Error output (e.g. ambiguity warning) goes to stderr; informational logs
#     go to stdout so the caller can capture them in transcripts.

# --- 1. Walk-up from PWD looking for .immutable-prd/config.yml ---
#   Stops at filesystem root or `.git` boundary, whichever comes first.
_sdd_walk_immutable_prd() {
  local current="$(pwd)"
  while :; do
    if [ -f "$current/.immutable-prd/config.yml" ]; then
      echo "$current/.immutable-prd/config.yml"
      return 0
    fi
    [ -d "$current/.git" ] && return 1
    local parent="$(dirname "$current")"
    [ "$parent" = "$current" ] && return 1
    current="$parent"
  done
}

# --- 2a. Sibling -app/-spec convention (bootstrap convenience only) ---
#   Input: a repo root (directory, not the config file).
#   Output: sibling repo root if config exists there, else empty.
#   Use: last-resort fallback for repos that follow the -app/-spec suffix
#   convention. Backend / non-standard naming should set explicit pointers
#   (`spec_repo_path:` in app config, or `.claude/sdd-mode` file).
_sdd_sibling_pair_root() {
  local root="$1"
  local base="$(basename "$root")"
  local sib=""
  case "$base" in
    *-app)  sib="$(dirname "$root")/${base%-app}-spec" ;;
    *-spec) sib="$(dirname "$root")/${base%-spec}-app" ;;
  esac
  if [ -n "$sib" ] && [ -f "$sib/.immutable-prd/config.yml" ]; then
    echo "$sib"
    return 0
  fi
  return 1
}

# --- 2a-bis. Main-checkout root (linked-worktree awareness) ---
#   Input:  a checkout root.
#   Output: the MAIN worktree's root on stdout when the input is a LINKED
#           worktree. Empty + return 1 when git is unavailable, the path is not a
#           git repo, or it already IS the main checkout — callers then keep their
#           checkout-relative resolution untouched.
#
#   `git worktree list --porcelain` lists the main worktree FIRST and always as an
#   absolute path. Preferred over `rev-parse --git-common-dir`, which prints a
#   *relative* `.git` from the main checkout and whose parent is not the checkout
#   root at all under `git init --separate-git-dir` or inside a submodule.
_sdd_main_worktree_root() {
  local root main
  root="$(cd "$1" 2>/dev/null && pwd -P)" || return 1
  [ -n "$root" ] || return 1
  main="$(git -C "$root" worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')"
  [ -n "$main" ] || return 1
  main="$(cd "$main" 2>/dev/null && pwd -P)" || return 1
  [ "$main" = "$root" ] && return 1
  echo "$main"
}

# --- 2a-ter. Resolve an app repo's `spec_repo_path:` to an absolute spec root ---
#   Input:  $1 = app repo root (may be a LINKED worktree), $2 = spec_repo_path value.
#   Output: absolute spec root on stdout, or empty + return 1.
#
#   A RELATIVE spec_repo_path means "the spec repo sits next to my REPO". Called
#   from a linked worktree, $1 is the worktree — not the repo — so `../` only lands
#   correctly when that worktree happens to be a sibling of the main checkout. It
#   does not for the nested layouts a dispatch harness creates
#   (`<parent>/<repo>-worktrees/cycle-N/pod-M`), where `../` is the cycle dir.
#   So: try the checkout-relative path FIRST (every existing layout keeps winning,
#   including a spec repo genuinely beside the worktree), then fall back to the
#   main-checkout-relative one. ABSOLUTE paths carry no such ambiguity and are used
#   as-is. A candidate counts only when it actually holds `.immutable-prd/config.yml`.
_sdd_resolve_spec_root() {
  local root="$1" spec="$2" cand main
  case "$spec" in
    /*)
      [ -f "$spec/.immutable-prd/config.yml" ] && { echo "$spec"; return 0; }
      return 1
      ;;
  esac
  cand="$(cd "$root" && cd "$spec" 2>/dev/null && pwd || echo "")"
  if [ -n "$cand" ] && [ -f "$cand/.immutable-prd/config.yml" ]; then
    echo "$cand"
    return 0
  fi
  main="$(_sdd_main_worktree_root "$root")" || return 1
  cand="$(cd "$main" && cd "$spec" 2>/dev/null && pwd || echo "")"
  if [ -n "$cand" ] && [ -f "$cand/.immutable-prd/config.yml" ]; then
    echo "$cand"
    return 0
  fi
  return 1
}

# --- 2b. Reverse-config scan: find app config whose spec_repo_path: points here ---
#   Input: spec repo absolute path.
#   Output (globals, not stdout — side-effect design):
#     _SDD_REV_APP_ROOT    set to matching sibling app repo root on single match,
#                          "" otherwise
#     SDD_AMBIGUITY_FLAG   set to "1" when >1 candidates found (survives into
#                          caller)
#   Call without `$()` so global writes persist in the caller's shell.
#   Scope: siblings under dirname($1) only — not recursive, not workspace-wide.
#   Rationale: this is the primary spec→app resolver. It ignores directory
#   naming entirely, working for backend/api/server/etc. repos. The app's
#   existing `spec_repo_path:` pointer is verified (must resolve to our spec
#   root), so unrelated apps in the workspace can't false-match.
_sdd_reverse_scan_app_for_spec() {
  local my_spec_root="$1"
  local parent
  parent="$(dirname "$my_spec_root")"
  local match_count=0
  local dir cfg role their_spec_path resolved
  _SDD_REV_APP_ROOT=""
  for dir in "$parent"/*/; do
    dir="${dir%/}"
    [ "$dir" = "$my_spec_root" ] && continue
    cfg="$dir/.immutable-prd/config.yml"
    [ -f "$cfg" ] || continue
    role="$(_sdd_config_role "$cfg")"
    [ "$role" = "app" ] || continue
    their_spec_path="$(grep '^spec_repo_path:' "$cfg" 2>/dev/null | head -1 | awk '{print $2}')"
    [ -n "$their_spec_path" ] || continue
    resolved="$(_sdd_resolve_spec_root "$dir" "$their_spec_path" || echo "")"
    [ "$resolved" = "$my_spec_root" ] || continue
    match_count=$((match_count + 1))
    _SDD_REV_APP_ROOT="$dir"
  done
  if [ "$match_count" -eq 0 ]; then
    _SDD_REV_APP_ROOT=""
    return 1
  elif [ "$match_count" -gt 1 ]; then
    _SDD_REV_APP_ROOT=""
    SDD_AMBIGUITY_FLAG=1
    return 2
  fi
  return 0
}

# --- 3. Explicit pointer escape hatch (non-standard layouts) ---
#   `.claude/sdd-mode` file contains a single line `immutable-prd:<repo-path>`
#   pointing at the config to use. Useful when sibling naming doesn't apply
#   (e.g., the spec is two directories away).
_sdd_explicit_immutable_prd() {
  local marker=".claude/sdd-mode"
  if [ -f "$marker" ]; then
    local line
    line="$(grep '^immutable-prd:' "$marker" | head -1 | sed 's/^immutable-prd://')"
    if [ -n "$line" ] && [ -f "$line/.immutable-prd/config.yml" ]; then
      echo "$line/.immutable-prd/config.yml"
      return 0
    fi
  fi
  return 1
}

# --- 4. Classify a config by role (spec / app / single) ---
#   Reads `repo_mode:` directly. Falls back to key inference for legacy
#   configs that lack the field.
_sdd_config_role() {
  local cfg="$1"
  local mode
  mode="$(grep '^repo_mode:' "$cfg" 2>/dev/null | head -1 | awk '{print $2}')"
  case "$mode" in
    two-repo-app) echo "app" ;;
    single-repo)  echo "single" ;;
    two-repo|two-repo-spec) echo "spec" ;;
    *)
      # Legacy / unset — infer from keys present.
      if grep -q '^adr_path:' "$cfg" 2>/dev/null; then echo "app"
      elif grep -q '^pitches_path:' "$cfg" 2>/dev/null; then echo "spec"
      else echo "unknown"
      fi
      ;;
  esac
}

# --- 5. Primary detect + cross-pair resolution ---
IMMUTABLE_PRD_CONFIG="$(_sdd_walk_immutable_prd || _sdd_explicit_immutable_prd || true)"

# If walk-up/explicit missed but we're in a sibling layout, fall through.
if [ -z "$IMMUTABLE_PRD_CONFIG" ]; then
  _sdd_sibling_root_from_pwd="$(_sdd_sibling_pair_root "$(pwd)" 2>/dev/null || true)"
  if [ -n "$_sdd_sibling_root_from_pwd" ]; then
    IMMUTABLE_PRD_CONFIG="$_sdd_sibling_root_from_pwd/.immutable-prd/config.yml"
  fi
fi

IMMUTABLE_PRD_SPEC_CONFIG=""
IMMUTABLE_PRD_APP_CONFIG=""
SDD_AMBIGUITY_FLAG=0

if [ -n "$IMMUTABLE_PRD_CONFIG" ]; then
  _sdd_primary_root="$(dirname "$(dirname "$IMMUTABLE_PRD_CONFIG")")"
  case "$(_sdd_config_role "$IMMUTABLE_PRD_CONFIG")" in
    app)
      IMMUTABLE_PRD_APP_CONFIG="$IMMUTABLE_PRD_CONFIG"
      # Resolve spec via spec_repo_path (preferred, explicit) or sibling fallback.
      # Relative paths resolve against this checkout first, then the main checkout
      # when this is a linked worktree — see _sdd_resolve_spec_root.
      _sdd_spec_path="$(grep '^spec_repo_path:' "$IMMUTABLE_PRD_CONFIG" 2>/dev/null | head -1 | awk '{print $2}')"
      if [ -n "$_sdd_spec_path" ]; then
        _sdd_resolved="$(_sdd_resolve_spec_root "$_sdd_primary_root" "$_sdd_spec_path" || echo "")"
        [ -n "$_sdd_resolved" ] && [ -f "$_sdd_resolved/.immutable-prd/config.yml" ] \
          && IMMUTABLE_PRD_SPEC_CONFIG="$_sdd_resolved/.immutable-prd/config.yml"
      fi
      if [ -z "$IMMUTABLE_PRD_SPEC_CONFIG" ]; then
        _sdd_sib="$(_sdd_sibling_pair_root "$_sdd_primary_root" 2>/dev/null || true)"
        [ -n "$_sdd_sib" ] && IMMUTABLE_PRD_SPEC_CONFIG="$_sdd_sib/.immutable-prd/config.yml"
      fi
      ;;
    spec)
      IMMUTABLE_PRD_SPEC_CONFIG="$IMMUTABLE_PRD_CONFIG"
      # Primary: reverse-scan siblings for an app whose spec_repo_path: points here.
      # Works regardless of repo naming (backend / api / server / custom).
      # Call without $() so the function's global writes persist in this shell.
      _SDD_REV_APP_ROOT=""
      _sdd_reverse_scan_app_for_spec "$_sdd_primary_root" 2>/dev/null || true
      if [ -n "$_SDD_REV_APP_ROOT" ]; then
        IMMUTABLE_PRD_APP_CONFIG="$_SDD_REV_APP_ROOT/.immutable-prd/config.yml"
      else
        if [ "${SDD_AMBIGUITY_FLAG}" = "1" ]; then
          echo "WARN: multiple sibling app configs point at this spec repo via spec_repo_path:. Use .claude/sdd-mode pointer to disambiguate." >&2
        fi
        # Fallback: suffix-based sibling heuristic (-spec → -app).
        _sdd_sib="$(_sdd_sibling_pair_root "$_sdd_primary_root" 2>/dev/null || true)"
        [ -n "$_sdd_sib" ] && IMMUTABLE_PRD_APP_CONFIG="$_sdd_sib/.immutable-prd/config.yml"
      fi
      ;;
    single)
      IMMUTABLE_PRD_SPEC_CONFIG="$IMMUTABLE_PRD_CONFIG"
      IMMUTABLE_PRD_APP_CONFIG="$IMMUTABLE_PRD_CONFIG"
      ;;
    *)
      # Unknown role — treat primary as spec for backward compat.
      IMMUTABLE_PRD_SPEC_CONFIG="$IMMUTABLE_PRD_CONFIG"
      ;;
  esac
fi

# --- 6. Resolve mode (priority: immutable-prd > legacy) ---
if [ -n "$IMMUTABLE_PRD_CONFIG" ]; then
  SDD_MODE="immutable-prd"
  IMMUTABLE_PRD_REPO_MODE="$(grep '^repo_mode:' "$IMMUTABLE_PRD_CONFIG" 2>/dev/null | head -1 | awk '{print $2}')"
  [ -z "$IMMUTABLE_PRD_REPO_MODE" ] && IMMUTABLE_PRD_REPO_MODE="two-repo"
else
  SDD_MODE="legacy"
  IMMUTABLE_PRD_REPO_MODE=""
fi

# --- 7. Emit detection summary (caller reads from variables; this is for transcripts) ---
echo "SDD_MODE=$SDD_MODE"
[ -n "$IMMUTABLE_PRD_CONFIG" ]      && echo "IMMUTABLE_PRD_CONFIG=$IMMUTABLE_PRD_CONFIG"
[ -n "$IMMUTABLE_PRD_SPEC_CONFIG" ] && echo "IMMUTABLE_PRD_SPEC_CONFIG=$IMMUTABLE_PRD_SPEC_CONFIG"
[ -n "$IMMUTABLE_PRD_APP_CONFIG" ]  && echo "IMMUTABLE_PRD_APP_CONFIG=$IMMUTABLE_PRD_APP_CONFIG"
[ -n "$IMMUTABLE_PRD_REPO_MODE" ]   && echo "IMMUTABLE_PRD_REPO_MODE=$IMMUTABLE_PRD_REPO_MODE"
[ "$SDD_AMBIGUITY_FLAG" = "1" ]     && echo "SDD_AMBIGUITY_FLAG=$SDD_AMBIGUITY_FLAG"

# Clean up internal temporaries (don't leak into caller).
unset _sdd_sibling_root_from_pwd _sdd_primary_root _sdd_spec_path _sdd_resolved _sdd_sib _SDD_REV_APP_ROOT
