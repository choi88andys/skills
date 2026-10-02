#!/usr/bin/env bash
# requirement_contract_gate.test.sh — regression test for
# `requirement_contract.py gate`, the spec repo's merge gate (v0.15.0).
#
# WHY THIS FILE EXISTS
# `lint` finds block hits on a ticket, but nothing stopped a pitch from merging
# while bound to one: a pilot pitch handled an unpinned-oracle QA item with
# `delegates: Figma` and passed every check. The gate closes that. For every
# ticket an ACTIVE pitch cites, each block hit must be contested by a
# disagreement entry in a citing pitch or acknowledged in the repo's ledger
# (`.immutable-prd/contract-acknowledgements.yml`); `delegates` resolves
# nothing. An acknowledgement whose hit is gone is STALE, so an exemption
# cannot outlive its cause. The cases pin those verdicts, the off / warn / on
# switch, and that the gate fails closed: a ticket it cannot fetch, a ledger it
# cannot trust, a deprecated pitch's disagreement — none buys a pass.
#
# The fixtures are synthetic. Ticket 4431 mirrors the SHAPE of the pilot's
# case: one block hit, QA 4 「…시안과 일치한다」 (unpinned_oracle).
#
# Usage:  bash immutable/scripts/requirement_contract_gate.test.sh
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  python3 + PyYAML. No git, no network — tickets come from a
#         --fetch-command adapter reading local JSON.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUT="$SCRIPT_DIR/requirement_contract.py"
PROFILE="$SCRIPT_DIR/../examples/_profiles/default-ko.yml"
[ -f "$SUT" ] || { echo "cannot run: $SUT not found" >&2; exit 2; }
[ -f "$PROFILE" ] || { echo "cannot run: $PROFILE not found" >&2; exit 2; }
python3 -c 'import yaml' 2>/dev/null || { echo "cannot run: gate needs PyYAML (pip install pyyaml)" >&2; exit 2; }

RIG="$(mktemp -d)"
trap 'rm -rf "$RIG"' EXIT
RIG="$(cd "$RIG" && pwd)"
mkdir -p "$RIG/tickets" "$RIG/pitches"

mkticket() {  # mkticket <id> <body-file>
  python3 - "$2" "$RIG/tickets/$1.json" "$1" <<'PYX'
import json, sys
json.dump({"id": sys.argv[3], "title": "t", "url": "https://example.invalid/" + sys.argv[3],
           "body": open(sys.argv[1], encoding="utf-8").read(), "version": "v1"},
          open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PYX
}
cat >"$RIG/4431.md" <<'MD'
### 완료 조건

- [ ] 주문 카드에 증정 상품이 이벤트 개수로 따로 표기된다
- [ ] 증정 여부를 모르면 기존 표기로 둔다

### QA 통과 리스트

- [ ] 증정 상품이 있는 주문을 본다 → 이벤트 개수가 따로 보인다
- [ ] 증정 상품이 없는 주문을 본다 → 기존 표기다
- [ ] 증정 여부를 모르는 주문을 본다 → 기존 표기다
- [ ] 표기 배지 형태가 시안과 일치한다
MD
mkticket 4431 "$RIG/4431.md"
cat >"$RIG/5000.md" <<'MD'
### 완료 조건

**적립**

- [ ] 잔당 스탬프 1개가 적립된다
- [ ] 이벤트 주문은 필요 시 적립한다

### QA 통과 리스트

- [ ] 주문한다 → 스탬프가 늘어난다
MD
mkticket 5000 "$RIG/5000.md"

mkpitch() {  # mkpitch <file> <deprecated> <ticket ids, space-separated> [body]
  { echo '---'; echo 'domain: order-status'; echo 'supersedes: null'; echo "deprecated: $2"
    echo 'references:'; echo '  tickets:'
    for t in $3; do
      echo '    - tracker: github'; echo '      repo: acme/tracker'; echo "      id: \"$t\""; echo '      version: "v1"'
      if [ "$t" = 4431 ]; then
        echo '      delegates:'; echo '        - binding: qa_checklist'; echo '          group: null'
        echo '          items: [4]'; echo '          to: Figma'; echo '          why: 배지 형태의 진실 소스는 시안'
      fi
    done
    echo '---'; echo; echo '# 제목'; echo; printf '%s\n' "${4:-}"; } >"$RIG/pitches/$1"
}
CONTEST_4431='## 요구사항 이견

### github acme/tracker#4431 · QA 통과 리스트 · 4

- **원문** 표기 배지 형태가 시안과 일치한다
- **정정** 증정 배지는 「이벤트 N개」 문구로 표기된다
- **사유** 구속 위임 — 고정되지 않은 시안
- **결과** 합의 — 10/2'
CONTEST_5000='### github acme/tracker#5000 · 완료 조건 · 적립 2

- **원문** 이벤트 주문은 필요 시 적립한다
- **정정** 이벤트 주문도 잔당 1개 적립한다
- **사유** 구체성 결함 — 「필요 시」
- **결과** 합의 — 10/2'

mkledger() {  # mkledger <file> <entry yaml lines...>
  local f="$RIG/$1"; shift
  { echo 'schema: 1'; echo 'acknowledgements:'; printf '%s\n' "$@"; } >"$f"
}
ACK_4431=(
  '  - tracker: github'
  '    repo: acme/tracker'
  '    id: "4431"'
  '    binding: qa_checklist'
  '    group: null'
  '    in_group: 4'
  '    rule: unpinned_oracle'
  '    kind: accepted_violation'
  '    reason: 규칙 이전에 머지된 pitch 가 시안을 기준으로 묶여 있다 — 이 건만 예외'
  '    decided_by: owner'
  '    date: 2026-10-02'
)

FAILURES=0
PASSES=0
pass() { printf 'PASS  %s\n' "$1"; PASSES=$((PASSES + 1)); }
fail() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }

gate() {  # gate <mode> [--ledger FILE] <pitch files...> → RC, ERR, $RIG/out.json
  local mode="$1"; shift
  python3 "$SUT" gate --mode "$mode" --profile "$PROFILE" --repo acme/tracker \
    --fetch-command "cat $RIG/tickets/{id}.json" \
    --binding "acceptance=완료 조건" --binding "qa_checklist=QA 통과 리스트" "$@" \
    >"$RIG/out.json" 2>"$RIG/stderr.txt" && RC=0 || RC=$?
  ERR=$(cat "$RIG/stderr.txt")
}
q() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))' "$RIG/out.json" "$1"; }
REM='[(r["id"], r["binding"], r["group"], r["in_group"], r["rule"]) for r in d["remaining"]]'

echo "requirement_contract.py gate — spec-repo merge gate"
echo

# G1 — the pilot's case, settled: the pitch delegates QA 4 to Figma (which
# resolves nothing) and the ledger acknowledges that one hit as an accepted
# violation → pass, resolved by the ledger with its kind.
mkpitch bound.md false "4431"
mkledger ack.yml "${ACK_4431[@]}"
gate on --ledger "$RIG/ack.yml" "$RIG/pitches/bound.md"
if [ "$RC" -eq 0 ] && [ "$(q 'd["verdict"]')" = "pass" ] \
  && [ "$(q '[(r["in_group"], r["by"], r.get("kind")) for r in d["resolved"]]')" = "[(4, 'ledger', 'accepted_violation')]" ]; then
  pass "G1 accepted_violation entry acknowledges the delegated QA 4 hit → pass"
else
  fail "G1 acknowledged" "rc=$RC $(q 'd["verdict"], d["remaining"], d["stale"], d["ledger"]')"
fi

# G2 — the same pitch with no ledger: `delegates` alone resolves nothing, so the
# hit remains, named by its ledger coordinate and the pitch that cites it.
gate on "$RIG/pitches/bound.md"
if [ "$RC" -eq 1 ] && [ "$(q 'd["verdict"]')" = "fail" ] \
  && [ "$(q "$REM")" = "[('4431', 'qa_checklist', None, 4, 'unpinned_oracle')]" ] \
  && [ "$(q 'd["remaining"][0]["cited_by"][0].endswith("bound.md")')" = "True" ]; then
  pass "G2 delegates-only, no acknowledgement → fail with the remaining hit"
else
  fail "G2 delegates-only" "rc=$RC $(q 'd["verdict"], d["remaining"]')"
fi

# G3 — eviction: an entry for a hit the ticket no longer has (in_group 3), and
# one for a ticket no active pitch cites, are stale → fail, each with its why;
# the valid entry still resolves QA 4.
mkledger stale.yml "${ACK_4431[@]}" \
  '  - {tracker: github, repo: acme/tracker, id: "4431", binding: qa_checklist, group: null, in_group: 3, rule: unpinned_oracle, kind: false_positive, reason: 옛 항목, decided_by: owner, date: 2026-10-01}' \
  '  - {tracker: github, repo: acme/tracker, id: "9999", binding: acceptance, group: null, in_group: 1, rule: deferral, kind: accepted_violation, reason: 폐기된 pitch, decided_by: owner, date: 2026-10-01}'
gate on --ledger "$RIG/stale.yml" "$RIG/pitches/bound.md"
if [ "$RC" -eq 1 ] && [ "$(q 'len(d["remaining"])')" = "0" ] \
  && [ "$(q '[(s["index"], s["why"].split(" (")[0]) for s in d["stale"]]')" = "[(2, 'the live ticket has no block hit with that coordinate and rule'), (3, 'no active pitch cites that ticket')]" ]; then
  pass "G3 stale acknowledgements (hit gone, ticket uncited) → fail, each with its reason"
else
  fail "G3 stale" "rc=$RC $(q 'd["stale"], d["remaining"]')"
fi

# G4 — a disagreement entry in a citing pitch contests the item → pass with no
# ledger, for an ungrouped header (「… · QA 통과 리스트 · 4」) and a grouped one
# (「… · 완료 조건 · 적립 2」) alike.
mkpitch contested.md false "4431 5000" "$CONTEST_4431

$CONTEST_5000"
gate on "$RIG/pitches/contested.md"
if [ "$RC" -eq 0 ] && [ "$(q 'd["verdict"]')" = "pass" ] \
  && [ "$(q 'sorted((r["id"], r["group"], r["in_group"], r["by"]) for r in d["resolved"])')" = "[('4431', None, 4, 'disagreement'), ('5000', '적립', 2, 'disagreement')]" ]; then
  pass "G4 disagreement entries contest the hits (ungrouped and grouped headers) → pass"
else
  fail "G4 disagreement" "rc=$RC $(q 'd["remaining"], d["unmatched_disagreements"]')"
fi

# G5 — fail closed on what does not count: a DEPRECATED pitch's disagreement
# contests nothing (and its ticket is checked through the active pitch), and a
# disagreement header for a ticket the pitch does not cite is reported, not used.
mkpitch dead.md true "4431" "$CONTEST_4431"
mkpitch stray.md false "5000" "$CONTEST_4431"
gate on "$RIG/pitches/bound.md" "$RIG/pitches/dead.md" "$RIG/pitches/stray.md"
if [ "$RC" -eq 1 ] && [ "$(q "$REM")" = "[('4431', 'qa_checklist', None, 4, 'unpinned_oracle'), ('5000', 'acceptance', '적립', 2, 'conditional')]" ] \
  && [ "$(q '[u["why"] for u in d["unmatched_disagreements"]]')" = "['header names a ticket this pitch does not cite']" ]; then
  pass "G5 deprecated pitch and uncited-ticket headers resolve nothing → fail"
else
  fail "G5 fail closed" "rc=$RC $(q "$REM"), $(q 'd["unmatched_disagreements"]')"
fi

# G6 — the switch: warn reports the same verdict basis but exits 0 and says on
# stderr what would fail; off fetches nothing (an adapter that would fail is
# never run) and exits 0.
gate warn "$RIG/pitches/bound.md"
W_RC=$RC; W_V="$(q 'd["verdict"]')"; W_ERR=$ERR
python3 "$SUT" gate --mode off --profile "$PROFILE" --fetch-command "false" \
  --binding "acceptance=완료 조건" "$RIG/pitches/bound.md" >"$RIG/out.json" 2>"$RIG/stderr.txt" && RC=0 || RC=$?
if [ "$W_RC" -eq 0 ] && [ "$W_V" = "warn" ] && grep -qF "1 unresolved block hit(s)" <<<"$W_ERR" \
  && [ "$RC" -eq 0 ] && [ "$(q 'd["verdict"]')" = "off" ]; then
  pass "G6 warn → exit 0 + stderr summary; off → exit 0, nothing fetched"
else
  fail "G6 modes" "warn rc=$W_RC verdict=$W_V err=$W_ERR | off rc=$RC $(cat "$RIG/stderr.txt")"
fi

# G7 — a cited ticket that cannot be fetched is not "clean": exit 2 with the
# ticket named, and its acknowledgement is not judged stale on missing data.
mkpitch ghost.md false "7777"
mkledger ghost.yml '  - {tracker: github, repo: acme/tracker, id: "7777", binding: acceptance, group: null, in_group: 1, rule: deferral, kind: accepted_violation, reason: x, decided_by: owner, date: 2026-10-02}'
gate on --ledger "$RIG/ghost.yml" "$RIG/pitches/ghost.md"
if [ "$RC" -eq 2 ] && [ "$(q 'd["verdict"]')" = "fail" ] && [ "$(q 'd["stale"]')" = "[]" ] \
  && [ "$(q 'any("7777: could not fetch" in e for e in d["errors"])')" = "True" ]; then
  pass "G7 unfetchable cited ticket → exit 2, its acknowledgement not judged stale"
else
  fail "G7 fetch failure" "rc=$RC $(q 'd["errors"], d["stale"]')"
fi

# G8 — a ledger the gate cannot trust fails it: an unknown key (a typo'd
# coordinate would silently widen the exemption), a bad kind, a duplicate.
mkledger bad.yml "${ACK_4431[@]}" "${ACK_4431[@]}" \
  '  - {tracker: github, id: "4431", binding: qa_checklist, group: null, ingroup: 4, rule: unpinned_oracle, kind: waived, reason: x, decided_by: owner, date: 2026-10-02}'
gate on --ledger "$RIG/bad.yml" "$RIG/pitches/bound.md"
if [ "$RC" -eq 1 ] && [ "$(q 'len(d["ledger"]["problems"])')" = "2" ] \
  && [ "$(q 'any("same coordinate and rule as acknowledgements[1]" in p for p in d["ledger"]["problems"])')" = "True" ] \
  && [ "$(q 'any("unknown key(s) [" in p and "kind" in p for p in d["ledger"]["problems"])')" = "True" ]; then
  pass "G8 malformed ledger (unknown key, bad kind, duplicate) → fail with the problems"
else
  fail "G8 ledger problems" "rc=$RC $(q 'd["ledger"]')"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
