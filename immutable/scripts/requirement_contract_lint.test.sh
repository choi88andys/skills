#!/usr/bin/env bash
# requirement_contract_lint.test.sh — regression test for
# `requirement_contract.py lint`, the deterministic wording check on a ticket's
# binding items (and on drafted corrections).
#
# WHY THIS FILE EXISTS
# The disagreement protocol let a pitch deviate from a binding item only when
# the item was infeasible, self-contradictory or in conflict. A real Epic
# passed that net carrying four binding items nobody could judge: a completion
# condition hedged with 「필요 시」, two QA items deferring to "what the pitch
# decides" (the pitch that must follow them), and an unpinned Figma made the
# acceptance oracle. `lint` is the recall net for that class — the skill, CI
# and the merge gate all run the same rules through `compile_wording` — so the
# cases below pin: the four block hits on an Epic of that shape, with ledger
# coordinates; the measured false positives staying quiet (capability 「할 수
# 있다」, 「되도록」, a quoted UI literal, a pinned 「X 전달」 or version-id
# design); a profile written before the rules existed falling back to the
# bundled ones out loud; and a profile rule the script cannot compile being an
# error, never a silently weaker lint.
#
# The fixtures are synthetic. They mirror the SHAPE of the pilot's Epics, not
# any real ticket's content.
#
# Usage:  bash immutable/scripts/requirement_contract_lint.test.sh
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  python3 + PyYAML (lint reads the profile). No git, no network — the
#         fetch path runs through a custom --fetch-command adapter.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUT="$SCRIPT_DIR/requirement_contract.py"
BUNDLED_KO="$SCRIPT_DIR/../examples/_profiles/default-ko.yml"
[ -f "$SUT" ] || { echo "cannot run: $SUT not found" >&2; exit 2; }
[ -f "$BUNDLED_KO" ] || { echo "cannot run: $BUNDLED_KO not found" >&2; exit 2; }
command -v python3 >/dev/null || { echo "cannot run: python3 not found" >&2; exit 2; }
python3 -c 'import yaml' 2>/dev/null \
  || { echo "cannot run: lint needs PyYAML (pip install pyyaml)" >&2; exit 2; }

RIG="$(mktemp -d)"
trap 'rm -rf "$RIG"' EXIT
RIG="$(cd "$RIG" && pwd)"

B_ACC='acceptance=완료 조건'
B_QA='qa_checklist=QA 통과 리스트'

# --- the defect shape: one hedged completion condition, two circular QA items,
# one unpinned design oracle; plus a struck item and the 비고 note a
# self-contradiction judgement reads (lint does not) ---
cat >"$RIG/hedged.md" <<'MD'
### 사용자 시나리오

사용자가 진행 화면에서 남은 시간을 분과 초로 본다.

### QA 통과 리스트

- [ ] 잔여가 1분 이상인 주문을 본다 → 「M분 S초 후 완성」으로 보인다
- [ ] 잔여가 1분 미만으로 내려간다 → 「S초 후 완성」으로 바뀐다
- [ ] 초가 줄어드는 동안 표기가 끊기거나 튀지 않는다
- [ ] 대기중 단계의 표기가 #12 pitch supersede 에서 확정된 대로다
- [ ] 토글의 절대 완성 시각 표기는 기존과 같다
- [ ] 정확히 N분 0초일 때의 표기가 #12 에서 확정된 대로다
- [ ] Figma 표기와 앱 문자열이 일치한다

### 완료 조건

- [ ] pitch supersede 작성·머지 (spec repo — 활성 pitch `progress/2026-01-01-status.md` 대체)
- [ ] 앱 구현 + 테스트 (pitch [MUST]와 1:1)
- [ ] 디자이너 Figma 표기 정합 확인 (필요 시)
- [ ] ~~옛 표기는 필요 시 유지한다~~

### 비고

- 정확히 N분 0초일 때는 「M분 00초」로 쓴다
MD

# --- the measured false positives: each line once fired a naive rule ---
cat >"$RIG/clean.md" <<'MD'
### 완료 조건

- [ ] 사용자가 쿠폰을 직접 등록할 수 있다
- [ ] 결제 중에는 「처리 중…」 문구가 표시된다
- [ ] 총액이 1,000원 미만이 되도록 주문을 구성한다 → 적립 예정이 0개다
- [ ] 구현이 「리워드 개편 전달」 시안과 일치한다
- [ ] 화면이 시안과 일치한다 (version-id=8812)

### QA 통과 리스트

- [ ] 결과 화면을 디자이너와 공유
MD

FAILURES=0
PASSES=0
pass() { printf 'PASS  %s\n' "$1"; PASSES=$((PASSES + 1)); }
fail() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }

# run <args...> → RC, ERR (stderr); JSON saved to $RIG/out.json
run() {
  python3 "$SUT" "$@" >"$RIG/out.json" 2>"$RIG/stderr.txt" && RC=0 || RC=$?
  ERR=$(cat "$RIG/stderr.txt")
}
# q <python expression over d> — evaluate against the last JSON output
q() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))' "$RIG/out.json" "$1"; }
HITS='[(h["target"], h["binding"], h["group"], h["in_group"], h["rule"], h["severity"]) for h in d["hits"]]'

python3 "$SUT" parse "$RIG/hedged.md" --binding "$B_ACC" --binding "$B_QA" >"$RIG/hedged.json"
python3 "$SUT" parse "$RIG/clean.md" --binding "$B_ACC" --binding "$B_QA" >"$RIG/clean.json"

echo "requirement_contract.py lint — ticket wording contract"
echo

# L1 — the defect shape: exit 1; block hits on 완료 3 (conditional AND
# unpinned_oracle), QA 4 and QA 6 (delegated_downstream), QA 7 (unpinned
# oracle); warn hits on 완료 3 (process_only — acceptance-scoped) and QA 3
# (unmeasurable). Every hit carries the ledger coordinate; the struck item is
# skipped and counted; the backtick path in 완료 1 is stripped before matching.
run lint --profile "$BUNDLED_KO" --from-json "$RIG/hedged.json"
GOT="$(q "$HITS")"
WANT="[('ticket_item', 'acceptance', None, 3, 'conditional', 'block'), ('ticket_item', 'acceptance', None, 3, 'unpinned_oracle', 'block'), ('ticket_item', 'acceptance', None, 3, 'process_only', 'warn'), ('ticket_item', 'qa_checklist', None, 3, 'unmeasurable', 'warn'), ('ticket_item', 'qa_checklist', None, 4, 'delegated_downstream', 'block'), ('ticket_item', 'qa_checklist', None, 6, 'delegated_downstream', 'block'), ('ticket_item', 'qa_checklist', None, 7, 'unpinned_oracle', 'block')]"
if [ "$RC" -eq 1 ] && [ "$GOT" = "$WANT" ] \
  && [ "$(q 'd["counts"]')" = "{'items': 10, 'struck_skipped': 1, 'items_with_block': 4, 'block': 5, 'warn': 2}" ] \
  && [ "$(q '[(h["category"], h["match"], h["line"]) for h in d["hits"] if h["rule"] == "conditional"]')" = "[('non_concrete', '필요 시', 19)]" ] \
  && [ "$(q 'd["rules"]["fallback"], d["rules"]["ticket_item"], d["rules"]["correction"]')" = "(None, 7, 9)" ]; then
  pass "L1 defect shape: 4 block items (5 hits) + 2 warns with ledger coordinates; struck item skipped"
else
  fail "L1 defect shape" "rc=$RC stderr=$ERR
--- got ---
$GOT
--- want ---
$WANT
counts=$(q 'd["counts"]')"
fi

# L2 — the measured false positives stay quiet: 「할 수 있다」 (capability),
# 「되도록」 ("~가 되도록 구성한다"), 「처리 중…」 (a quoted UI literal is stripped
# before the open-enumeration rule sees its ellipsis), a design pinned by a
# named 「X 전달」 delivery or a version-id link (`unless` reads the RAW text,
# since the pin is itself a quoted literal), and a process-only line in the QA
# section (process_only is scoped to acceptance).
run lint --profile "$BUNDLED_KO" --from-json "$RIG/clean.json"
if [ "$RC" -eq 0 ] && [ "$(q 'd["hits"]')" = "[]" ] && [ "$(q 'd["counts"]["items"]')" = "6" ]; then
  pass "L2 measured false positives: no hit at all, exit 0"
else
  fail "L2 false positives" "rc=$RC $(q "$HITS")"
fi

# L3 — a profile written before `wording_rules` (v0.12 shape: three
# categories, deferral_patterns only) lints with the bundled rules for its
# locale, and says so in `rules.fallback` and a warning — never "0 rules, all
# clean". Its own legacy deferral_patterns still apply, to corrections only.
cat >"$RIG/legacy.yml" <<'YML'
profile_schema: 4
locale: ko
requirement_contract:
  categories:
    - { id: infeasible, label: "구현 불가" }
    - { id: self_contradiction, label: "자기모순" }
    - { id: conflict, label: "확정된 다른 요구사항과의 충돌" }
  disagreement:
    deferral_patterns:
      - id: team_hold
        regex: '보류'
        hint: "팀이 정한 보류 표시"
YML
run lint --profile "$RIG/legacy.yml" --from-json "$RIG/hedged.json"
L3_RC=$RC; L3_HITS="$(q "$HITS")"; L3_FB="$(q 'd["rules"]["fallback"].endswith("default-ko.yml")')"
L3_WARN="$(q 'any("no requirement_contract.wording_rules" in w for w in d["warnings"])')"
run lint --profile "$RIG/legacy.yml" --correction "이 값은 보류한다"
if [ "$L3_RC" -eq 1 ] && [ "$L3_HITS" = "$WANT" ] && [ "$L3_FB" = "True" ] && [ "$L3_WARN" = "True" ] \
  && [ "$RC" -eq 1 ] && [ "$(q '[(h["rule"], h["source"], h["category"]) for h in d["hits"]]')" = "[('team_hold', 'deferral_patterns', None)]" ]; then
  pass "L3 pre-v0.13 profile: bundled rules by locale, named; legacy deferral_patterns still judge corrections"
else
  fail "L3 legacy profile" "rc=$L3_RC fallback=$L3_FB warn=$L3_WARN hits=$L3_HITS
correction rc=$RC $(q 'd["hits"]')"
fi

# L4 — --correction runs the SAME rules on a drafted correction, so the skill
# checks its own sentence with the engine the merge gate uses: a hedged one is
# a block hit with no coordinate; a decisive one is clean; a correction-only
# rule (confirm_later, the v0.11 deferral pattern) never fires on a ticket item.
run lint --profile "$BUNDLED_KO" --correction "문구는 필요 시 디자이너와 맞춘다" --correction "기준액은 측과 대조해 확정한다"
C1_RC=$RC; C1="$(q "$HITS")"
run lint --profile "$BUNDLED_KO" --correction "최종 결제 금액이 1,000원 미만이 된 주문건은 제외된다"
C2_RC=$RC; C2="$(q 'd["hits"]')"
printf '%s\n' '### 완료 조건' '' '- [ ] 기준액은 측과 대조해 확정한다' >"$RIG/item.md"
python3 "$SUT" parse "$RIG/item.md" --binding "$B_ACC" >"$RIG/item.json"
run lint --profile "$BUNDLED_KO" --from-json "$RIG/item.json"
if [ "$C1_RC" -eq 1 ] && [ "$C1" = "[('correction', None, None, None, 'conditional', 'block'), ('correction', None, None, None, 'confirm_later', 'block')]" ] \
  && [ "$C2_RC" -eq 0 ] && [ "$C2" = "[]" ] && [ "$RC" -eq 0 ] && [ "$(q 'd["hits"]')" = "[]" ]; then
  pass "L4 --correction: same engine; hedged → block, decisive → clean; correction-only rule spares ticket items"
else
  fail "L4 corrections" "hedged rc=$C1_RC $C1
decisive rc=$C2_RC $C2
item rc=$RC $(q 'd["hits"]')"
fi

# L5 — a rule the profile states but the script cannot trust is an error
# (exit 2, named), never a quieter lint: invalid regex, a category the profile
# does not declare, a bad severity. An explicit empty list is the team's
# choice — honoured, with a warning that nothing is checked.
mkprofile() {  # mkprofile <file> <wording_rules yaml lines...>
  local f="$1"; shift
  { echo 'locale: ko'; echo 'requirement_contract:'; echo '  categories:'; echo '    - { id: non_concrete, label: "구체성 결함" }'
    printf '%s\n' "$@"; } >"$f"
}
mkprofile "$RIG/badre.yml" '  wording_rules:' '    - { id: broken, category: non_concrete, severity: block, applies_to: [ticket_item], regex: "(unclosed" }'
mkprofile "$RIG/badcat.yml" '  wording_rules:' '    - { id: orphan, category: nowhere, severity: block, applies_to: [ticket_item], regex: "x" }'
mkprofile "$RIG/badsev.yml" '  wording_rules:' '    - { id: loud, category: non_concrete, severity: fatal, applies_to: [ticket_item], regex: "x" }'
mkprofile "$RIG/empty.yml" '  wording_rules: []'
OK=1; DETAIL=""
for pair in "badre.yml:wording_rules[broken].regex is an invalid regex" "badcat.yml:category 'nowhere' is not one of" "badsev.yml:severity must be one of"; do
  run lint --profile "$RIG/${pair%%:*}" --from-json "$RIG/hedged.json"
  if [ "$RC" -ne 2 ] || ! grep -qF "${pair#*:}" <<<"$ERR" || grep -qF Traceback <<<"$ERR"; then OK=0; DETAIL="$DETAIL ${pair%%:*} rc=$RC $ERR;"; fi
done
run lint --profile "$RIG/empty.yml" --from-json "$RIG/hedged.json"
if [ "$OK" -eq 1 ] && [ "$RC" -eq 0 ] && [ "$(q 'd["hits"]')" = "[]" ] \
  && [ "$(q 'any("no wording rule applies to ticket_item" in w for w in d["warnings"])')" = "True" ]; then
  pass "L5 untrustworthy rule → exit 2 naming it; explicit empty rule list → exit 0 with a warning"
else
  fail "L5 profile problems" "$DETAIL empty rc=$RC $(q 'd["warnings"]')"
fi

# L6 — a rule scoped to a binding this run does not declare is reported, not
# silently inert.
mkprofile "$RIG/scoped.yml" '  wording_rules:' '    - { id: only_spec, category: non_concrete, severity: warn, applies_to: [ticket_item], scope: [spec_notes], regex: "x" }'
run lint --profile "$RIG/scoped.yml" --from-json "$RIG/hedged.json"
if [ "$RC" -eq 0 ] && [ "$(q 'any("only_spec is scoped to" in w and "spec_notes" in w for w in d["warnings"])')" = "True" ]; then
  pass "L6 scope naming an undeclared binding → warning"
else
  fail "L6 scope warning" "rc=$RC $(q 'd["warnings"]')"
fi

# L7 — the fetch path (what CI runs) and --from-json (what the skill runs on
# the file §1.5.1 kept) see the same hits; the fetch path fills `source`. A
# required binding section the ticket lacks exits 1 with `errors[]`, as
# `fetch` does — a malformed ticket is never "lint clean".
mkdir -p "$RIG/tickets"
python3 - "$RIG/hedged.md" "$RIG/tickets/T-9.json" <<'PYX'
import json, sys
json.dump({"id": "T-9", "title": "hedged", "url": "https://example.invalid/T-9",
           "body": open(sys.argv[1], encoding="utf-8").read(), "version": "rev-3"},
          open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PYX
run lint --profile "$BUNDLED_KO" --id T-9 --tracker jira --fetch-command "cat $RIG/tickets/{id}.json" --binding "$B_ACC" --binding "$B_QA"
F_RC=$RC; F_HITS="$(q "$HITS")"; F_SRC="$(q '(d["source"]["id"], d["source"]["version"], d["source"]["tracker"])')"
run lint --profile "$BUNDLED_KO" --id T-9 --fetch-command "cat $RIG/tickets/{id}.json" --binding "$B_ACC" --binding "missing=없는 섹션"
if [ "$F_RC" -eq 1 ] && [ "$F_HITS" = "$WANT" ] && [ "$F_SRC" = "('T-9', 'rev-3', 'jira')" ] \
  && [ "$RC" -eq 1 ] && [ "$(q 'any("binding section not found: missing" in e for e in d["errors"])')" = "True" ] \
  && [ "$(q '[a["id"] for a in d["absent"]]')" = "['missing']" ]; then
  pass "L7 fetch path = --from-json hits, source filled; missing required section → exit 1 + errors[]"
else
  fail "L7 fetch path" "rc=$F_RC src=$F_SRC hits=$F_HITS
missing rc=$RC $(q 'd["errors"]')"
fi

# L8 — usage errors exit 2 with a message, never a traceback: no input
# source, --binding beside --from-json (the JSON carries its own), a JSON that
# is not parser output.
run lint --profile "$BUNDLED_KO"
U1=$RC; E1=$ERR
run lint --profile "$BUNDLED_KO" --from-json "$RIG/hedged.json" --binding "$B_ACC"
U2=$RC; E2=$ERR
printf '{"bindings": [], "schema": 1}' >"$RIG/old.json"
run lint --profile "$BUNDLED_KO" --from-json "$RIG/old.json"
U3=$RC; E3=$ERR
if [ "$U1" -eq 2 ] && [ "$U2" -eq 2 ] && grep -qF -- '--from-json carries its own bindings' <<<"$E2" \
  && [ "$U3" -eq 2 ] && grep -qF 'this script reads schema 2' <<<"$E3" && ! grep -qF Traceback <<<"$E1$E2$E3"; then
  pass "L8 usage errors → exit 2 with a message"
else
  fail "L8 usage errors" "rc=$U1/$U2/$U3 $E1 | $E2 | $E3"
fi

# L9 — unpinned_oracle precision (v0.13.1). A document that is the DELIVERABLE
# being produced — the subject of 「…된다」 or the object of 「…한다」 with a
# production verb — is not an oracle; a provenance parenthetical led by a date
# or 「정정」 is stripped before matching. Their look-alikes stay flagged: an
# undated 「(Figma 기준)」, a design word between the document and the verb (the
# PRD revised to match an unpinned design), a document used as the basis for
# something else, and a dated parenthetical hiding a deferral.
cat >"$RIG/oracle.md" <<'MD'
### 완료 조건

- [ ] PRD 「상태 표출」·「상세 화면」가 표기 기준으로 개정된다(개정본 새 행)
- [ ] PRD 「안내 관리」이 텍스트 입력 기준으로 개정된다
- [ ] PRD 「쿠폰」를 표기 기준으로 개정한다
- [ ] 듀스는 제어 칸을 두지 않는다 (2026-10-01 정정 — PRD 「상세·제어」 기준)
- [ ] 듀스는 제어 칸을 두지 않는다 (Figma 기준)
- [ ] PRD가 Figma 시안에 맞춰 개정된다
- [ ] PRD를 기준으로 화면을 작성한다
- [ ] 표기 단위를 바꾼다 (2026-10-01 정정 — TBD)
MD
python3 "$SUT" parse "$RIG/oracle.md" --binding "$B_ACC" >"$RIG/oracle.json"
run lint --profile "$BUNDLED_KO" --from-json "$RIG/oracle.json"
GOT="$(q '[(h["in_group"], h["rule"]) for h in d["hits"]]')"
if [ "$RC" -eq 1 ] && [ "$GOT" = "[(5, 'unpinned_oracle'), (6, 'unpinned_oracle'), (7, 'unpinned_oracle'), (8, 'deferral')]" ]; then
  pass "L9 oracle precision: deliverable documents and provenance notes quiet; their look-alikes still block"
else
  fail "L9 oracle precision" "rc=$RC got=$GOT"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
