#!/usr/bin/env bash
# validate_docs_supersede_diff.test.sh — regression test for
# `validate_docs.py --supersede-diff` and the `changes` frontmatter it reads.
#
# WHY THIS FILE EXISTS (v0.17.0)
# Supersedes that said they inherited text unchanged drifted when the body was
# re-authored (lounge-x-spec, measured 2026-11-06): one kept 5 of 15 inherited
# normative lines identical and added a duty, another resurrected three items its
# parent had removed. Nothing compared a successor with its predecessor. The
# authoring skill now copies the predecessor and edits only the sections it
# declares in `changes: [{section, kind}]`; this mode proves the body matches the
# declaration in both directions.
#
# Pinned below: declared changes pass and whitespace is not a change (D1); an
# undeclared rewording fails, naming the section and the normative line first
# (D2); a declaration of the wrong kind, of an unchanged section, or of a section
# that does not exist fails (D3); the frontmatter and fenced headings are not
# body units (D4); a fold diffs against the union of its predecessors and a
# retitle alone is no change (D5); a split's files are judged together — alone,
# the half the sibling carries reads as removed (D6); `--base` judges the pitches
# added since a commit (D7); usage errors exit 2 and a pitch that supersedes
# nothing is skipped with a note (D8); the static shape of `changes` is checked by
# plain validation (D9).
#
# Review catches before v0.17.0 shipped, each reproduced on a fixture first:
# grouping depended on argument order (D10); `--base` silently skipped a pitch
# under a non-ASCII directory, which git prints quoted (D11); two `### Limits`
# under different `## ` headings merged into one unit, so swapping their values
# read as no change (D12); a successor with malformed frontmatter was skipped as
# "supersedes nothing" and the run passed (D13). Also pinned: `--base` reads a
# predecessor as it was at the base, so editing it in the same change cannot make
# the diff agree (D14), and a missing pitch directory exits 2 (D15). v0.18: a
# heading that itself holds " / " resolves by its bare name (D16).
#
# Usage:  bash immutable/scripts/validate_docs_supersede_diff.test.sh
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  python3 + PyYAML, git (D7 only).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$SCRIPT_DIR/validate_docs.py"

[ -f "$VALIDATOR" ] || { echo "cannot run: $VALIDATOR not found" >&2; exit 2; }
python3 -c 'import yaml' 2>/dev/null \
  || { echo "cannot run: validate_docs.py needs PyYAML (pip install pyyaml)" >&2; exit 2; }
command -v git >/dev/null 2>&1 || { echo "cannot run: git not on PATH" >&2; exit 2; }

RIG="$(mktemp -d)"
trap 'rm -rf "$RIG"' EXIT
RIG="$(cd "$RIG" && pwd)"

mkrepo() {  # mkrepo <dir>
  mkdir -p "$1/.immutable-prd" "$1/pitches/alpha"
  cat >"$1/.immutable-prd/config.yml" <<'YML'
version: 3
repo_mode: two-repo-spec
team_language: en
pitches_path: pitches/
profile: .immutable-prd/profile.yml
YML
  printf '%s\n' 'profile_schema: 8' 'locale: en' >"$1/.immutable-prd/profile.yml"
  printf '%s\n' '| domain | description |' '|---|---|' '| `alpha` | first |' >"$1/pitches/README.md"
}

# A predecessor with every unit kind: title preamble, H2 lead, two stories, a table.
base_body() {
  cat <<'MD'
# Payment lock

## Background

Two kinds of identity check exist.

## User Stories

### Session check

- **Given** a stored credential
- **[MUST]** The system checks the credential on every protected entry.

### Payment lock

- **[MUST]** The system supports 4 payment auth methods.
- **[SHOULD]** A failed biometric attempt may be retried.

## Edge Cases

| case | handling |
|---|---|
| network down | log out |
MD
}

fm() {  # fm <supersedes> <deprecated> [extra frontmatter lines...]
  local sup="$1" dep="$2"; shift 2
  printf '%s\n' '---' 'domain: alpha' "supersedes: $sup" "deprecated: $dep" "$@" '---' ''
}

FAILURES=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }

diffrun() {  # diffrun <repo> <args...> -> OUT, RC
  local repo="$1"; shift
  OUT=$(python3 "$VALIDATOR" --config "$repo/.immutable-prd/config.yml" --supersede-diff "$@" 2>&1) && RC=0 || RC=$?
}

# --- repo U: one update ---
U="$RIG/update"; mkrepo "$U"; UA="$U/pitches/alpha"
{ fm null true; base_body; } >"$UA/2026-01-01-lock.md"

# D1: declared method change; whitespace-only differences elsewhere.
{ fm 2026-01-01-lock.md false 'changes:' '  - section: Payment lock' '    kind: modify'
  base_body | sed -e 's/supports 4 payment auth methods/supports 3 payment auth methods/' \
                  -e 's/^| network down | log out |$/|  network down  |  log out |/' \
                  -e 's/^Two kinds of identity check exist\.$/Two  kinds of identity   check exist./'
} >"$UA/2026-02-01-lock.md"
diffrun "$U" "$UA/2026-02-01-lock.md"
if [ "$RC" -eq 0 ] && grep -qF 'modify  declared   Payment lock' <<<"$OUT" \
  && grep -qF 'every change declared' <<<"$OUT" && ! grep -qF 'Edge Cases' <<<"$OUT"; then
  pass "D1 a declared change passes; whitespace is no change"
else
  fail "D1 declared change" "rc=$RC
$OUT"
fi

# D2: the drift class — a reworded inherited normative in an undeclared section.
{ fm 2026-01-01-lock.md false 'changes:' '  - section: "### Payment lock"' '    kind: modify'
  base_body | sed -e 's/supports 4 payment auth methods/supports 3 payment auth methods/' \
                  -e 's/checks the credential on every protected entry/verifies the credential on each protected entry/'
} >"$UA/2026-02-02-lock.md"
diffrun "$U" "$UA/2026-02-02-lock.md"
if [ "$RC" -eq 1 ] && grep -qF '«Session check» — modify not declared in `changes`' <<<"$OUT" \
  && grep -qF -- '- - **[MUST]** The system checks the credential on every protected entry.' <<<"$OUT" \
  && grep -qF -- '+ - **[MUST]** The system verifies the credential on each protected entry.' <<<"$OUT" \
  && grep -qF 'modify  declared   Payment lock' <<<"$OUT" && grep -qF '1 violation(s) found.' <<<"$OUT"; then
  pass "D2 an undeclared rewording fails with the normative lines shown"
else
  fail "D2 undeclared rewording" "rc=$RC
$OUT"
fi

# D3: wrong kind, stale declaration, nonexistent section.
{ fm 2026-01-01-lock.md false 'changes:' \
    '  - section: Payment lock' '    kind: add' \
    '  - section: Session check' '    kind: modify' \
    '  - section: Refunds' '    kind: remove'
  base_body | sed -e 's/supports 4 payment auth methods/supports 3 payment auth methods/'
} >"$UA/2026-02-03-lock.md"
diffrun "$U" "$UA/2026-02-03-lock.md"
if [ "$RC" -eq 1 ] && grep -qF '«Payment lock» is declared `add` but the change is `modify`' <<<"$OUT" \
  && grep -qF '«Session check» is declared `modify` in `changes`, but nothing in it changed' <<<"$OUT" \
  && grep -qF '«Refunds» is declared `remove` in `changes`, but the pitch has no such section' <<<"$OUT"; then
  pass "D3 wrong kind, stale and nonexistent declarations fail"
else
  fail "D3 declaration mismatches" "rc=$RC
$OUT"
fi

# D4: frontmatter is not body; a `## ` inside a fence is not a heading.
{ fm 2026-01-01-lock.md false 'references:' '  tickets: []' 'changes:' '  - section: Background' '    kind: modify'
  base_body | sed -e 's/^Two kinds of identity check exist\.$/Two kinds of identity check exist.\n\n```\n## Not a heading\n```/'
} >"$UA/2026-02-04-lock.md"
diffrun "$U" "$UA/2026-02-04-lock.md"
if [ "$RC" -eq 0 ] && grep -qF 'modify  declared   Background' <<<"$OUT" && ! grep -qF 'Not a heading' <<<"$OUT"; then
  pass "D4 frontmatter and fenced headings are not body units"
else
  fail "D4 frontmatter and fences" "rc=$RC
$OUT"
fi

# --- repo F: a fold of two pitches ---
F="$RIG/fold"; mkrepo "$F"; FA="$F/pitches/alpha"
{ fm null true; printf '%s\n' '# Part A' '' '## Background' '' 'A exists.' '' '## User Stories' '' \
    '### Story A' '' '- **[MUST]** A works.' '' '## Edge Cases' '' '| case | handling |' '|---|---|' '| a | handled |'; } >"$FA/2026-01-01-a.md"
{ fm null true; printf '%s\n' '# Part B' '' '## Background' '' 'B exists.' '' '## User Stories' '' \
    '### Story B' '' '- **[MUST]** B works.' '' '## Edge Cases' '' '| case | handling |' '|---|---|' '| b | handled |'; } >"$FA/2026-01-01-b.md"
{ fm '[2026-01-01-a.md, 2026-01-01-b.md]' false 'changes:' '  - section: Background' '    kind: modify'
  printf '%s\n' '# One feature area' '' '## Background' '' 'A exists.' 'B exists.' 'Both are one feature area.' '' \
    '## User Stories' '' '### Story B' '' '- **[MUST]** B works.' '' '### Story A' '' '- **[MUST]** A works.' '' \
    '## Edge Cases' '' '| case | handling |' '|---|---|' '| b | handled |' '| a | handled |'; } >"$FA/2026-02-01-fold.md"
diffrun "$F" "$FA/2026-02-01-fold.md"
if [ "$RC" -eq 0 ] && grep -qF 'pitches/alpha/2026-02-01-fold.md  <-  pitches/alpha/2026-01-01-a.md + pitches/alpha/2026-01-01-b.md' <<<"$OUT" \
  && grep -qF 'modify  declared   Background' <<<"$OUT" && ! grep -qF 'Edge Cases' <<<"$OUT" && ! grep -qF '# One' <<<"$OUT"; then
  pass "D5 a fold diffs against the union; reordering and a retitle are no change"
else
  fail "D5 fold" "rc=$RC
$OUT"
fi

# --- repo S: a split into two files ---
S="$RIG/split"; mkrepo "$S"; SA="$S/pitches/alpha"
{ fm null true; base_body; } >"$SA/2026-01-01-lock.md"
{ fm 2026-01-01-lock.md false; base_body | sed '/^### Payment lock$/,/^## Edge Cases$/{/^## Edge Cases$/!d;}'; } >"$SA/2026-02-01-session.md"
{ fm 2026-01-01-lock.md false; base_body | sed '/^### Session check$/,/^### Payment lock$/{/^### Payment lock$/!d;}'; } >"$SA/2026-02-01-payment.md"
diffrun "$S" "$SA/2026-02-01-session.md" "$SA/2026-02-01-payment.md"
if [ "$RC" -eq 0 ] && grep -qF '(no difference outside the frontmatter)' <<<"$OUT"; then
  pass "D6 a split judged together loses nothing"
else
  fail "D6 split together" "rc=$RC
$OUT"
fi
diffrun "$S" "$SA/2026-02-01-session.md"
if [ "$RC" -eq 1 ] && grep -qF '«Payment lock» — remove not declared in `changes`' <<<"$OUT"; then
  pass "D6b one half alone reads the other half as removed"
else
  fail "D6b split alone" "rc=$RC
$OUT"
fi

# D7: --base judges the pitches added since a commit (both halves of the split).
git -C "$S" init -q
git -C "$S" -c user.name=t -c user.email=t@t add .immutable-prd pitches/README.md pitches/alpha/2026-01-01-lock.md
git -C "$S" -c user.name=t -c user.email=t@t commit -qm base
BASE="$(git -C "$S" rev-parse HEAD)"
git -C "$S" -c user.name=t -c user.email=t@t add -A
git -C "$S" -c user.name=t -c user.email=t@t commit -qm split
diffrun "$S" --base "$BASE"
if [ "$RC" -eq 0 ] && grep -qF 'pitches/alpha/2026-02-01-payment.md + pitches/alpha/2026-02-01-session.md  <-  pitches/alpha/2026-01-01-lock.md' <<<"$OUT"; then
  pass "D7 --base judges every pitch added since the commit, as one group"
else
  fail "D7 --base" "rc=$RC
$OUT"
fi

# D8: usage errors and a pitch that supersedes nothing.
OUT=$(python3 "$VALIDATOR" --config "$U/.immutable-prd/config.yml" --supersede-diff 2>&1) && RC=0 || RC=$?
OUT2=$(python3 "$VALIDATOR" --config "$U/.immutable-prd/config.yml" --base HEAD 2>&1) && RC2=0 || RC2=$?
OUT3=$(python3 "$VALIDATOR" --config "$U/.immutable-prd/config.yml" --supersede-diff "$U/.immutable-prd/config.yml" 2>&1) && RC3=0 || RC3=$?
RC1="$RC"; OUT1="$OUT"
diffrun "$U" "$UA/2026-01-01-lock.md"
if [ "$RC1" -eq 2 ] && [ "$RC2" -eq 2 ] && [ "$RC3" -eq 2 ] && [ "$RC" -eq 0 ] \
  && grep -qF 'needs PITCH paths, --base REV, or both' <<<"$OUT1" && grep -qF -- '--base needs --supersede-diff' <<<"$OUT2" \
  && grep -qF 'not a pitch file under' <<<"$OUT3" && grep -qF 'supersedes nothing' <<<"$OUT"; then
  pass "D8 usage errors exit 2; a pitch with no predecessor is skipped with a note"
else
  fail "D8 usage" "rc=$RC1/$RC2/$RC3/$RC
$OUT1
$OUT2
$OUT3"
fi

# D9: `changes` shape under plain validation (always on, pitches).
C="$RIG/shape"; mkrepo "$C"; CA="$C/pitches/alpha"
{ fm null false 'changes:' '  - section: Background' '    kind: modify'; base_body; } >"$CA/2026-01-01-orphan.md"
{ fm null true; base_body; } >"$CA/2026-01-01-prev.md"
{ fm 2026-01-01-prev.md false 'changes:' '  - section: Background' '    kind: rewrite' \
    '  - section: Background' '    kind: modify' '  - {section: x, kind: add, note: y}'; base_body; } >"$CA/2026-02-01-bad.md"
OUT=$(python3 "$VALIDATOR" --config "$C/.immutable-prd/config.yml" 2>&1) && RC=0 || RC=$?
if [ "$RC" -eq 1 ] && grep -qF '2026-01-01-orphan.md: `changes` declares a difference from a predecessor, but `supersedes` names none' <<<"$OUT" \
  && grep -qF "changes[0].kind must be one of ['add', 'modify', 'remove'], got 'rewrite'" <<<"$OUT" \
  && grep -qF "changes names section 'Background' more than once" <<<"$OUT" \
  && grep -qF 'changes[2] must be a mapping with exactly `section` and `kind`' <<<"$OUT"; then
  pass "D9 plain validation checks the shape of \`changes\`"
else
  fail "D9 changes shape" "rc=$RC
$OUT"
fi

# D10: a successor bridging two groups merges them — whatever the argument order.
O="$RIG/order"; mkrepo "$O"; OA="$O/pitches/alpha"
story() { printf '%s\n' "# $1" '' '## User Stories' '' "### $2" '' "- **[MUST]** $2 works."; }
{ fm null true; story A Sa; } >"$OA/2026-01-01-a.md"
{ fm null true; story B Sb; } >"$OA/2026-01-01-b.md"
{ fm 2026-01-01-a.md false; story A Sa; } >"$OA/2026-02-01-s1.md"
{ fm 2026-01-01-b.md false; story B Sb; } >"$OA/2026-02-01-s2.md"
{ fm '[2026-01-01-a.md, 2026-01-01-b.md]' false; story AB Sa; printf '%s\n' '' '### Sb' '' '- **[MUST]** Sb works.'; } >"$OA/2026-02-01-s3.md"
diffrun "$O" "$OA/2026-02-01-s1.md" "$OA/2026-02-01-s2.md" "$OA/2026-02-01-s3.md"; RC1="$RC"; OUT1="$OUT"
diffrun "$O" "$OA/2026-02-01-s3.md" "$OA/2026-02-01-s2.md" "$OA/2026-02-01-s1.md"
if [ "$RC1" -eq 0 ] && [ "$RC" -eq 0 ] && [ "$(grep -c '  <-  ' <<<"$OUT1")" = "1" ] && [ "$(grep -c '  <-  ' <<<"$OUT")" = "1" ]; then
  pass "D10 a bridging successor merges groups in any argument order"
else
  fail "D10 grouping order" "rc=$RC1/$RC
$OUT1
$OUT"
fi

# D11: --base finds a pitch whose path holds a non-ASCII directory.
K="$RIG/g"; mkdir -p "$K"; git -C "$K" init -q; mkrepo "$K/스펙"; KA="$K/스펙/pitches/alpha"
{ fm null false; base_body; } >"$KA/2026-01-01-lock.md"
git -C "$K" -c user.name=t -c user.email=t@t add -A; git -C "$K" -c user.name=t -c user.email=t@t commit -qm base
KB="$(git -C "$K" rev-parse HEAD)"
sed -i.bak 's/^deprecated: false$/deprecated: true/' "$KA/2026-01-01-lock.md"; rm "$KA/2026-01-01-lock.md.bak"
{ fm 2026-01-01-lock.md false; base_body | sed 's/supports 4/supports 3/'; } >"$KA/2026-02-01-lock.md"
git -C "$K" -c user.name=t -c user.email=t@t add -A; git -C "$K" -c user.name=t -c user.email=t@t commit -qm next
diffrun "$K/스펙" --base "$KB"
if [ "$RC" -eq 1 ] && grep -qF '«Payment lock» — modify not declared' <<<"$OUT"; then
  pass "D11 --base judges a pitch under a non-ASCII directory"
else
  fail "D11 non-ASCII path" "rc=$RC
$OUT"
fi

# D12: same-named sub-sections under different `## ` stay distinct units.
H="$RIG/dup"; mkrepo "$H"; HA="$H/pitches/alpha"
limits() { printf '%s\n' '# Limits' '' '## Admin' '' '### Limits' '' "- **[MUST]** The cap is $1." '' '## Customer' '' '### Limits' '' "- **[MUST]** The cap is $2."; }
{ fm null true; limits 100 10; } >"$HA/2026-01-01-limits.md"
{ fm 2026-01-01-limits.md false; limits 10 100; } >"$HA/2026-02-01-limits.md"
{ fm 2026-01-01-limits.md false 'changes:' '  - section: Limits' '    kind: modify'; limits 10 100; } >"$HA/2026-02-02-limits.md"
diffrun "$H" "$HA/2026-02-01-limits.md"
diffrun "$H" "$HA/2026-02-02-limits.md"; RC2="$RC"; OUT2="$OUT"
diffrun "$H" "$HA/2026-02-01-limits.md"
if [ "$RC" -eq 1 ] && grep -qF '«Admin / Limits» — modify not declared' <<<"$OUT" \
  && grep -qF '«Customer / Limits» — modify not declared' <<<"$OUT" \
  && [ "$RC2" -eq 1 ] && grep -qF 'it names more than one section — write `Admin / Limits` or `Customer / Limits`' <<<"$OUT2"; then
  pass "D12 same-named sub-sections stay apart; an ambiguous declaration says how to name one"
else
  fail "D12 duplicate headings" "rc=$RC/$RC2
$OUT
$OUT2"
fi

# D13: malformed successor frontmatter is a violation in this mode, never a skip.
{ fm '[2026-01-01-lock.md, 2026-01-01-lock.md]' false; base_body | sed 's/supports 4/supports 5/'; } >"$UA/2026-03-01-twice.md"
{ printf '%s\n' '---' 'domain: alpha' 'supersedes: [unclosed' '---' ''; base_body; } >"$UA/2026-03-02-broken.md"
diffrun "$U" "$UA/2026-03-01-twice.md" "$UA/2026-03-02-broken.md"
if [ "$RC" -eq 1 ] && grep -qF '2026-03-01-twice.md: `supersedes` names 2026-01-01-lock.md more than once' <<<"$OUT" \
  && grep -qF '2026-03-02-broken.md: frontmatter missing or malformed' <<<"$OUT"; then
  pass "D13 a malformed successor fails the diff run"
else
  fail "D13 malformed successor" "rc=$RC
$OUT"
fi

# D14: --base reads the predecessor at the base — editing it to match does not help.
sed -i.bak 's/supports 4/supports 3/' "$KA/2026-01-01-lock.md"; rm "$KA/2026-01-01-lock.md.bak"
git -C "$K" -c user.name=t -c user.email=t@t commit -qam "edit the predecessor too"
diffrun "$K/스펙" --base "$KB"
if [ "$RC" -eq 1 ] && grep -qF "2026-01-01-lock.md@$KB" <<<"$OUT" && grep -qF '«Payment lock» — modify not declared' <<<"$OUT"; then
  pass "D14 --base diffs against the predecessor as it was at the base"
else
  fail "D14 predecessor at base" "rc=$RC
$OUT"
fi

# D15: a config whose pitch directory does not exist cannot run.
M="$RIG/nodir"; mkrepo "$M"; sed -i.bak 's#^pitches_path: pitches/$#pitches_path: pitchez/#' "$M/.immutable-prd/config.yml"; rm "$M/.immutable-prd/config.yml.bak"
OUT=$(python3 "$VALIDATOR" --config "$M/.immutable-prd/config.yml" --supersede-diff --base HEAD 2>&1) && RC=0 || RC=$?
if [ "$RC" -eq 2 ] && grep -qF 'needs the repo' <<<"$OUT"; then
  pass "D15 a missing pitch directory exits 2"
else
  fail "D15 missing pitch dir" "rc=$RC
$OUT"
fi

# D16 (v0.18): a heading that itself holds " / " resolves by its bare name. v0.17
# split it as <parent> / <child> and reported «no such section» plus UNDECLARED
# (measured 2026-11-06, xyzcorpsoftware/lounge-x-spec#71). The <parent> / <child> form still wins
# when such a pair exists, so the disambiguation D12 suggests keeps working.
L="$RIG/slash"; mkrepo "$L"; LA="$L/pitches/alpha"
lockbody() { printf '%s\n' '# Lock' '' '## User Stories' '' '### Lock (PIN / bio)' '' "- **[MUST]** The system offers $1 methods." '' '### Other' '' '- **[MUST]** Unchanged.'; }
{ fm null true; lockbody 4; } >"$LA/2026-01-01-lock.md"
{ fm 2026-01-01-lock.md false 'changes:' '  - section: Lock (PIN / bio)' '    kind: modify'; lockbody 3; } >"$LA/2026-02-01-lock.md"
{ fm 2026-01-01-lock.md false 'changes:' '  - section: User Stories / Lock (PIN / bio)' '    kind: modify'; lockbody 3; } >"$LA/2026-02-02-lock.md"
diffrun "$L" "$LA/2026-02-01-lock.md"; RC1="$RC"; OUT1="$OUT"
diffrun "$L" "$LA/2026-02-02-lock.md"
if [ "$RC1" -eq 0 ] && grep -qF 'modify  declared   Lock (PIN / bio)' <<<"$OUT1" \
  && [ "$RC" -eq 0 ] && grep -qF 'every change declared' <<<"$OUT"; then
  pass "D16 a heading holding \" / \" resolves bare and as <parent> / <child>"
else
  fail "D16 slash in heading" "rc=$RC1/$RC
$OUT1
$OUT"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
