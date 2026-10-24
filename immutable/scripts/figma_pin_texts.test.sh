#!/usr/bin/env bash
# figma_pin_texts.test.sh — regression test for `figma_pin_texts.py`, the
# pinned-design reader `/immutable:prd` Stage 1.6 compares binding items with.
#
# WHY THIS FILE EXISTS
# A pilot Epic's binding items and its pinned design differed in two places (a
# notice missing on one toggle, a different toast order) and only a manual
# Figma REST diff caught it: the MCP tools read a file's current state, never a
# pinned version. This script is the reader for the pinned version. The cases
# pin what the comparison depends on: only version-id links are fetched (an
# unpinned link is listed, not read), only the named section counts, a missing
# token fails loudly instead of yielding an empty dump, screens and texts come
# out in reading order with soft breaks as newlines and hidden nodes skipped,
# and a pin that cannot be read is an error, not a silently shorter list.
#
# The responses are synthetic, shaped like the REST API's `files/:key/nodes`.
#
# Usage:  bash immutable/scripts/figma_pin_texts.test.sh
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  python3. No network — every fetch goes through --from-response.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUT="$SCRIPT_DIR/figma_pin_texts.py"
PARSER="$SCRIPT_DIR/requirement_contract.py"
[ -f "$SUT" ] || { echo "cannot run: $SUT not found" >&2; exit 2; }
command -v python3 >/dev/null || { echo "cannot run: python3 not found" >&2; exit 2; }

RIG="$(mktemp -d)"
trap 'rm -rf "$RIG"' EXIT
RIG="$(cd "$RIG" && pwd)"
mkdir -p "$RIG/responses"

cat >"$RIG/ticket.md" <<'MD'
### 완료 조건

- [ ] 홈 시트에서 동의하면 결과 토스트가 광고성 → 야간 → 마케팅 순서로 보인다
- [ ] 참고 [옛 시안](https://www.figma.com/design/OLDKEY/App?node-id=1-1&version-id=111)

### 기획 / 디자인

<!-- [주석 속 시안](https://www.figma.com/design/HIDDEN/App?node-id=9-9&version-id=999) -->
- 시안: [동의 시트·결과 토스트](https://www.figma.com/design/KEY1/Lounge%E2%80%99X-APP?version-id=2413576020041390627&node-id=18388-2385) · [알림 설정](https://www.figma.com/design/KEY1/Lounge%E2%80%99X-APP?version-id=2413576020041390627&node-id=18139-8602)
- 작업 중 파일: https://www.figma.com/design/KEY1/Lounge%E2%80%99X-APP?node-id=5-5
MD

# The home sheet section: three toast frames placed out of document order
# (children listed 마케팅, 광고성, 야간; stacked 광고성 → 마케팅 → 야간 by y), a
# hidden draft frame, a soft break inside one toast text.
cat >"$RIG/responses/KEY1_18388-2385_2413576020041390627.json" <<'JSON'
{"nodes": {"18388:2385": {"document": {"id": "18388:2385", "name": "01. 홈", "type": "SECTION", "children": [
  {"id": "2:1", "name": "토스트 / 마케팅", "type": "FRAME", "absoluteBoundingBox": {"x": 0, "y": 900, "width": 360, "height": 80},
   "children": [{"id": "2:2", "name": "문구", "type": "TEXT", "characters": "마케팅 활용에 동의했어요", "absoluteBoundingBox": {"x": 10, "y": 910, "width": 300, "height": 40}}]},
  {"id": "3:1", "name": "토스트 / 광고성", "type": "FRAME", "absoluteBoundingBox": {"x": 0, "y": 500, "width": 360, "height": 80},
   "children": [{"id": "3:2", "name": "문구", "type": "TEXT", "characters": "광고성 정보 수신에 동의했어요", "absoluteBoundingBox": {"x": 10, "y": 510, "width": 300, "height": 40}}]},
  {"id": "4:1", "name": "토스트 / 야간", "type": "FRAME", "absoluteBoundingBox": {"x": 0, "y": 1300, "width": 360, "height": 80},
   "children": [{"id": "4:2", "name": "문구", "type": "TEXT", "characters": "야간 수신에 동의했어요", "absoluteBoundingBox": {"x": 10, "y": 1310, "width": 300, "height": 40}},
                {"id": "4:3", "name": "숨김", "type": "TEXT", "visible": false, "characters": "지운 문구", "absoluteBoundingBox": {"x": 10, "y": 1300, "width": 300, "height": 40}}]},
  {"id": "5:1", "name": "초안", "type": "FRAME", "visible": false, "absoluteBoundingBox": {"x": 0, "y": 0, "width": 360, "height": 80}, "children": []}
]}}}}
JSON
# The settings screen: one frame (the node itself), texts top to bottom, two
# child frames (toggle rows) out of order.
cat >"$RIG/responses/KEY1_18139-8602_2413576020041390627.json" <<'JSON'
{"nodes": {"18139:8602": {"document": {"id": "18139:8602", "name": "알림 설정", "type": "FRAME", "absoluteBoundingBox": {"x": 0, "y": 0, "width": 360, "height": 800}, "children": [
  {"id": "7:1", "name": "행 / 마케팅", "type": "INSTANCE", "absoluteBoundingBox": {"x": 0, "y": 300, "width": 360, "height": 60},
   "children": [{"id": "7:2", "name": "라벨", "type": "TEXT", "characters": "마케팅 정보 활용", "absoluteBoundingBox": {"x": 16, "y": 310, "width": 200, "height": 20}}]},
  {"id": "6:1", "name": "행 / 광고성", "type": "INSTANCE", "absoluteBoundingBox": {"x": 0, "y": 200, "width": 360, "height": 60},
   "children": [{"id": "6:2", "name": "라벨", "type": "TEXT", "characters": "광고성 정보 수신", "absoluteBoundingBox": {"x": 16, "y": 210, "width": 200, "height": 20}}]},
  {"id": "8:1", "name": "제목", "type": "TEXT", "characters": "알림 설정", "absoluteBoundingBox": {"x": 16, "y": 40, "width": 200, "height": 30}}
]}}}}
JSON

FAILURES=0
PASSES=0
pass() { printf 'PASS  %s\n' "$1"; PASSES=$((PASSES + 1)); }
fail() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }
run() {  # run <args...> → RC, ERR; JSON in $RIG/out.json
  python3 "$SUT" "$@" >"$RIG/out.json" 2>"$RIG/stderr.txt" && RC=0 || RC=$?
  ERR=$(cat "$RIG/stderr.txt")
}
q() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))' "$RIG/out.json" "$1"; }

echo "figma_pin_texts.py — pinned-design reader"
echo

# F1 — only the named section counts, only version-id links are pins, node ids
# are API form (18388:2385), the link text is kept, a link inside an HTML
# comment is ignored, and an unpinned link is listed, not fetched.
run --body "$RIG/ticket.md" --section "기획 / 디자인" --from-response "$RIG/responses"
if [ "$RC" -eq 0 ] \
  && [ "$(q '[(p["file_key"], p["node_id"], p["version_id"], p["label"]) for p in d["pins"]]')" = "[('KEY1', '18388:2385', '2413576020041390627', '동의 시트·결과 토스트'), ('KEY1', '18139:8602', '2413576020041390627', '알림 설정')]" ] \
  && [ "$(q '[u["url"].split("?")[1] for u in d["unpinned"]]')" = "['node-id=5-5']" ] \
  && [ "$(q 'd["errors"]')" = "[]" ]; then
  pass "F1 section-scoped pins: version-id links only, API node ids, labels kept; comments ignored, unpinned listed"
else
  fail "F1 link extraction" "rc=$RC $ERR $(cat "$RIG/out.json")"
fi

# F2 — screens in reading order (y, then x), whatever the document order; texts
# per screen with U+2028 as a newline; hidden frames and texts skipped; a
# single-frame node is its own screen, with its child frames ordered.
if [ "$(q '[s["name"] for s in d["pins"][0]["screens"]]')" = "['토스트 / 광고성', '토스트 / 마케팅', '토스트 / 야간']" ] \
  && [ "$(q '[t["text"] for s in d["pins"][0]["screens"] for t in s["texts"]]')" = "['광고성 정보 수신에 동의했어요', '마케팅 활용에\n동의했어요', '야간 수신에 동의했어요']" ] \
  && [ "$(q '[(s["name"], [t["text"] for t in s["texts"]], [f["name"] for f in s["frames"]]) for s in d["pins"][1]["screens"]]')" = "[('알림 설정', ['알림 설정', '광고성 정보 수신', '마케팅 정보 활용'], ['행 / 광고성', '행 / 마케팅'])]" ]; then
  pass "F2 reading order: screens and texts by position, soft breaks as newlines, hidden nodes skipped"
else
  fail "F2 reading order" "$(q '[(s["name"], s["texts"], s["frames"]) for p in d["pins"] for s in p["screens"]]')"
fi

# F3 — no FIGMA_TOKEN and pins to fetch → exit 2 naming the variable, never an
# empty dump that reads as "nothing to compare". No pins → no token needed.
( unset FIGMA_TOKEN; python3 "$SUT" --body "$RIG/ticket.md" --section "기획 / 디자인" >"$RIG/out.json" 2>"$RIG/stderr.txt" ) && T_RC=0 || T_RC=$?
T_ERR=$(cat "$RIG/stderr.txt")
( unset FIGMA_TOKEN; python3 "$SUT" --body "$RIG/ticket.md" --section "비고" >"$RIG/out.json" 2>"$RIG/stderr.txt" ) && N_RC=0 || N_RC=$?
if [ "$T_RC" -eq 2 ] && grep -qF "FIGMA_TOKEN is not set — 2 pinned design link(s)" <<<"$T_ERR" \
  && [ "$N_RC" -eq 0 ] && [ "$(q 'd["pins"], d["unpinned"]')" = "([], [])" ]; then
  pass "F3 missing FIGMA_TOKEN with pins → exit 2 naming it; nothing to fetch → no token needed"
else
  fail "F3 token" "rc=$T_RC $T_ERR | none rc=$N_RC $(cat "$RIG/out.json")"
fi

# F4 — a pin that cannot be read (no saved response here, standing in for an
# API error) is an error with exit 1, and the other pin is still read.
rm "$RIG/responses/KEY1_18139-8602_2413576020041390627.json"
run --body "$RIG/ticket.md" --section "기획 / 디자인" --from-response "$RIG/responses"
if [ "$RC" -eq 1 ] && [ "$(q 'len(d["errors"])')" = "1" ] \
  && [ "$(q '[(p["node_id"], bool(p.get("error")), len(p["screens"])) for p in d["pins"]]')" = "[('18388:2385', False, 3), ('18139:8602', True, 0)]" ]; then
  pass "F4 an unreadable pin → exit 1 with the error; the other pins still read"
else
  fail "F4 unreadable pin" "rc=$RC $(q 'd["errors"]')"
fi

# F5 — --from-json reads the same section out of the parser's `sections[]`
# (what Stage 1.5 kept), so the skill needs no second fetch of the ticket.
# `sections[]` holds no text above the first heading, so a run without
# --section says so on stderr instead of implying it scanned the whole body.
python3 "$PARSER" parse "$RIG/ticket.md" --binding "acceptance=완료 조건" >"$RIG/parsed.json"
run --from-json "$RIG/parsed.json" --section "기획 / 디자인" --from-response "$RIG/responses"
J_RC=$RC; J_PINS="$(q '[p["node_id"] for p in d["pins"]]')"
run --from-json "$RIG/parsed.json" --from-response "$RIG/responses"
if [ "$J_RC" -eq 1 ] && [ "$J_PINS" = "['18388:2385', '18139:8602']" ] \
  && grep -qF "not text above the first heading — use --body" <<<"$ERR"; then
  pass "F5 --from-json: the parser's sections[] give the same pins; without --section it says what it cannot see"
else
  fail "F5 from-json" "rc=$J_RC pins=$J_PINS | no-section stderr: $ERR"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
