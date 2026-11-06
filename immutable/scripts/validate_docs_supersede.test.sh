#!/usr/bin/env bash
# validate_docs_supersede.test.sh — regression test for how invariant 2
# (supersede chain integrity) resolves a `supersedes:` target, per doc type.
#
# WHY THIS FILE EXISTS (v0.15.1)
# Until v0.15.1 every supersede edge was resolved by the pair (domain, filename).
# That key is right for pitches, which live in per-domain directories where the
# same filename legitimately repeats (`checkout/2026-01-01-initial.md` beside
# `payments/2026-01-01-initial.md`). It was wrong for ADRs, which live in ONE
# flat directory, so a filename already names exactly one ADR: the domain bought
# no disambiguation and made a chain whose subject legitimately moved to another
# domain unresolvable by construction. A consumer hit it on a real chain whose
# root decided two domains at once (choi88andys/Water-Submersion#130): filing
# the successor under the domain its subject belongs to failed with
# "target file not found ... under domain", and no filing was subject-clean.
#
# Pinned below: an ADR target resolves by filename across domains (S1), the
# widening touched only resolution, not the deprecation rule (S2) or the
# missing-target report (S3); pitches keep (domain, filename) — twins in two
# domains stay distinct (S4, which a filename-only key fails in either glob
# order) and a cross-domain pitch edge stays unresolvable (S5).
#
# FAN-IN (v0.17): a pitch may fold several pitches of its own domain into one,
# `supersedes: [a.md, b.md]`. Before v0.17 a list reached the chain check as a
# dict key and crashed the validator (`TypeError: unhashable type: 'list'`).
# Pinned: a fold of two deprecated pitches is clean (F1); each listed edge is
# judged on its own — an active or missing member fails, a cross-domain member
# stays unresolvable (F2); malformed lists are reported, never crash (F3); an
# ADR list is a violation, since fan-in is pitch-only (F4).
#
# Usage:  bash immutable/scripts/validate_docs_supersede.test.sh
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
# macOS TMPDIR carries a trailing slash; normalize so printed paths compare.
RIG="$(cd "$RIG" && pwd)"

mkrepo() {  # mkrepo <dir> — single-repo layout, domains `alpha` and `beta`
  mkdir -p "$1/.immutable-prd" "$1/pitches/alpha" "$1/pitches/beta" "$1/adr"
  cat >"$1/.immutable-prd/config.yml" <<'YML'
version: 3
repo_mode: single-repo
team_language: en
pitches_path: pitches/
adr_path: adr/
YML
  cat >"$1/pitches/README.md" <<'MD'
# Pitches

| domain | description |
|---|---|
| `alpha` | first domain |
| `beta` | second domain |
MD
}

mkdoc() {  # mkdoc <path> <line>...
  local p="$1"; shift
  printf '%s\n' "$@" > "$p"
}

mkadr() {  # mkadr <path> <domain> <supersedes> <deprecated> — cites the repo's one pitch
  mkdoc "$1" '---' 'type: adr' "domain: $2" "supersedes: $3" "deprecated: $4" \
    'references:' '  pitches:' '    - 2026-01-01-feature.md' '---' '' 'Decision.'
}

mkpitch() {  # mkpitch <path> <domain> <supersedes> <deprecated>
  mkdoc "$1" '---' 'type: pitch' "domain: $2" "supersedes: $3" "deprecated: $4" '---' '' 'Promise.'
}

# --- repo A: an ADR chain that moves from alpha to beta, predecessor deprecated ---
A="$RIG/adr-chain"; mkrepo "$A"
mkpitch "$A/pitches/alpha/2026-01-01-feature.md" alpha null false
mkadr "$A/adr/2026-01-01-root.md"      alpha null               true
mkadr "$A/adr/2026-01-02-successor.md" beta  2026-01-01-root.md false

# --- repo B: ADR edges that must still fail after the widening ---
B="$RIG/adr-negatives"; mkrepo "$B"
mkpitch "$B/pitches/alpha/2026-01-01-feature.md" alpha null false
mkadr "$B/adr/2026-01-01-live-root.md"  alpha null                          false
mkadr "$B/adr/2026-01-02-over-live.md"  beta  2026-01-01-live-root.md       false
mkadr "$B/adr/2026-01-03-dangling.md"   beta  2026-01-01-does-not-exist.md  false

# --- repo C: pitches, where the same filename lives in two domains ---
C="$RIG/pitch-twins"; mkrepo "$C"
mkpitch "$C/pitches/alpha/2026-01-01-initial.md"    alpha null                     true
mkpitch "$C/pitches/beta/2026-01-01-initial.md"     beta  null                     false
mkpitch "$C/pitches/alpha/2026-01-02-next.md"       alpha 2026-01-01-initial.md    false
mkpitch "$C/pitches/beta/2026-01-02-next.md"        beta  2026-01-01-initial.md    false
mkpitch "$C/pitches/alpha/2026-01-01-alpha-only.md" alpha null                     true
mkpitch "$C/pitches/beta/2026-01-03-cross.md"       beta  2026-01-01-alpha-only.md false

# --- repo F: fan-in (a fold) ---
F="$RIG/fan-in"; mkrepo "$F"
mkpitch "$F/pitches/alpha/2026-01-01-a.md" alpha null true
mkpitch "$F/pitches/alpha/2026-01-01-b.md" alpha null true
mkpitch "$F/pitches/alpha/2026-01-02-fold.md" alpha '[2026-01-01-a.md, 2026-01-01-b.md]' false

# --- repo G: fan-in edges that must fail ---
G="$RIG/fan-in-negatives"; mkrepo "$G"
mkpitch "$G/pitches/alpha/2026-01-01-dead.md"   alpha null true
mkpitch "$G/pitches/alpha/2026-01-01-live.md"   alpha null false
mkpitch "$G/pitches/beta/2026-01-01-other.md"   beta  null true
mkpitch "$G/pitches/alpha/2026-01-02-fold.md"   alpha '[2026-01-01-dead.md, 2026-01-01-live.md, 2026-01-01-other.md, 2026-01-01-ghost.md]' false

# --- repo H: malformed lists, and an ADR list ---
H="$RIG/fan-in-malformed"; mkrepo "$H"
mkpitch "$H/pitches/alpha/2026-01-01-dead.md"   alpha null true
mkpitch "$H/pitches/alpha/2026-01-02-empty.md"  alpha '[]' false
mkpitch "$H/pitches/alpha/2026-01-03-twice.md"  alpha '[2026-01-01-dead.md, 2026-01-01-dead.md]' false
mkpitch "$H/pitches/alpha/2026-01-04-mixed.md"  alpha '[2026-01-01-dead.md, 7]' false
mkpitch "$H/pitches/alpha/2026-01-01-feature.md" alpha null false
mkadr "$H/adr/2026-01-01-one.md"  alpha null true
mkadr "$H/adr/2026-01-01-two.md"  alpha null true
mkadr "$H/adr/2026-01-02-both.md" alpha '[2026-01-01-one.md, 2026-01-01-two.md]' false

FAILURES=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }

run() {  # run <repo> -> stdout+stderr in OUT, rc in RC, violation tally in GOT_V
  OUT=$(python3 "$VALIDATOR" --config "$1/.immutable-prd/config.yml" 2>&1) && RC=0 || RC=$?
  GOT_V="$(sed -n 's/^\([0-9][0-9]*\) violation(s) found\.$/\1/p' <<<"$OUT")"
  GOT_V="${GOT_V:-0}"
}

echo "validate_docs.py — supersede target resolution per doc type"
echo

# S1 — the defect: an ADR successor in another domain finds its predecessor.
run "$A"
if [ "$RC" -eq 0 ] && grep -qF 'all checks passed.' <<<"$OUT"; then
  pass "S1 ADR chain crossing domains resolves (filename alone)"
else
  fail "S1 cross-domain ADR chain" "rc=$RC violations=$GOT_V
$OUT"
fi

# S2 + S3 — only resolution widened: an active cross-domain target still fails
# the deprecation rule, and a missing target is still reported (no domain named,
# since none scoped the search).
run "$B"
if [ "$RC" -eq 1 ] && [ "$GOT_V" = "2" ] \
  && grep -qF '2026-01-02-over-live.md: supersedes `2026-01-01-live-root.md` but target is still active' <<<"$OUT"; then
  pass "S2 cross-domain ADR edge to an ACTIVE target still fails"
else
  fail "S2 deprecation rule across domains" "rc=$RC violations=$GOT_V
$OUT"
fi
if grep -qF '2026-01-03-dangling.md: supersedes `2026-01-01-does-not-exist.md` but target file not found in adr set' <<<"$OUT" \
  && ! grep -qF 'not found in adr set under domain' <<<"$OUT"; then
  pass "S3 missing ADR target reported, no domain in the message"
else
  fail "S3 missing ADR target" "$OUT"
fi

# S4 — pitch twins stay distinct. alpha's twin is deprecated, beta's is active,
# and each domain's `2026-01-02-next.md` supersedes `2026-01-01-initial.md`:
# only beta's edge may fail. A filename-only key resolves both edges to the SAME
# twin, so it reports either zero of these or two, whatever the glob order.
run "$C"
if grep -qF 'beta/2026-01-02-next.md: supersedes `2026-01-01-initial.md` but target is still active' <<<"$OUT" \
  && ! grep -qF 'alpha/2026-01-02-next.md' <<<"$OUT"; then
  pass "S4 same pitch filename in two domains resolves per domain"
else
  fail "S4 pitch twins" "rc=$RC violations=$GOT_V
$OUT"
fi

# S5 — a cross-domain pitch edge stays unresolvable, message unchanged, and the
# repo's tally is exactly S4's edge plus this one.
if [ "$RC" -eq 1 ] && [ "$GOT_V" = "2" ] \
  && grep -qF 'beta/2026-01-03-cross.md: supersedes `2026-01-01-alpha-only.md` but target file not found in pitch set under domain `beta`' <<<"$OUT"; then
  pass "S5 cross-domain pitch edge still not found (domain-scoped)"
else
  fail "S5 cross-domain pitch edge" "rc=$RC violations=$GOT_V
$OUT"
fi

# F1 — a fold of two deprecated pitches is clean.
run "$F"
if [ "$RC" -eq 0 ] && grep -qF 'all checks passed.' <<<"$OUT"; then
  pass "F1 fan-in of two deprecated pitches resolves"
else
  fail "F1 fan-in" "rc=$RC violations=$GOT_V
$OUT"
fi

# F2 — each listed edge on its own: active, cross-domain and missing members fail.
run "$G"
if [ "$RC" -eq 1 ] && [ "$GOT_V" = "3" ] && ! grep -qF 'Traceback' <<<"$OUT" \
  && grep -qF 'supersedes `2026-01-01-live.md` but target is still active' <<<"$OUT" \
  && grep -qF 'supersedes `2026-01-01-other.md` but target file not found in pitch set under domain `alpha`' <<<"$OUT" \
  && grep -qF 'supersedes `2026-01-01-ghost.md` but target file not found' <<<"$OUT" \
  && ! grep -qF '2026-01-01-dead.md` but' <<<"$OUT"; then
  pass "F2 fan-in judges every member; cross-domain stays unresolvable"
else
  fail "F2 fan-in negatives" "rc=$RC violations=$GOT_V
$OUT"
fi

# F3 + F4 — malformed lists and an ADR list are reported, never a crash.
run "$H"
if [ "$RC" -eq 1 ] && [ "$GOT_V" = "4" ] && ! grep -qF 'Traceback' <<<"$OUT" \
  && grep -qF '2026-01-02-empty.md: `supersedes: []`' <<<"$OUT" \
  && grep -qF '2026-01-03-twice.md: `supersedes` names 2026-01-01-dead.md more than once' <<<"$OUT" \
  && grep -qF '2026-01-04-mixed.md: every `supersedes` entry must be a filename' <<<"$OUT"; then
  pass "F3 malformed pitch lists reported (empty, duplicate, non-string)"
else
  fail "F3 malformed lists" "rc=$RC violations=$GOT_V
$OUT"
fi
if grep -qF '2026-01-02-both.md: `supersedes` lists 2 files; an ADR supersedes one file' <<<"$OUT"; then
  pass "F4 an ADR list is a violation, not a crash"
else
  fail "F4 ADR list" "$OUT"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all 9 cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
