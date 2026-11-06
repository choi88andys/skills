#!/usr/bin/env bash
# validate_docs_input_contract.test.sh — regression test for the v0.18 input
# contract (SCHEMA.md "Validation invariants" 13).
#
# WHY THIS FILE EXISTS (v0.18.0)
# In lounge-x-app 2.3.1 (2026-11-06) the signup pitch asked for an optional
# birthdate and said neither how it is entered nor what happens to a wrong value.
# The ticket was silent and the design drew a plain text field, so the app took
# six typed digits and stored impossible dates. A pitch-level rule ("the edge
# table holds an invalid-input row") PASSED that pitch, because its edge table
# already had one-time-code error rows, and flagged 1 of the 9 input-bearing
# pitches of the repo. So the check is per field: the pitch declares each value
# the user enters in a `## 입력 항목` table (field, how it is entered, accepted
# values, on an invalid value), and the validator polices what is declared.
#
# Pinned below, on the pre-fix signup shape (one-time-code error rows in the edge
# table, an undeclared birthdate input): it warns before the section's `since`
# (I1) and fails on or after it (I2); with a complete table it passes silently
# (I3). A present table fails on an empty or placeholder cell (I4), an undecided
# cell (I5), a field declared twice (I6), and a wrong header, a missing delimiter
# or no row (I7). A table that declares the code but not the birthdate warns on
# the birthdate line, per field, and never blocks (I8). A section that says in
# one line which pitch defines the input passes; an empty one fails (I9). A team
# profile without the section reads the bundled vocabulary and warns, never
# blocks (I10); a team section without `since` blocks every pitch (I11); a
# malformed `since` or marker list is a profile violation (I12). Scope: only
# under --strict-body, only bracketed normative lines outside fences, never a
# deprecated pitch or one before --strict-since (I13). A field cell's
# parenthetical and alternatives still name it, and a header label may carry
# emphasis or extra spaces (I14). The bundled profiles and
# `migrate/schema_v9.yml` agree on the stock text and the gate counts (I15).
# Review catches before v0.18.0 shipped, each reproduced on a fixture first: four
# fail-open shapes (I16) and six rejections or crashes on legitimate input (I17).
#
# Usage:  bash immutable/scripts/validate_docs_input_contract.test.sh
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  python3 + PyYAML — no git.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$SCRIPT_DIR/validate_docs.py"
BUNDLED_KO="$SCRIPT_DIR/../examples/_profiles/default-ko.yml"

[ -f "$VALIDATOR" ] || { echo "cannot run: $VALIDATOR not found" >&2; exit 2; }
[ -f "$BUNDLED_KO" ] || { echo "cannot run: $BUNDLED_KO not found" >&2; exit 2; }
python3 -c 'import yaml' 2>/dev/null \
  || { echo "cannot run: validate_docs.py needs PyYAML (pip install pyyaml)" >&2; exit 2; }
grep -q '^    since: 2026-11-07$' "$BUNDLED_KO" \
  || { echo "cannot run: the fixtures assume the bundled input_contract since 2026-11-07" >&2; exit 2; }

RIG="$(mktemp -d)"
trap 'rm -rf "$RIG"' EXIT
RIG="$(cd "$RIG" && pwd)"

mkrepo() {  # mkrepo <dir> — ko spec repo, domain auth, team profile = the bundled ko profile
  local d="$1"
  mkdir -p "$d/.immutable-prd" "$d/pitches/auth"
  cat >"$d/.immutable-prd/config.yml" <<'YML'
version: 3
repo_mode: two-repo-spec
team_language: ko
pitches_path: pitches/
profile: .immutable-prd/profile.yml
YML
  cp "$BUNDLED_KO" "$d/.immutable-prd/profile.yml"
  printf '%s\n' '| domain | description |' '|---|---|' '| `auth` | 인증 |' >"$d/pitches/README.md"
}

# The pre-fix signup pitch, reduced: one-time-code error rows in the edge table,
# a birthdate input no section declares. $1 = the Inputs section ("" for none).
signup() {
  local inputs="$1" dep="${2:-false}"
  cat <<MD
---
domain: auth
supersedes: null
deprecated: $dep
---

# 가입

## 배경과 문제

휴대폰 번호로 본인 확인을 끝내고 가입한다.

## 사용자 스토리 및 수용 조건

### 인증번호 확인

- **Given** 비로그인 사용자가 휴대폰 번호를 입력한 상태
- **When** 받은 6자리 인증번호를 입력해 확인한다
- **Then** 시스템은 본인 확인을 끝낸다

- **[MUST]** 시스템은 사용자가 휴대폰 번호를 입력하고 발송을 요청하면 그 번호로 인증번호를 보낸다.
- **[MUST]** 시스템은 인증번호가 틀리면 틀렸음을 안내하고 인증번호 입력 상태를 유지한다.

### 가입 완료

- **Given** 본인 확인을 마친 사용자
- **When** 가입을 확정한다
- **Then** 시스템은 가입을 완료한다

- **[MUST]** 시스템은 생년월일 입력을 선택 사항으로 두고, 비워 둔 채로도 가입을 완료한다.

$inputs

## 엣지 케이스

| 상황 | 처리 |
|---|---|
| 인증번호 유효 시간이 지난 뒤 확인 | 틀린 인증번호와 같은 안내를 거친다 |
| 인증번호가 틀림 | 틀렸음을 안내하고 입력 상태를 유지한다 |

## 범위 제외 (No-gos)

- **휴대폰 번호의 입력 수단** — 시안과 구현이 정한다. *(outside-scope)*
MD
}

HEADER='| 항목 | 입력 방식 | 받는 값 | 잘못된 값일 때 |'
PHONE='| 휴대폰 번호 | 숫자 키패드 | 010 으로 시작하는 11자리 숫자 | 발송 버튼이 비활성으로 남는다 |'
CODE='| 인증번호 | 숫자 키패드 | 6자리 숫자 | 틀렸음을 안내하고 입력 상태를 유지한다 |'
BIRTH='| 생년월일 (선택) | 날짜 선택기 — 연, 월, 일을 고른다 | 오늘 이전의 실제 날짜 | 선택기가 미래 날짜와 없는 날짜를 고를 수 없게 한다 |'
inputs() { printf '%s\n' '## 입력 항목' '' "$HEADER" '|---|---|---|---|' "$@"; }

FAILURES=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }

run() {  # run <repo> [extra args...] -> OUT (stdout+stderr), RC
  local repo="$1"; shift
  OUT=$(python3 "$VALIDATOR" --config "$repo/.immutable-prd/config.yml" --type pitch "$@" 2>&1) && RC=0 || RC=$?
}

# --- I1 / I2 / I3: the pre-fix signup shape, by date, then fixed ---
R="$RIG/signup"; mkrepo "$R"; A="$R/pitches/auth"
signup "" >"$A/2026-11-06-signup.md"
run "$R" --strict-body
if [ "$RC" -eq 0 ] && grep -qF '2026-11-06-signup.md: 3 normative line(s) speak of a user-entered value — line(s) 21, 22, 30' <<<"$OUT" \
  && grep -qF 'dated before its since 2026-11-07' <<<"$OUT" && grep -qF 'all checks passed.' <<<"$OUT"; then
  pass "I1 the pre-fix signup shape (code error rows, undeclared birthdate) warns before since"
else
  fail "I1 pre-fix shape before since" "rc=$RC
$OUT"
fi

mv "$A/2026-11-06-signup.md" "$A/2026-11-07-signup.md"
run "$R" --strict-body
if [ "$RC" -eq 1 ] && grep -qF '2026-11-07-signup.md: input contract violation: 3 normative line(s)' <<<"$OUT" \
  && grep -qF 'line 30: - **[MUST]** 시스템은 생년월일 입력을 선택 사항으로' <<<"$OUT" \
  && grep -qF '1 violation(s) found.' <<<"$OUT"; then
  pass "I2 the same pitch dated on its since fails"
else
  fail "I2 pre-fix shape on since" "rc=$RC
$OUT"
fi

signup "$(inputs "$PHONE" "$CODE" "$BIRTH")" >"$A/2026-11-07-signup.md"
run "$R" --strict-body
if [ "$RC" -eq 0 ] && ! grep -qF 'input contract' <<<"$OUT" && ! grep -qF 'warning:' <<<"$OUT"; then
  pass "I3 a complete table passes with no warning"
else
  fail "I3 complete table" "rc=$RC
$OUT"
fi

# --- I4 / I5 / I6 / I7: a present table is policed at any date ---
B="$RIG/table"; mkrepo "$B"; BA="$B/pitches/auth"
signup "$(inputs "$PHONE" "$CODE" '| 생년월일 | 날짜 선택기 | 오늘 이전의 날짜 |  |')" >"$BA/2026-01-01-empty.md"
signup "$(inputs "$PHONE" "$CODE" '| 생년월일 | 날짜 선택기 | — | 고를 수 없다 |')" >"$BA/2026-01-02-dash.md"
signup "$(inputs "$PHONE" '| 인증번호 | [미확정] | 6자리 숫자 | TBD |' "$BIRTH")" >"$BA/2026-01-03-undecided.md"
signup "$(inputs "$PHONE" "$CODE" "$BIRTH" '| 인증번호 | 붙여넣기 | 6자리 숫자 | 거절한다 |')" >"$BA/2026-01-04-twice.md"
signup "$(printf '%s\n' '## 입력 항목' '' '| 항목 | 방식 | 값 | 오류 |' '|---|---|---|---|' "$PHONE")" >"$BA/2026-01-05-header.md"
signup "$(printf '%s\n' '## 입력 항목' '' "$HEADER" "$PHONE")" >"$BA/2026-01-06-nodelim.md"
signup "$(printf '%s\n' '## 입력 항목' '' "$HEADER" '|---|---|---|---|')" >"$BA/2026-01-07-norow.md"
signup "$(inputs "$PHONE" '| 인증번호 | 숫자 키패드 | 6자리 숫자 |')" >"$BA/2026-01-08-short.md"
run "$B" --strict-body
if grep -qF '2026-01-01-empty.md: input contract violation:' <<<"$OUT" \
  && grep -qF '«생년월일» — `잘못된 값일 때` is empty' <<<"$OUT" \
  && grep -qF '2026-01-02-dash.md: input contract violation:' <<<"$OUT" \
  && grep -qF '«생년월일» — `받는 값` is empty' <<<"$OUT"; then
  pass "I4 an empty or placeholder cell fails — dated long before since"
else
  fail "I4 empty cell" "$OUT"
fi
if grep -qF '«인증번호» — `입력 방식` is undecided: [미확정]' <<<"$OUT" \
  && grep -qF '«인증번호» — `잘못된 값일 때` is undecided: TBD' <<<"$OUT"; then
  pass "I5 an undecided cell ([미확정], TBD) fails"
else
  fail "I5 undecided cell" "$OUT"
fi
if grep -qF '2026-01-04-twice.md: input contract violation:' <<<"$OUT" \
  && grep -qE '«인증번호» is declared twice \(first at line [0-9]+\)' <<<"$OUT"; then
  pass "I6 a field declared twice fails"
else
  fail "I6 duplicate field" "$OUT"
fi
if grep -qF '2026-01-05-header.md' <<<"$OUT" \
  && grep -qF 'the table header must be `| 항목 | 입력 방식 | 받는 값 | 잘못된 값일 때 |`' <<<"$OUT" \
  && grep -qF 'the header is not followed by a delimiter row of 4 cells' <<<"$OUT" \
  && grep -qF 'the table has no row' <<<"$OUT" && grep -qF 'a row has 3 cell(s), the table 4' <<<"$OUT" \
  && [ "$RC" -eq 1 ] && grep -qF '8 violation(s) found.' <<<"$OUT"; then
  pass "I7 a wrong header, a missing delimiter, no row and a short row fail"
else
  fail "I7 table shape" "rc=$RC
$OUT"
fi

# --- I8: the per-field net — a table for the code, none for the birthdate ---
C="$RIG/perfield"; mkrepo "$C"; CA="$C/pitches/auth"
signup "$(inputs "$PHONE" "$CODE")" >"$CA/2026-11-08-signup.md"
run "$C" --strict-body
if [ "$RC" -eq 0 ] && grep -qF 'line 30 speaks of a user-entered value but names no field of `## 입력 항목`' <<<"$OUT" \
  && [ "$(grep -c 'names no field' <<<"$OUT")" -eq 1 ] \
  && grep -qF 'note: input contract: 1 normative line(s) name no field' <<<"$OUT"; then
  pass "I8 a table without the birthdate warns on the birthdate line, per field, and passes"
else
  fail "I8 per-field net" "rc=$RC
$OUT"
fi

# --- I9: a one-line statement instead of a table; an empty section ---
D="$RIG/statement"; mkrepo "$D"; DA="$D/pitches/auth"
signup "$(printf '%s\n' '## 입력 항목' '' '이 pitch 는 입력을 정하지 않는다 — 휴대폰 번호와 인증번호는 `pitches/auth/2026-01-01-phone.md` 가 정한다.')" \
  >"$DA/2026-11-08-mention.md"
signup "$(printf '%s\n' '## 입력 항목' '' '<!--' '값마다 한 행.' '-->')" >"$DA/2026-11-08-empty.md"
printf '%s\n' '---' 'domain: auth' 'supersedes: null' 'deprecated: false' '---' '' '# 휴대폰' '' >"$DA/2026-01-01-phone.md"
run "$D" --strict-body
if ! grep -qF '2026-11-08-mention.md' <<<"$OUT" \
  && grep -qF '2026-11-08-empty.md: input contract violation:' <<<"$OUT" \
  && grep -qF '`## 입력 항목` holds neither a table nor a statement' <<<"$OUT"; then
  pass "I9 a one-line statement passes; a section holding only a comment fails"
else
  fail "I9 statement form" "$OUT"
fi

# --- I10: a team profile at schema 8 reads the bundled vocabulary and never blocks ---
E="$RIG/schema8"; mkrepo "$E"; EA="$E/pitches/auth"
printf '%s\n' 'profile_schema: 8' 'locale: ko' >"$E/.immutable-prd/profile.yml"
signup "" >"$EA/2026-12-01-signup.md"
run "$E" --strict-body
if [ "$RC" -eq 0 ] && grep -qF 'note: the active profile has no sections[id=input_contract] / input_markers (profile_schema 9)' <<<"$OUT" \
  && grep -qF 'the team profile predates the rule (profile_schema 9)' <<<"$OUT" \
  && grep -qF 'all checks passed.' <<<"$OUT"; then
  pass "I10 an unmigrated team profile warns, never blocks, even after the bundled since"
else
  fail "I10 schema-8 team profile" "rc=$RC
$OUT"
fi

# --- I11: a team section without `since` blocks every pitch ---
F="$RIG/nosince"; mkrepo "$F"; FA="$F/pitches/auth"
sed -i.bak '/^    since: 2026-11-07$/d' "$F/.immutable-prd/profile.yml"; rm "$F/.immutable-prd/profile.yml.bak"
signup "" >"$FA/2020-01-01-signup.md"
run "$F" --strict-body
if [ "$RC" -eq 1 ] && grep -qF '2020-01-01-signup.md: input contract violation' <<<"$OUT"; then
  pass "I11 a team section without since blocks a pitch of any date"
else
  fail "I11 no since" "rc=$RC
$OUT"
fi

# --- I12: a malformed since or marker list is a profile violation ---
G="$RIG/malformed"; mkrepo "$G"; GA="$G/pitches/auth"
sed -i.bak -e 's/^    since: 2026-11-07$/    since: "11월 7일"/' -e "s/^  - '타이핑'$/  - '타이핑('/" "$G/.immutable-prd/profile.yml"
rm "$G/.immutable-prd/profile.yml.bak"
signup "" >"$GA/2026-12-01-signup.md"
run "$G" --strict-body
if [ "$RC" -eq 1 ] && grep -qF "active profile: sections[id=input_contract].since must be a YYYY-MM-DD date, got '11월 7일'" <<<"$OUT" \
  && grep -qF 'active profile: input_markers' <<<"$OUT" && grep -qF 'the bundled list applies' <<<"$OUT" \
  && ! grep -qF 'input contract violation' <<<"$OUT" && grep -qF '2 violation(s) found.' <<<"$OUT"; then
  pass "I12 a malformed since or marker regex is a profile violation; the rule then only warns"
else
  fail "I12 malformed profile" "rc=$RC
$OUT"
fi

# --- I13: scope ---
H="$RIG/scope"; mkrepo "$H"; HA="$H/pitches/auth"
signup "" true >"$HA/2026-12-01-dead.md"
signup "" >"$HA/2026-12-02-legacy.md"
{ signup "" | sed -e 's/^- \*\*\[MUST\]\*\* 시스템은 생년월일 입력을 선택 사항으로 두고,/- **[MUST]** 시스템은 생년월일 없이도,/' \
    -e 's/^휴대폰 번호로 본인 확인을 끝내고 가입한다\.$/사용자는 휴대폰 번호를 입력해 본인 확인을 끝내고 가입한다./' \
    -e 's/^- \*\*\[MUST\]\*\* 시스템은 사용자가 휴대폰 번호를 입력하고/- **[MUST]** 시스템은 사용자가 휴대폰 번호를 넣고/' \
    -e 's/^- \*\*\[MUST\]\*\* 시스템은 인증번호가 틀리면 틀렸음을 안내하고 인증번호 입력 상태를/- **[MUST]** 시스템은 인증번호가 틀리면 틀렸음을 안내하고 그 상태를/'
  printf '%s\n' '' '```' '- **[MUST]** 예시: 코드를 입력한다.' '```'; } >"$HA/2026-12-03-prose.md"
signup "" >"$HA/2026-12-04-live.md"
run "$H"
OUT_PLAIN="$OUT"; RC_PLAIN="$RC"
run "$H" --strict-body --strict-since 2026-12-03
if [ "$RC_PLAIN" -eq 0 ] && ! grep -qF 'input' <<<"$OUT_PLAIN" \
  && ! grep -qF '2026-12-01-dead.md' <<<"$OUT" && ! grep -qF '2026-12-02-legacy.md' <<<"$OUT" \
  && ! grep -qF '2026-12-03-prose.md' <<<"$OUT" \
  && grep -qF '2026-12-04-live.md: input contract violation' <<<"$OUT" && grep -qF '1 violation(s) found.' <<<"$OUT"; then
  pass "I13 only --strict-body, only normative lines outside fences, not deprecated, not before --strict-since"
else
  fail "I13 scope" "rc=$RC_PLAIN/$RC
$OUT_PLAIN
$OUT"
fi

# --- I14: a field's parenthetical and alternatives still name it ---
J="$RIG/names"; mkrepo "$J"; JA="$J/pitches/auth"
signup "$(inputs '| 「휴대폰 번호」 / 전화번호 | 숫자 키패드 | 11자리 숫자 | 발송 버튼이 비활성으로 남는다 |' "$CODE" "$BIRTH")" \
  | sed -e 's/사용자가 휴대폰 번호를 입력하고/사용자가 전화번호를 입력하고/' \
        -e 's/^| 항목 | 입력 방식 |/| **항목** | 입력  방식 |/' >"$JA/2026-11-08-signup.md"
run "$J" --strict-body
if [ "$RC" -eq 0 ] && ! grep -qF 'names no field' <<<"$OUT"; then
  pass "I14 「quoted」, (parenthetical) and / alternatives name the field; header emphasis and spacing pass"
else
  fail "I14 field names" "rc=$RC
$OUT"
fi

# --- I16 / I17: review catches before v0.18.0 shipped, each reproduced first ---
# I16 — fail-open shapes that passed: a table without the leading pipe or inside a
# blockquote was read as the statement; a statement of only a dash, a sub-heading
# or an undecided marker passed; one field in two marked-up rows was not a
# duplicate; a bare `input_markers:` key turned the undeclared-input check off.
K="$RIG/review-open"; mkrepo "$K"; KA="$K/pitches/auth"
signup "$(printf '%s\n' '## 입력 항목' '' '항목 | 입력 방식 | 받는 값 | 잘못된 값일 때' '---|---|---|---' '생년월일 | 텍스트 필드 |  | 거절한다')" >"$KA/2026-11-07-nopipe.md"
signup "$(printf '%s\n' '## 입력 항목' '' "> $HEADER" '> |---|---|---|---|' '> | 생년월일 | 텍스트 필드 | 아무 값 |  |')" >"$KA/2026-11-07-quoted.md"
signup "$(printf '%s\n' '## 입력 항목' '' '-')" >"$KA/2026-11-07-dash.md"
signup "$(printf '%s\n' '## 입력 항목' '' '### 상세')" >"$KA/2026-11-07-subhead.md"
signup "$(printf '%s\n' '## 입력 항목' '' '[미확정]')" >"$KA/2026-11-07-tbd.md"
signup "$(inputs "$BIRTH" '| **생년월일** | 텍스트 필드 | 아무 값 | 거절한다 |')" >"$KA/2026-11-07-dupmark.md"
run "$K" --strict-body
OK16=1
for f in nopipe quoted dash subhead tbd dupmark; do
  grep -qF "2026-11-07-$f.md: input contract violation" <<<"$OUT" || OK16=0
done
grep -qF '«**생년월일**» is declared twice' <<<"$OUT" || OK16=0
grep -qF '`## 입력 항목` — the statement is undecided: [미확정]' <<<"$OUT" || OK16=0
N="$RIG/review-null"; mkrepo "$N"
sed -i.bak 's/^input_markers:$/input_markers:\nretired_markers:/' "$N/.immutable-prd/profile.yml"; rm "$N/.immutable-prd/profile.yml.bak"
signup "" >"$N/pitches/auth/2026-11-07-signup.md"
run "$N" --strict-body
grep -qF 'active profile: input_markers must be a list of non-empty regex strings' <<<"$OUT" \
  && grep -qF '2026-11-07-signup.md: input contract violation' <<<"$OUT" || OK16=0
if [ "$OK16" -eq 1 ]; then
  pass "I16 no-pipe and quoted tables, empty statements, marked-up duplicates and a null marker key fail"
else
  fail "I16 fail-open shapes" "$OUT"
fi

# I17 — legitimate forms that failed or crashed: a one-dash or aligned delimiter,
# a closing-hash or indented heading, a linked field name; an impossible `since`
# date crashed the run; a team `gate` without `unresolved_tag` dropped the tag. An
# empty marker list is the team's choice and is said on stderr.
P="$RIG/review-ok"; mkrepo "$P"; PA="$P/pitches/auth"
signup "$(printf '%s\n' '## 입력 항목 ##' '' "$HEADER" '|-|:-:|-:|:--|' "$PHONE" "$CODE" "$BIRTH")" >"$PA/2026-11-07-closehash.md"
signup "$(printf '%s\n' ' ## 입력 항목' '' "$HEADER" '|---|---|---|---|' "$PHONE" "$CODE" '| [생년월일](#가입) | 날짜 선택기 | 오늘 이전의 날짜 | 고를 수 없다 |')" >"$PA/2026-11-07-indent.md"
run "$P" --strict-body
OK17=1
[ "$RC" -eq 0 ] && ! grep -qF 'names no field' <<<"$OUT" || OK17=0
OUT17A="$OUT"
Q="$RIG/review-misc"; mkrepo "$Q"
sed -i.bak -e 's/^    since: 2026-11-07$/    since: 2026-02-30/' "$Q/.immutable-prd/profile.yml"; rm "$Q/.immutable-prd/profile.yml.bak"
signup "" >"$Q/pitches/auth/2026-01-01-signup.md"
run "$Q" --strict-body
grep -qF 'failed to parse' <<<"$OUT" && ! grep -qF 'Traceback' <<<"$OUT" || OK17=0
OUT17B="$OUT"
T="$RIG/review-tag"; mkrepo "$T"
python3 - "$T/.immutable-prd/profile.yml" <<'PY'
import sys, re
p = sys.argv[1]; s = open(p, encoding="utf-8").read()
s = re.sub(r'^  unresolved_tag: "\[미확정\]"\n', "", s, count=1, flags=re.M)
s = re.sub(r"^input_markers:\n(?:  - .*\n)+", "input_markers: []\n", s, count=1, flags=re.M)
open(p, "w", encoding="utf-8").write(s)
PY
signup "$(inputs "$PHONE" "$CODE" '| 생년월일 | [미확정] | 오늘 이전의 날짜 | 고를 수 없다 |')" >"$T/pitches/auth/2026-11-07-signup.md"
run "$T" --strict-body
grep -qF '«생년월일» — `입력 방식` is undecided: [미확정]' <<<"$OUT" \
  && grep -qF 'note: no input_markers are in force' <<<"$OUT" || OK17=0
if [ "$OK17" -eq 1 ]; then
  pass "I17 GFM delimiters, heading forms and linked names pass; a bad date, a tag-less gate and no markers do not fail open"
else
  fail "I17 legitimate forms" "$OUT17A
$OUT17B
$OUT"
fi

# --- I15: the bundled profiles and migrate/schema_v9.yml agree ---
# migrate replaces quality_auditor.checks only when they equal the recorded
# schema-8 stock, and appends the criterion at the end of gate.criteria; both
# assume the bundled schema-9 values are that stock plus one, and the gate
# counts match the list.
SCHEMA_V9="$SCRIPT_DIR/../migrate/schema_v9.yml"
OUT=$(python3 - "$SCRIPT_DIR/../examples/_profiles" "$SCHEMA_V9" <<'PY' 2>&1
import sys, yaml, datetime
root, sv = sys.argv[1], yaml.safe_load(open(sys.argv[2], encoding="utf-8"))
for lang in ("ko", "en"):
    p = yaml.safe_load(open(f"{root}/default-{lang}.yml", encoding="utf-8"))
    assert p["profile_schema"] == sv["schema"], (lang, "schema")
    ids = [s["id"] for s in p["sections"]]
    assert ids[ids.index("user_stories") + 1] == "input_contract", (lang, "section order")
    sec = p["sections"][ids.index("input_contract")]
    assert isinstance(sec["since"], datetime.date), (lang, "since")
    assert set(sec["columns"]) == {"field", "entry", "accepted", "invalid"}, (lang, "columns")
    qa = next(x for x in p["personas"] if x["id"] == "quality_auditor")["checks"]
    assert qa[:-1] == sv["replace_if_stock"][lang]["personas[id=quality_auditor].checks"], (lang, "stock")
    g = p["gate"]
    assert g["criteria"][-1]["id"] == "input_contract", (lang, "criterion last")
    assert g["total"] == len(g["criteria"]) and g["pass_threshold"] == g["total"] - 1, (lang, "gate counts")
    assert p["input_markers"], (lang, "markers")
print("consistent")
PY
) || true
if [ "$OUT" = "consistent" ]; then
  pass "I15 bundled profiles = schema_v9.yml stock + one, the criterion last, gate counts match"
else
  fail "I15 schema_v9 consistency" "$OUT"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
