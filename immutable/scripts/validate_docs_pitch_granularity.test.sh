#!/usr/bin/env bash
# validate_docs_pitch_granularity.test.sh — regression test for the v0.17 body
# rules that replaced the pitch size caps: cross-pitch references and the byte
# ceiling (SCHEMA.md "Validation invariants" 10 and 11).
#
# WHY THIS FILE EXISTS (v0.17.0)
# In lounge-x-spec (2026-11-06) a sibling pitch outranked one clause of a
# baseline with a sentence naming the baseline's FILE (「그 조항에 한해 … 우선한다」).
# A later supersede of the baseline could not see that sentence and copied the
# clause back: two live pitches demanded 4 and 3 payment-auth methods. The
# validator now refuses a body line that names another pitch's path together
# with a profile `precedence_keywords` phrase (R1-R3), and a citation whose
# supersede chain reaches no active pitch or that names no pitch (R7, R8). A citation of an OLDER version
# whose chain still ends in one active pitch is NOT a violation — it names the
# chain, the read guard hands the reader its successor, and failing it would make
# every supersede re-version every citer (29 of 71 lounge-x-spec pitches cite an
# older version). It is counted on stderr, and a forked chain is named (R5, R6).
# The size caps (`max_items`, `anti_monolith`) are gone; one machine limit stays,
# `max_bytes`, because Claude Code's Read returns a partial page past about 55 KB
# of Korean pitch text (Z1-Z3). Both rules are body rules: --strict-body only,
# the --strict-since scope applies, and a deprecated pitch is frozen (S1-S3).
# A team profile predating the fields reads the bundled default's (P1-P2).
#
# Usage:  bash immutable/scripts/validate_docs_pitch_granularity.test.sh
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  python3 + PyYAML — no git.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$SCRIPT_DIR/validate_docs.py"

[ -f "$VALIDATOR" ] || { echo "cannot run: $VALIDATOR not found" >&2; exit 2; }
python3 -c 'import yaml' 2>/dev/null \
  || { echo "cannot run: validate_docs.py needs PyYAML (pip install pyyaml)" >&2; exit 2; }

RIG="$(mktemp -d)"
trap 'rm -rf "$RIG"' EXIT
RIG="$(cd "$RIG" && pwd)"

mkrepo() {  # mkrepo <dir> <profile body...> — spec repo, domains alpha/beta, team profile
  local d="$1"; shift
  mkdir -p "$d/.immutable-prd" "$d/pitches/alpha" "$d/pitches/beta"
  cat >"$d/.immutable-prd/config.yml" <<'YML'
version: 3
repo_mode: two-repo-spec
team_language: en
pitches_path: pitches/
profile: .immutable-prd/profile.yml
YML
  printf '%s\n' 'profile_schema: 8' 'locale: en' "$@" >"$d/.immutable-prd/profile.yml"
  cat >"$d/pitches/README.md" <<'MD'
| domain | description |
|---|---|
| `alpha` | first |
| `beta` | second |
MD
}

mkpitch() {  # mkpitch <path> <supersedes> <deprecated> <body line>...
  local p="$1" sup="$2" dep="$3"; shift 3
  local dom; dom="$(basename "$(dirname "$p")")"
  { printf '%s\n' '---' "domain: $dom" "supersedes: $sup" "deprecated: $dep" '---' '' '# Title' ''
    printf '%s\n' "$@"; } >"$p"
}

FAILURES=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }

run() {  # run <repo> [extra args...] -> OUT (stdout+stderr), RC, GOT_V
  local repo="$1"; shift
  OUT=$(python3 "$VALIDATOR" --config "$repo/.immutable-prd/config.yml" --type pitch "$@" 2>&1) && RC=0 || RC=$?
  GOT_V="$(sed -n 's/^\([0-9][0-9]*\) violation(s) found\.$/\1/p' <<<"$OUT")"
  GOT_V="${GOT_V:-0}"
}

KW='precedence_keywords: ["takes precedence", "overrides", "우선한다"]'

# --- repo R: references ---
R="$RIG/refs"; mkrepo "$R" "$KW" 'max_bytes: 50000'
A="$R/pitches/alpha"; B="$R/pitches/beta"
mkpitch "$A/2026-02-01-base.md"        null false 'The base rule.'
mkpitch "$A/2026-01-01-old.md"         null true  'Superseded once.'
mkpitch "$A/2026-02-02-old.md"         2026-01-01-old.md false 'Its live version.'
mkpitch "$A/2026-01-01-gone.md"        null true  'Deprecated, nothing supersedes it.'
mkpitch "$A/2026-01-01-split.md"       null true  'Split in two.'
mkpitch "$A/2026-02-03-split-one.md"   2026-01-01-split.md false 'Half one.'
mkpitch "$A/2026-02-03-split-two.md"   2026-01-01-split.md false 'Half two.'
mkpitch "$A/2026-01-01-prev.md"        null true  'The version the successor replaces.'
mkpitch "$A/2026-02-04-price-overrides.md" null false 'A pitch whose slug holds a keyword.'
# A chain whose successor is itself deprecated with nothing after it: dead, two hops out.
mkpitch "$A/2026-01-01-hop.md"         null true  'First version.'
mkpitch "$A/2026-01-15-hop.md"         2026-01-01-hop.md true 'Second version, later retired.'
# R1: the incident — names another pitch and outranks it (inflected Korean keyword).
mkpitch "$B/2026-03-01-override.md"    null false \
  'For that clause only, this pitch `pitches/alpha/2026-02-01-base.md` 보다 우선한다고 밝힌다.'
# R2: English keyword, case-insensitive.
mkpitch "$B/2026-03-02-override-en.md" null false \
  'This Takes Precedence over pitches/alpha/2026-02-01-base.md on the method list.'
# R3: a keyword on a line naming only the pitch's OWN supersedes target, a keyword on
# a line with no path, a path with no keyword, and both inside a fence — all clean.
mkpitch "$A/2026-03-03-successor.md"   2026-01-01-prev.md false \
  'This version overrides `pitches/alpha/2026-01-01-prev.md` where it differs.' \
  'The new token overrides the old one.' \
  'The base rule is owned by `pitches/alpha/2026-02-01-base.md`.' \
  '```' 'pitches/alpha/2026-02-01-base.md takes precedence (example only)' '```'
# R4: a keyword inside a cited slug is a name, not an override (review catch).
mkpitch "$B/2026-03-08-cites-slug.md" null false 'Price rules are owned by `pitches/alpha/2026-02-04-price-overrides.md`.'
# R5 / R6 / R7 / R8: citation targets.
mkpitch "$B/2026-03-04-cites-old.md"   null false 'Owned by `pitches/alpha/2026-01-01-old.md`.'
mkpitch "$B/2026-03-05-cites-split.md" null false 'Owned by `pitches/alpha/2026-01-01-split.md`.'
mkpitch "$B/2026-03-06-cites-gone.md"  null false 'Owned by `pitches/alpha/2026-01-01-gone.md`.' \
  'Also by `pitches/alpha/2026-01-01-hop.md`.'
mkpitch "$B/2026-03-07-cites-ghost.md" null false 'Owned by `pitches/alpha/2026-01-01-ghost.md`.' \
  'The domain list is `pitches/README.md`; the domain README `pitches/alpha/README.md` is no pitch.'

run "$R" --strict-body

if grep -qF '2026-03-01-override.md: cross-pitch reference violation' <<<"$OUT" \
  && grep -qF 'names `pitches/alpha/2026-02-01-base.md` and says "우선한다"' <<<"$OUT"; then
  pass "R1 a line naming another pitch with a precedence keyword fails"
else
  fail "R1 precedence line" "$OUT"
fi
if grep -qF '2026-03-02-override-en.md: cross-pitch reference violation' <<<"$OUT" \
  && grep -qF 'says "takes precedence"' <<<"$OUT"; then
  pass "R2 keywords match case-insensitively"
else
  fail "R2 case-insensitive keyword" "$OUT"
fi
if ! grep -qF '2026-03-03-successor.md' <<<"$OUT"; then
  pass "R3 own supersedes target, keyword without a path, path without a keyword, fenced: clean"
else
  fail "R3 exemptions" "$OUT"
fi
if ! grep -qF '2026-03-08-cites-slug.md' <<<"$OUT"; then
  pass "R4 a keyword inside a cited pitch's slug is not an override"
else
  fail "R4 keyword in slug" "$OUT"
fi
if ! grep -qF '2026-03-04-cites-old.md: cross' <<<"$OUT" \
  && grep -qF 'note: 2 citation(s) name an older version of a pitch' <<<"$OUT"; then
  pass "R5 a citation of an older version with one live end passes, counted on stderr"
else
  fail "R5 older-version citation" "$OUT"
fi
if ! grep -qF '2026-03-05-cites-split.md: cross' <<<"$OUT" \
  && grep -qF '1 of them fork into several active pitches' <<<"$OUT" \
  && grep -qF '2026-03-05-cites-split.md -> alpha/2026-01-01-split.md -> 2026-02-03-split-one.md, 2026-02-03-split-two.md' <<<"$OUT"; then
  pass "R6 a forked chain passes and is named"
else
  fail "R6 forked citation" "$OUT"
fi
if grep -qF '2026-03-06-cites-gone.md: cross-pitch reference violation' <<<"$OUT" \
  && grep -qF 'cites `pitches/alpha/2026-01-01-gone.md`, which is deprecated, and its supersede chain reaches no active pitch' <<<"$OUT" \
  && grep -qF 'cites `pitches/alpha/2026-01-01-hop.md`, which is deprecated, and its supersede chain reaches no active pitch' <<<"$OUT"; then
  pass "R7 a citation whose chain reaches no active pitch fails, however many hops out"
else
  fail "R7 dead chain" "$OUT"
fi
if grep -qF 'cites `pitches/alpha/2026-01-01-ghost.md`, which is not a pitch in this repo' <<<"$OUT" \
  && ! grep -qF 'README.md`, which' <<<"$OUT"; then
  pass "R8 a citation of a missing pitch fails; README paths are no citation"
else
  fail "R8 missing target" "$OUT"
fi
if [ "$RC" -eq 1 ] && [ "$GOT_V" = "4" ]; then
  pass "R9 exactly the four offending pitches"
else
  fail "R9 tally" "rc=$RC violations=$GOT_V
$OUT"
fi

# S1-S3: scope. No --strict-body → no reference rule. --strict-since exempts older
# citers. A deprecated citer is frozen.
run "$R"
if [ "$RC" -eq 0 ]; then pass "S1 without --strict-body the body rules do not run"; else fail "S1 off without --strict-body" "$OUT"; fi
run "$R" --strict-body --strict-since 2026-03-03
if [ "$RC" -eq 1 ] && [ "$GOT_V" = "2" ] && ! grep -qF '2026-03-01-override.md' <<<"$OUT" \
  && ! grep -qF '2026-03-02-override-en.md' <<<"$OUT"; then
  pass "S2 --strict-since exempts citers dated before the cutoff"
else
  fail "S2 strict-since scope" "rc=$RC violations=$GOT_V
$OUT"
fi
sed -i.bak 's/^deprecated: false$/deprecated: true/' "$B/2026-03-06-cites-gone.md"; rm "$B/2026-03-06-cites-gone.md.bak"
run "$R" --strict-body --strict-since 2026-03-03
if [ "$GOT_V" = "1" ] && ! grep -qF '2026-03-06-cites-gone.md' <<<"$OUT"; then
  pass "S3 a deprecated citer is frozen"
else
  fail "S3 frozen citer" "rc=$RC violations=$GOT_V
$OUT"
fi

# --- repo Z: the byte ceiling ---
Z="$RIG/size"; mkrepo "$Z" "$KW" 'max_bytes: 400'
BIG="$(python3 -c 'print("x" * 500)')"
mkpitch "$Z/pitches/alpha/2026-02-01-small.md" null false 'Small.'
mkpitch "$Z/pitches/alpha/2026-02-02-big.md"   null false "$BIG"
mkpitch "$Z/pitches/alpha/2026-01-01-dead-big.md" null true "$BIG"
mkpitch "$Z/pitches/alpha/2026-01-01-old-big.md"  null false "$BIG"
run "$Z" --strict-body --strict-since 2026-02-01
if [ "$RC" -eq 1 ] && [ "$GOT_V" = "1" ] && grep -qE '2026-02-02-big\.md: [0-9]+ bytes, over max_bytes 400' <<<"$OUT"; then
  pass "Z1 an active pitch over max_bytes fails; deprecated and pre-cutoff ones do not"
else
  fail "Z1 max_bytes" "rc=$RC violations=$GOT_V
$OUT"
fi
printf '%s\n' 'profile_schema: 8' 'locale: en' "$KW" 'max_bytes: "big"' >"$Z/.immutable-prd/profile.yml"
run "$Z" --strict-body --strict-since 2026-02-01
if [ "$RC" -eq 1 ] && grep -qF "active profile: max_bytes must be a positive integer, got 'big'" <<<"$OUT" \
  && ! grep -qF 'over max_bytes' <<<"$OUT"; then
  pass "Z2 a malformed max_bytes is a violation and the 50000 default applies"
else
  fail "Z2 malformed max_bytes" "rc=$RC
$OUT"
fi
printf '%s\n' 'profile_schema: 8' 'locale: en' "$KW" 'max_bytes: 0' >"$Z/.immutable-prd/profile.yml"
run "$Z" --strict-body --strict-since 2026-02-01
if [ "$RC" -eq 1 ] && grep -qF 'max_bytes must be a positive integer, got 0' <<<"$OUT"; then
  pass "Z3 max_bytes: 0 does not switch the ceiling off"
else
  fail "Z3 zero max_bytes" "rc=$RC
$OUT"
fi
head -c 51000 /dev/zero | tr '\0' 'y' >"$RIG/fill.txt"
mkpitch "$Z/pitches/alpha/2026-02-03-huge.md" null false "$(cat "$RIG/fill.txt")"

# --- P1-P2: a team profile predating the fields reads the bundled default's ---
printf '%s\n' 'profile_schema: 7' 'locale: en' >"$Z/.immutable-prd/profile.yml"
run "$Z" --strict-body --strict-since 2026-02-01
if grep -qF 'note: the active profile has no max_bytes / precedence_keywords (profile_schema 8)' <<<"$OUT" \
  && grep -qE '2026-02-03-huge\.md: [0-9]+ bytes, over max_bytes 50000' <<<"$OUT" \
  && ! grep -qF '2026-02-02-big.md:' <<<"$OUT"; then
  pass "P1 no max_bytes in the team profile → the bundled 50000, said on stderr"
else
  fail "P1 bundled max_bytes fallback" "rc=$RC
$OUT"
fi
P="$RIG/prefs"; mkrepo "$P"
mkpitch "$P/pitches/alpha/2026-02-01-base.md" null false 'Base.'
mkpitch "$P/pitches/beta/2026-02-02-over.md"  null false 'It overrides pitches/alpha/2026-02-01-base.md.'
run "$P" --strict-body
if [ "$RC" -eq 1 ] && grep -qF 'says "overrides"' <<<"$OUT"; then
  pass "P2 no precedence_keywords in the team profile → the bundled list"
else
  fail "P2 bundled keyword fallback" "rc=$RC
$OUT"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
