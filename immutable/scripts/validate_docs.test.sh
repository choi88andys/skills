#!/usr/bin/env bash
# validate_docs.test.sh — regression test for `validate_docs.py`'s `spec_repo_path`
# resolution, across every git checkout layout that resolves it differently.
#
# Builds a throwaway two-repo SDD workspace under `mktemp -d`:
#
#   <rig>/spec-repo/                          pitches live here
#   <rig>/app-repo/                           ADRs; `spec_repo_path: ../spec-repo`
#   <rig>/app-repo-sibling-wt/                linked worktree, SIBLING layout
#   <rig>/app-repo-worktrees/cycle-1/pod-1/   linked worktree, NESTED layout
#
# WHY THIS FILE EXISTS (v0.7.8)
# `.immutable-prd/config.yml` is tracked, so it exists in every linked worktree
# too. Walk-up therefore finds it at the WORKTREE root, and a relative
# `spec_repo_path` resolves from there — correct only when the worktree happens to
# sit beside the main checkout, since only then does `../` land in the same parent
# directory. From the NESTED layout `../` is the cycle directory, so every pitch
# reference missed and the validator refused the commit with one bogus
# `references.pitches file not found` per ADR. That defect was rediscovered three
# times and fixed zero times, because nothing in this repo could catch it.
#
# The four cases below are the four distinct resolution outcomes. Keep them all:
# the sibling and main-checkout cases are what prove the fix stayed additive.
#
# Usage:  bash immutable/scripts/validate_docs.test.sh
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  bash, git, python3 + PyYAML — the same set validate_docs.py assumes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$SCRIPT_DIR/validate_docs.py"

[ -f "$VALIDATOR" ] || { echo "cannot run: $VALIDATOR not found" >&2; exit 2; }
command -v git >/dev/null 2>&1 || { echo "cannot run: git is not on PATH" >&2; exit 2; }
python3 -c 'import yaml' 2>/dev/null \
  || { echo "cannot run: validate_docs.py needs PyYAML (pip install pyyaml)" >&2; exit 2; }

RIG="$(mktemp -d)"
trap 'rm -rf "$RIG"' EXIT

SPEC="$RIG/spec-repo"
APP="$RIG/app-repo"
SIBLING_WT="$RIG/app-repo-sibling-wt"
NESTED_WT="$RIG/app-repo-worktrees/cycle-1/pod-1"

# The machine's global git identity may be unset; pass one per commit rather than
# depending on it. Branch names are never referenced — only created — so the
# host's `init.defaultBranch` cannot influence the outcome.
rig_commit() { # rig_commit <repo> <message>
  git -C "$1" add -A
  git -C "$1" -c user.email=test@invalid -c user.name=test commit -q -m "$2"
}

# --- spec repo: one allowlisted domain, one pitch ---
mkdir -p "$SPEC/.immutable-prd" "$SPEC/pitches/checkout"
cat >"$SPEC/.immutable-prd/config.yml" <<'YML'
version: 3
repo_mode: two-repo-spec
team_language: en
pitches_path: pitches/
YML
cat >"$SPEC/pitches/README.md" <<'MD'
# Pitches

| domain | description |
|---|---|
| `checkout` | checkout + payment |
MD
cat >"$SPEC/pitches/checkout/2026-01-01-card-payment.md" <<'MD'
---
type: pitch
domain: checkout
supersedes: null
deprecated: false
---

## Problem
Cards fail.
MD
git -C "$SPEC" init -q
rig_commit "$SPEC" "spec repo"

# --- app repo: ADRs referencing that pitch, via a RELATIVE spec_repo_path ---
mkdir -p "$APP/.immutable-prd" "$APP/adr"
cat >"$APP/.immutable-prd/config.yml" <<'YML'
version: 3
repo_mode: two-repo-app
team_language: en
adr_path: adr/
spec_repo_path: ../spec-repo
pitches_path_in_spec: pitches/
YML
# TWO ADRs, deliberately: the pre-v0.7.8 defect emitted one bogus violation PER
# ADR, so "exactly 1 violation" in the last case is what separates the honest
# single report from the old per-ADR noise. One ADR would not distinguish them.
for n in 1 2; do
  cat >"$APP/adr/2026-01-0$n-decision-$n.md" <<'MD'
---
type: adr
domain: checkout
supersedes: null
deprecated: false
references:
  pitches:
    - 2026-01-01-card-payment.md
---

## Decision
Use the gateway.
MD
done
git -C "$APP" init -q
rig_commit "$APP" "app repo"

git -C "$APP" worktree add -q -b sibling-wt "$SIBLING_WT"
git -C "$APP" worktree add -q -b nested-wt "$NESTED_WT"

FAILURES=0

check() { # check <label> <cwd> <expected-exit> [<expected-violation-count>]
  local label="$1" dir="$2" want_rc="$3" want_v="${4:-any}"
  local out rc got_v
  out="$(cd "$dir" && python3 "$VALIDATOR" 2>&1)" && rc=0 || rc=$?
  # The validator's tally line, e.g. "3 violation(s) found." — absent when clean.
  got_v="$(sed -n 's/^\([0-9][0-9]*\) violation(s) found\.$/\1/p' <<<"$out")"
  got_v="${got_v:-0}"

  if [ "$rc" = "$want_rc" ] && { [ "$want_v" = "any" ] || [ "$got_v" = "$want_v" ]; }; then
    printf 'PASS  %s\n' "$label"
    return 0
  fi
  printf 'FAIL  %s\n' "$label"
  printf '        want exit=%s violations=%s — got exit=%s violations=%s\n' \
    "$want_rc" "$want_v" "$rc" "$got_v"
  printf '%s\n' "$out" | sed 's/^/        | /'
  FAILURES=$((FAILURES + 1))
  return 0
}

echo "validate_docs.py — spec_repo_path resolution across checkout layouts"
echo

check "main checkout            — spec repo resolves"                  "$APP"        0
check "sibling worktree         — spec repo resolves (worked pre-fix)" "$SIBLING_WT" 0
check "nested worktree          — spec repo resolves (the v0.7.8 fix)" "$NESTED_WT"  0

# Unresolvable spec repo: ONE violation naming the paths tried — not one bogus
# `references.pitches file not found` per ADR, which is what it used to emit.
rm -rf "$SPEC"
check "nested wt, spec repo gone — ONE violation, not one per ADR"     "$NESTED_WT"  1 1

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all 4 cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
