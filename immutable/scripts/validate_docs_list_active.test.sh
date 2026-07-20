#!/usr/bin/env bash
# validate_docs_list_active.test.sh — regression test for `--list-active`, the
# active-doc resolver added in v0.10.0, and for the scalar-frontmatter parse fix
# that shipped with it.
#
# WHY THIS FILE EXISTS
# Before v0.10.0 the flow skills picked "active" pitches with a line grep
# (`grep -L '^deprecated: true'`), which is wrong in BOTH directions on real
# YAML: `deprecated: True` and `deprecated:  true` are live YAML the grep reads
# as ACTIVE (a dead spec offered for implementation), and a fenced example body
# line starting `deprecated: true` reads as DEPRECATED (a live pitch silently
# dropped from every picker). `--list-active` replaces that with the same
# PyYAML parse the validator uses everywhere; the cases below pin both
# directions, the fail-open contract for unparseable frontmatter (a live doc
# is never silently dropped — it lists with domain `-` and a stderr warning),
# and the exact output format the skills consume (`<path>` TAB `<domain>`,
# sorted, README/TEMPLATE excluded).
#
# Also pinned here: `load_frontmatter` used to return a SCALAR for frontmatter
# like `---\njust text\n---` (yaml.safe_load parses it fine), which crashed
# `check_frontmatter` with an AttributeError — a traceback instead of a
# violation. It now reports as malformed frontmatter, and the lister lists the
# file fail-open.
#
# Usage:  bash immutable/scripts/validate_docs_list_active.test.sh
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
# macOS TMPDIR carries a trailing slash → mktemp yields `.../T//x`, while the
# validator prints python-normalized paths; normalize or every exact-output
# comparison mismatches on pure string inequality.
RIG="$(cd "$RIG" && pwd)"

REPO="$RIG/repo"
P="$REPO/pitches"
mkdir -p "$REPO/.immutable-prd" "$P/checkout" "$P/payments" "$REPO/adr"

cat >"$REPO/.immutable-prd/config.yml" <<'YML'
version: 3
repo_mode: single-repo
team_language: en
pitches_path: pitches/
adr_path: adr/
YML

mkdoc() {  # mkdoc <path> <line>...
  local p="$1"; shift
  printf '%s\n' "$@" > "$p"
}

# --- pitches: every deprecation spelling the resolver must judge correctly ---
mkdoc "$P/checkout/2026-01-01-dead.md"   '---' 'domain: checkout' 'supersedes: null' 'deprecated: true' '---' '' 'Dead body.'
mkdoc "$P/checkout/2026-01-02-live.md"   '---' 'domain: checkout' 'supersedes: 2026-01-01-dead.md' 'deprecated: false' '---' '' 'Live body.'
mkdoc "$P/checkout/2026-01-03-cap.md"    '---' 'domain: checkout' 'supersedes: null' 'deprecated: True' '---' '' 'Capital-True body.'
mkdoc "$P/checkout/2026-01-04-spaced.md" '---' 'domain: checkout' 'supersedes: null' 'deprecated:  true' '---' '' 'Double-space body.'
mkdoc "$P/checkout/2026-01-05-fenced.md" '---' 'domain: checkout' 'supersedes: null' 'deprecated: false' '---' '' \
  'A schema example follows:' '' '```yaml' 'deprecated: true' '```'
mkdoc "$P/checkout/2026-01-07-broken.md" '---' 'domain: checkout' 'bad: [unclosed' '---' '' 'Unparseable-frontmatter body.'
mkdoc "$P/checkout/2026-01-10-scalar.md" '---' 'just a scalar, not a mapping' '---' '' 'Scalar-frontmatter body.'
mkdoc "$P/payments/2026-01-06-refund.md" '---' 'domain: payments' 'supersedes: null' 'deprecated: false' '---' '' 'Refund body.'
# Excluded by NAME at any level, whatever their frontmatter says:
mkdoc "$P/README.md"            'Domain table deliberately absent (keeps the allowlist check inert).'
mkdoc "$P/checkout/TEMPLATE.md" '---' 'domain: checkout' 'supersedes: null' 'deprecated: false' '---' '' 'Template body.'

# --- ADRs: `_global` is adr_only-reserved, so empty references stay clean ---
mkdoc "$REPO/adr/2026-01-08-gateway.md" '---' 'type: adr' 'domain: _global' 'supersedes: null' 'deprecated: false' '---' '' 'Use the gateway.'
mkdoc "$REPO/adr/2026-01-09-old.md"     '---' 'type: adr' 'domain: _global' 'supersedes: null' 'deprecated: true' '---' '' 'Old decision.'

FAILURES=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }

CFG="$REPO/.immutable-prd/config.yml"
list() {  # list <extra args...> -> stdout in LIST_OUT, stderr in LIST_ERR, rc in LIST_RC
  LIST_OUT=$(python3 "$VALIDATOR" --config "$CFG" "$@" 2>"$RIG/stderr.txt") && LIST_RC=0 || LIST_RC=$?
  LIST_ERR=$(cat "$RIG/stderr.txt")
}

echo "validate_docs.py --list-active — resolver contract"
echo

# C1 — exact output: every active doc, sorted, `<path>\t<domain>`, `-` for unknown,
# README/TEMPLATE absent, pitches before ADRs. This is the format the skills parse.
list --list-active
EXPECTED=$(printf '%s\t%s\n' \
  "$P/checkout/2026-01-02-live.md"   "checkout" \
  "$P/checkout/2026-01-05-fenced.md" "checkout" \
  "$P/checkout/2026-01-07-broken.md" "-" \
  "$P/checkout/2026-01-10-scalar.md" "-" \
  "$P/payments/2026-01-06-refund.md" "payments" \
  "$REPO/adr/2026-01-08-gateway.md"  "_global")
if [ "$LIST_RC" -eq 0 ] && [ "$LIST_OUT" = "$EXPECTED" ]; then
  pass "C1 exact listing (sorted, TAB-separated, name-excludes README/TEMPLATE)"
else
  fail "C1 exact listing" "rc=$LIST_RC
--- got ---
$LIST_OUT
--- want ---
$EXPECTED"
fi

# C2 — the false-ACTIVE grep direction: live-YAML deprecation spellings are OUT.
if ! grep -qF '2026-01-03-cap.md' <<<"$LIST_OUT" && ! grep -qF '2026-01-04-spaced.md' <<<"$LIST_OUT"; then
  pass "C2 'deprecated: True' / 'deprecated:  true' excluded (grep read them as active)"
else
  fail "C2 live-YAML deprecation spellings" "a dead spec is listed as active: $LIST_OUT"
fi

# C3 — the false-DEPRECATED grep direction: a fenced body line is not frontmatter.
if grep -qF '2026-01-05-fenced.md' <<<"$LIST_OUT"; then
  pass "C3 fenced 'deprecated: true' body line still listed (grep dropped it)"
else
  fail "C3 fenced body line" "live pitch silently dropped: $LIST_OUT"
fi

# C4 — fail-open is loud: unparseable frontmatter lists with `-` AND warns on stderr.
if grep -qF "2026-01-07-broken.md" <<<"$LIST_ERR" && grep -qF "frontmatter missing or malformed" <<<"$LIST_ERR"; then
  pass "C4 unparseable frontmatter warns on stderr (fail-open, never silent)"
else
  fail "C4 fail-open warning" "stderr: $LIST_ERR"
fi

# C5 — --type scopes the listing.
list --list-active --type adr
if [ "$LIST_RC" -eq 0 ] && [ "$LIST_OUT" = "$(printf '%s\t%s' "$REPO/adr/2026-01-08-gateway.md" "_global")" ]; then
  pass "C5 --type adr lists only the active ADR"
else
  fail "C5 --type adr" "rc=$LIST_RC got: $LIST_OUT"
fi

# C6 — --domain keeps matches AND unknown-domain docs (they cannot be proven
# not to match), drops known non-matches.
list --list-active --type pitch --domain checkout
if [ "$LIST_RC" -eq 0 ] \
  && grep -qF '2026-01-02-live.md' <<<"$LIST_OUT" \
  && grep -qF '2026-01-07-broken.md' <<<"$LIST_OUT" \
  && grep -qF '2026-01-10-scalar.md' <<<"$LIST_OUT" \
  && ! grep -qF '2026-01-06-refund.md' <<<"$LIST_OUT"; then
  pass "C6 --domain filters known domains, keeps unknown-domain docs"
else
  fail "C6 --domain filter" "rc=$LIST_RC got: $LIST_OUT"
fi

# C7 — empty result is exit 0: emptiness is an answer, not an error.
list --list-active --type adr --domain checkout
if [ "$LIST_RC" -eq 0 ] && [ -z "$LIST_OUT" ]; then
  pass "C7 empty listing exits 0"
else
  fail "C7 empty listing" "rc=$LIST_RC got: $LIST_OUT"
fi

# C8 — --json emits the same six as objects with path/domain/doc_type.
list --list-active --json
if [ "$LIST_RC" -eq 0 ] \
  && [ "$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); a=d["active"]; print(len(a), a[0]["doc_type"], a[-1]["doc_type"], a[2]["domain"])' "$LIST_OUT")" = "6 pitch adr None" ]; then
  pass "C8 --json shape ({'active': [{path, domain, doc_type}]})"
else
  fail "C8 --json shape" "rc=$LIST_RC got: $LIST_OUT"
fi

# C9 — scalar-frontmatter crash regression: plain validation REPORTS both
# malformed docs as violations (exactly 2 — broken + scalar) instead of dying
# on an AttributeError traceback.
list
GOT_V="$(sed -n 's/^\([0-9][0-9]*\) violation(s) found\.$/\1/p' <<<"$LIST_ERR")"
if [ "$LIST_RC" -eq 1 ] && [ "${GOT_V:-0}" = "2" ] \
  && grep -qF '2026-01-10-scalar.md' <<<"$LIST_ERR" \
  && ! grep -qF 'Traceback' <<<"$LIST_ERR"; then
  pass "C9 scalar frontmatter is a reported violation, not a crash"
else
  fail "C9 scalar-frontmatter regression" "rc=$LIST_RC violations=${GOT_V:-0} stderr: $LIST_ERR"
fi

# C10 — flag hygiene: --domain without --list-active warns instead of silently
# doing nothing (house rule: scoping is observable, never silent).
list --domain checkout
if grep -qF -- '--domain has no effect without --list-active' <<<"$LIST_ERR"; then
  pass "C10 --domain without --list-active warns"
else
  fail "C10 no-effect warning" "stderr: $LIST_ERR"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all 10 cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
