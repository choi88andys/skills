#!/usr/bin/env bash
# feature_slug.test.sh — regression test for `feature_slug.sh`.
#
# WHY THIS FILE EXISTS
# `feature_slug.sh` is the handoff-contract anchor for FIVE skills — design,
# plan-review-ceo, plan-review-eng, ship, office-hours — every one of which
# composes a path as `${FEATURE_SLUG}.md`. That makes exactly one property
# load-bearing: **the slug is never empty.** CHANGELOG v0.6.1 is what an empty
# slug costs — `.claude/immutable/design/.md`, a hidden file that "could never
# match real notes", which drove `/immutable:ship` to refuse every PR.
#
# The original one-liner tried to guarantee it with a trailing
# `|| echo "no-branch"` — which cannot fire, because `git branch --show-current`
# EXITS 0 AND PRINTS NOTHING on a detached HEAD. Both branchless cases (detached
# HEAD, non-repo) therefore produced an empty slug, and the documented
# "no-branch" fallback was dead code from the day it was written.
#
# Case 3 and case 4 below are that regression. Keep the other cases too: they are
# what prove the fix stayed additive (override still wins, `/` still becomes `-`).
#
# Usage:  bash immutable/scripts/feature_slug.test.sh

set -u

SUT="$(cd "$(dirname "$0")" && pwd)/feature_slug.sh"
[ -f "$SUT" ] || { echo "cannot find feature_slug.sh next to this test"; exit 1; }

RIG="$(mktemp -d)"
trap 'rm -rf "$RIG"' EXIT

git_init() {  # $1=dir
  mkdir -p "$1"
  git -C "$1" init -q .
  git -C "$1" -c user.email=test@invalid -c user.name=test \
    commit -q --allow-empty -m "chore: seed"
}

# Resolve the slug the way a SKILL.md bash block does: source it, then read the var.
# Runs in a subshell so FEATURE_SLUG never leaks between cases.
#   $1 = cwd
#   $2 = preset FEATURE_SLUG; the sentinel "-" means "leave it unset"
slug_in() {
  (
    cd "$1" || exit 1
    # shellcheck disable=SC2030  # subshell-local by design: isolation is the point here
    if [ "$2" = "-" ]; then unset FEATURE_SLUG; else FEATURE_SLUG="$2"; fi
    # shellcheck source=/dev/null
    . "$SUT"
    # shellcheck disable=SC2031  # ditto — we read it inside the same subshell that set it
    printf '%s' "$FEATURE_SLUG"
  )
}

# Sourcing must not abort when the caller has `set -u` and FEATURE_SLUG is unset,
# which is the state every SKILL.md block sources it in.
slug_under_set_u() {
  (
    set -u
    cd "$1" || exit 1
    unset FEATURE_SLUG
    # shellcheck source=/dev/null
    . "$SUT"
    # shellcheck disable=SC2031  # set in this subshell by the source above
    printf '%s' "$FEATURE_SLUG"
  )
}

FAILURES=0
check() {  # $1=label $2=cwd $3=preset $4=expected slug
  local got
  got="$(slug_in "$2" "$3")"
  if [ "$got" = "$4" ]; then
    printf 'PASS  %s\n' "$1"
    return 0
  fi
  printf 'FAIL  %s\n' "$1"
  printf '      expected [%s]  got [%s]\n' "$4" "$got"
  FAILURES=$((FAILURES + 1))
}

# ---- rigs ----
git_init "$RIG/branchy"
git -C "$RIG/branchy" checkout -q -b feat/nested/thing

git_init "$RIG/detached"
git -C "$RIG/detached" checkout -q --detach HEAD

mkdir -p "$RIG/norepo"   # deliberately NOT a git repo

echo
echo "feature_slug.sh — slug resolution across every branchless / override case"
echo

check "branch with slashes      — '/' becomes '-'"                "$RIG/branchy"  "-"          "feat-nested-thing"
check "explicit override        — wins over the branch name"      "$RIG/branchy"  "my-feature" "my-feature"
check "detached HEAD            — no-branch (the v0.6.1 class)"   "$RIG/detached" "-"          "no-branch"
check "not a git repo           — no-branch (the v0.6.1 class)"   "$RIG/norepo"   "-"          "no-branch"
check "empty-string override    — falls through, never empty"     "$RIG/norepo"   ""           "no-branch"

# The one property every consumer depends on, asserted directly rather than
# inferred from the cases above: no reachable input yields an empty slug, because
# an empty one collapses unrelated runs onto the same hidden `.md` path.
for rig in branchy detached norepo; do
  if [ -z "$(slug_in "$RIG/$rig" "-")" ]; then
    printf 'FAIL  never-empty invariant — %s produced an EMPTY slug\n' "$rig"
    FAILURES=$((FAILURES + 1))
  fi
done

if [ "$(slug_under_set_u "$RIG/norepo" 2>/dev/null)" = "no-branch" ]; then
  printf 'PASS  %s\n' "sourced under set -u    — no abort on the unset var"
else
  printf 'FAIL  %s\n' "sourced under set -u    — no abort on the unset var"
  FAILURES=$((FAILURES + 1))
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
