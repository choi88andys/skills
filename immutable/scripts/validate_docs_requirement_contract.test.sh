#!/usr/bin/env bash
# validate_docs_requirement_contract.test.sh — regression test for the
# requirement-contract checks in `validate_docs.py` (v0.11.0, invariant 9).
#
# WHY THIS FILE EXISTS
# The contract's merge gate is a validator rule: a pitch whose disagreement
# section still carries a provisional outcome must not merge. A gate that
# silently stops firing is worse than none, so every branch of it is pinned:
# the always-on ticket-record shape, the `required` presence rule and its
# --strict-since grandfathering, the provisional / terminal / missing-field
# outcomes, the "opted out → no-op" contract, the "profile lacks vocabulary →
# skipped with a warning" contract, and a malformed config block being fatal.
#
# Usage:  bash immutable/scripts/validate_docs_requirement_contract.test.sh
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  python3 + PyYAML — no git. Runs in-tree so the bundled default-ko
#         profile (which carries the vocabulary) resolves.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$SCRIPT_DIR/validate_docs.py"
[ -f "$VALIDATOR" ] || { echo "cannot run: $VALIDATOR not found" >&2; exit 2; }
python3 -c 'import yaml' 2>/dev/null \
  || { echo "cannot run: validate_docs.py needs PyYAML (pip install pyyaml)" >&2; exit 2; }

RIG="$(mktemp -d)"
trap 'rm -rf "$RIG"' EXIT
RIG="$(cd "$RIG" && pwd)"
REPO="$RIG/repo"; P="$REPO/pitches/reward"
mkdir -p "$REPO/.immutable-prd" "$P"

write_config() {  # write_config <enforcement|none> [profile-line]
  {
    echo "version: 3"; echo "repo_mode: two-repo-spec"; echo "team_language: ko"; echo "pitches_path: pitches/"
    if [ -n "${2:-}" ]; then echo "$2"; fi
    if [ "$1" != "none" ]; then
      echo "requirement_contract:"; echo "  enforcement: $1"; echo "  tracker: github"; echo "  repo: acme/tracker"
    fi
  } >"$REPO/.immutable-prd/config.yml"
}
write_config required

cat >"$REPO/pitches/README.md" <<'MD'
| domain | description |
|---|---|
| `reward` | reward stamps |
MD

# A body that passes every non-contract strict check (required sections +
# per-story structure under default-ko), so violations below are contract ones.
BODY='# 제목

## 배경과 문제

문제.

## 사용자 스토리 및 수용 조건

### 스토리 하나

- **Given** 상태
- **When** 행위
- **Then** 반응

- **[MUST]** 시스템은 한다.

### 스토리 둘

- **[MUST]** 시스템은 또 한다.

## 엣지 케이스

| 상황 | 처리 |
|---|---|
| 없음 | 없음 |

## 범위 제외 (No-gos)

- 제외 (deferred)
'
TICKET='references:
  tickets:
    - tracker: github
      repo: acme/tracker
      id: "3755"
      version: "2026-09-08T05:25:01Z"
      read_at: 2026-09-08'
DISAGREE_HEAD='## 요구사항 이견

### github acme/tracker#3755 · 완료 조건 · 적립 7

- **원문** 1,000원 미만 제외
- **정정** 0원 제외
- **사유** 자기모순 — 비고 미해결이 기준을 미정으로 둠
'
mkpitch() {  # mkpitch <name> <frontmatter-extra> <body-extra>
  {
    echo '---'; echo 'domain: reward'; echo 'supersedes: null'; echo 'deprecated: false'
    if [ -n "$2" ]; then printf '%s\n' "$2"; fi
    echo '---'; echo; printf '%s' "$BODY"
    if [ -n "$3" ]; then echo; printf '%s' "$3"; fi
  } >"$P/$1"
}
mkpitch 2026-01-01-legacy.md      ""        ""                                                  # predates cutoff
mkpitch 2026-02-01-bound.md       "$TICKET" "$DISAGREE_HEAD- **결과** 합의 — 9/10 티켓 정정"      # clean
mkpitch 2026-02-02-exempt.md      'references:
  ticket_exemption: 개발 발 리팩터, 대응 Epic 없음' ""                                              # clean
mkpitch 2026-02-03-none.md        ""        ""                                                  # required → violation
mkpitch 2026-02-04-badshape.md    'references:
  tickets:
    - tracker: github
      id: "3755"' ""                                                                            # no version → always-on violation
mkpitch 2026-02-05-provisional.md "$TICKET" "$DISAGREE_HEAD- **결과** 잠정 — 정정 요청 2026-09-08"  # merge gate
mkpitch 2026-02-06-missingfield.md "$TICKET" '## 요구사항 이견

### 항목

- **원문** 원문
- **정정** 정정
- **결과** 기한 경과 — 개발 정정으로 확정'                                                        # no 사유
mkpitch 2026-02-07-empty.md       "$TICKET" '## 요구사항 이견

(아직 없음)'                                                                                   # heading, no entry
mkpitch 2026-02-08-oddoutcome.md  "$TICKET" "$DISAGREE_HEAD- **결과** 논의 중"                     # neither token

FAILURES=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }
run() {  # run <args...> → RC, OUT (stdout+stderr)
  OUT=$(cd "$REPO" && python3 "$VALIDATOR" "$@" 2>&1) && RC=0 || RC=$?
}
count() { sed -n 's/^\([0-9][0-9]*\) violation(s) found\.$/\1/p' <<<"$OUT"; }
hits() { grep -c -F -- "$1" <<<"$OUT" || true; }

echo "validate_docs.py — requirement-contract checks (invariant 9)"
echo

# C1 — plain run: only the always-on shape check fires (badshape), nothing else.
run --type pitch
if [ "$RC" -eq 1 ] && [ "$(count)" = "1" ] && [ "$(hits 'badshape.md')" = "1" ] && grep -qF "missing non-empty ['version']" <<<"$OUT"; then
  pass "C1 plain run: ticket-record shape is always on, nothing else fires"
else
  fail "C1 plain run" "rc=$RC
$OUT"
fi

# C2 — strict-body + cutoff under `required`: none / badshape / provisional /
# missingfield / empty / oddoutcome each fire once; bound + exempt clean;
# legacy exempted by the cutoff (and reported as such).
run --type pitch --strict-body --strict-since 2026-02-01
if [ "$RC" -eq 1 ] && [ "$(count)" = "6" ] \
  && [ "$(hits 'none.md')" = "1" ] && grep -qF 'records neither references.tickets nor references.ticket_exemption' <<<"$OUT" \
  && [ "$(hits 'provisional.md')" = "1" ] && grep -qF 'outcome is `잠정` (correction request still open)' <<<"$OUT" \
  && [ "$(hits 'missingfield.md')" = "1" ] && grep -qF 'missing bullet(s): 사유' <<<"$OUT" \
  && [ "$(hits 'empty.md')" = "1" ] && grep -qF 'holds no `### ` entry' <<<"$OUT" \
  && [ "$(hits 'oddoutcome.md')" = "1" ] && grep -qF "outcome must begin with one of ['합의', '기한 경과']" <<<"$OUT" \
  && [ "$(hits 'bound.md')" = "0" ] && [ "$(hits 'exempt.md')" = "0" ] && [ "$(hits 'legacy.md')" = "0" ] \
  && grep -qF '1 legacy file(s) exempt' <<<"$OUT"; then
  pass "C2 strict + required: presence, provisional, missing field, empty, odd outcome; clean ones clean; legacy exempt"
else
  fail "C2 strict + required" "rc=$RC violations=$(count)
$OUT"
fi

# C3 — `optional`: the presence rule goes away, the gate stays.
write_config optional
run --type pitch --strict-body --strict-since 2026-02-01
if [ "$RC" -eq 1 ] && [ "$(count)" = "5" ] && [ "$(hits 'none.md')" = "0" ] && [ "$(hits 'provisional.md')" = "1" ]; then
  pass "C3 optional: presence rule off, merge gate still on"
else
  fail "C3 optional" "rc=$RC violations=$(count)
$OUT"
fi

# C4 — no block at all: every contract check but the shape one is a no-op,
# even with --strict-body — a repo that never opted in sees nothing new.
write_config none
run --type pitch --strict-body --strict-since 2026-02-01
if [ "$RC" -eq 1 ] && [ "$(count)" = "1" ] && [ "$(hits 'badshape.md')" = "1" ] && [ "$(hits 'provisional.md')" = "0" ]; then
  pass "C4 no config block: only the shape check remains"
else
  fail "C4 opted out" "rc=$RC violations=$(count)
$OUT"
fi

# C5 — the block is present but the team profile lacks the vocabulary: the
# gate is skipped WITH a warning (never silently), presence still enforced.
cat >"$REPO/.immutable-prd/profile.yml" <<'YML'
profile_schema: 2
locale: ko
sections:
  - id: background
    heading: "배경과 문제"
    required: true
  - id: user_stories
    heading: "사용자 스토리 및 수용 조건"
    required: true
    structure: per_story_grouped
  - id: edge_cases
    heading: "엣지 케이스"
    required: true
  - id: no_gos
    heading: "범위 제외 (No-gos)"
    required: true
YML
write_config required "profile: .immutable-prd/profile.yml"
run --type pitch --strict-body --strict-since 2026-02-01
if [ "$RC" -eq 1 ] && [ "$(count)" = "2" ] && [ "$(hits 'none.md')" = "1" ] && [ "$(hits 'provisional.md')" = "0" ] \
  && grep -qF 'disagreement-outcome check is skipped' <<<"$OUT"; then
  pass "C5 profile without vocabulary: gate skipped with a warning, presence still enforced"
else
  fail "C5 vocabulary missing" "rc=$RC violations=$(count)
$OUT"
fi
rm -f "$REPO/.immutable-prd/profile.yml"

# C6 — a malformed block is fatal, never "off": bad enforcement, bad repo,
# empty fetch_command each stop the run with a config error.
for bad in 'enforcement: sometimes' 'repo: "not a slug"' 'fetch_command: ""'; do
  { echo "version: 3"; echo "repo_mode: two-repo-spec"; echo "team_language: ko"; echo "pitches_path: pitches/"
    echo "requirement_contract:"; echo "  $bad"; } >"$REPO/.immutable-prd/config.yml"
  run --type pitch
  if [ "$RC" -eq 1 ] && grep -qF 'error: config.yml requirement_contract' <<<"$OUT" && ! grep -qF 'violation(s) found' <<<"$OUT"; then
    pass "C6 malformed block (${bad%%:*}) is fatal"
  else
    fail "C6 malformed block (${bad%%:*})" "rc=$RC
$OUT"
  fi
done

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all 8 cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
