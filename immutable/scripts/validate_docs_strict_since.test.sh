#!/usr/bin/env bash
# validate_docs_strict_since.test.sh — regression test for the `--strict-body`
# date cutoff (`--strict-since` / config `strict_body_since`), added in v0.9.0.
#
# WHY THIS FILE EXISTS
# `--strict-body` scans EVERY pitch and ADR, so switching it on in a repo with
# legacy docs lights up every file that predates a later structural requirement —
# and those docs are append-only, so they cannot simply be edited into shape. The
# cutoff grandfathers them: body checks apply only to files dated on/after it, so
# a repo enforces structure on NEW docs without rewriting history. That is a
# forward-enforcement gate, and a gate is only worth shipping if it (a) still
# catches a new bad doc, (b) genuinely exempts an old one, and (c) fails loudly
# on a bad cutoff rather than silently checking everything or nothing. The cases
# below assert exactly those, plus the inclusive boundary and the config path.
#
# The rig uses the REAL bundled `default-ko` profile (team_language: ko) — the
# same one the in-house repos load — so "fails strict-body" here means the same
# thing it means in production: an ADR missing the profile's required sections.
# Domain `_global` is reserved adr_only, so the fixtures need no pitch reference
# and no allowlist row; the ONLY violation they can produce is the body check.
#
# Usage:  bash immutable/scripts/validate_docs_strict_since.test.sh
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  python3 + PyYAML — no git (no worktree/spec resolution is exercised).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$SCRIPT_DIR/validate_docs.py"

[ -f "$VALIDATOR" ] || { echo "cannot run: $VALIDATOR not found" >&2; exit 2; }
python3 -c 'import yaml' 2>/dev/null \
  || { echo "cannot run: validate_docs.py needs PyYAML (pip install pyyaml)" >&2; exit 2; }
# The rig loads the plugin's bundled default-ko profile via team_language; if it
# is not beside the validator the whole premise (real required sections) is gone.
[ -f "$SCRIPT_DIR/../examples/_profiles/default-ko.yml" ] \
  || { echo "cannot run: bundled default-ko profile not found beside the script" >&2; exit 2; }

RIG="$(mktemp -d)"
trap 'rm -rf "$RIG"' EXIT

APP="$RIG/app-repo"
mkdir -p "$APP/.immutable-prd" "$APP/adr"

write_config() { # write_config [<strict_body_since value>]
  {
    echo "version: 3"
    echo "repo_mode: two-repo-app"
    echo "team_language: ko"
    echo "adr_path: adr/"
    # `if`, not `[ ] && echo`: the latter returns 1 when no arg is passed, which
    # under `set -e` would kill the caller. An unentered `if` returns 0.
    if [ "$#" -ge 1 ]; then echo "strict_body_since: $1"; fi
  } >"$APP/.immutable-prd/config.yml"
}

# Two ADRs, both deliberately FAIL strict-body (a single `## Nope` heading, none
# of default-ko's required sections). domain `_global` keeps them otherwise clean.
write_failing_adr() { # write_failing_adr <yyyy-mm-dd> <slug>
  cat >"$APP/adr/$1-$2.md" <<'MD'
---
type: adr
domain: _global
supersedes: null
deprecated: false
---

## Nope
This body has none of the required sections, so strict-body must flag it —
unless the cutoff exempts it as legacy.
MD
}

OLD="adr/2026-01-01-old-decision.md"
NEW="adr/2026-12-01-new-decision.md"
write_config
write_failing_adr 2026-01-01 old-decision
write_failing_adr 2026-12-01 new-decision

FAILURES=0

# run <cwd> <args...> → sets OUT, RC
run() {
  local dir="$1"; shift
  OUT="$(cd "$dir" && python3 "$VALIDATOR" "$@" 2>&1)" && RC=0 || RC=$?
}

# assert <label> <want_rc> <spec...>
#   spec tokens: has:<substr> | no:<substr>  (checked against combined stdout+stderr)
assert() {
  local label="$1" want_rc="$2"; shift 2
  local ok=1 t
  [ "$RC" = "$want_rc" ] || ok=0
  for t in "$@"; do
    case "$t" in
      has:*) grep -qF -- "${t#has:}" <<<"$OUT" || ok=0 ;;
      no:*)  grep -qF -- "${t#no:}"  <<<"$OUT" && ok=0 ;;
    esac
  done
  if [ "$ok" = 1 ]; then printf 'PASS  %s\n' "$label"; return 0; fi
  printf 'FAIL  %s\n' "$label"
  printf '        want rc=%s (+ %s) — got rc=%s\n' "$want_rc" "$*" "$RC"
  printf '%s\n' "$OUT" | sed 's/^/        | /'
  FAILURES=$((FAILURES + 1))
}

echo "validate_docs.py — --strict-body date cutoff (strict-since)"
echo

# 1. No cutoff: unchanged behaviour — every file is checked, both fail.
run "$APP" --strict-body
assert "no cutoff — both files checked (backward compatible)" 1 "has:$OLD" "has:$NEW"

# 2. Cutoff between the two dates: the old file is exempt, the new one still fails.
run "$APP" --strict-body --strict-since 2026-06-01
assert "cutoff 2026-06-01 — old exempt, new enforced" 1 "no:$OLD" "has:$NEW" "has:1 legacy file(s) exempt"

# 3. Cutoff EQUAL to the new file's date: inclusive — the new file is still checked.
run "$APP" --strict-body --strict-since 2026-12-01
assert "cutoff == new date — boundary is inclusive, new enforced" 1 "no:$OLD" "has:$NEW"

# 4. Cutoff after both: everything is legacy, the gate goes green — and says so.
run "$APP" --strict-body --strict-since 2027-01-01
assert "cutoff after all — all exempt, exits clean" 0 "has:all checks passed" "has:2 legacy file(s) exempt"

# 5. Cutoff from CONFIG (strict_body_since), no CLI flag: same scoping.
write_config 2026-06-01
run "$APP" --strict-body
assert "config strict_body_since — old exempt, new enforced" 1 "no:$OLD" "has:$NEW"
write_config  # reset to no cutoff

# 6. Malformed cutoff (impossible date): fatal, and NOTHING is checked.
run "$APP" --strict-body --strict-since 2026-13-01
assert "impossible date — dies loudly, checks nothing" 1 "has:error:" "has:not a real calendar date" "no:$NEW"

# 7. Malformed cutoff (wrong shape): fatal with the shape message.
run "$APP" --strict-body --strict-since nonsense
assert "non-date cutoff — dies with the shape message" 1 "has:error:" "has:zero-padded YYYY-MM-DD"

# 8. --strict-since without --strict-body: warns, and enforces nothing.
run "$APP" --strict-since 2026-06-01
assert "strict-since without strict-body — warns, no enforcement" 0 "has:warning:" "has:no effect" "no:$NEW"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all 8 cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
