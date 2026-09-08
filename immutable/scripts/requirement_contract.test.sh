#!/usr/bin/env bash
# requirement_contract.test.sh — regression test for `requirement_contract.py`,
# the Epic-body parser behind the requirement contract.
#
# WHY THIS FILE EXISTS
# Two consumers read a tracker Epic through this parser — `/immutable:prd`
# at authoring time and a spec repo's CI drift check later — and the contract
# only works if both see the SAME items with the SAME text. The cases below
# pin the shapes a real Epic template produces that a naive heading split
# gets wrong: whole-line `**bold**` group labels between `###` headings,
# guidance shipped inside HTML comments (which must never become items),
# fenced code (which must never become headings or items), continuation
# lines, struck-through items, nested and checkbox-less bullets. They also
# pin the failure contract: a missing or empty binding section is reported
# in `errors` with exit 1 and the JSON still emitted, never a traceback —
# most `ux` Epics in the wild predate the template and are malformed.
#
# The fixture is synthetic. It mirrors the SHAPE of the pilot's Epic
# template, not any real ticket's content.
#
# Usage:  bash immutable/scripts/requirement_contract.test.sh
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  python3 only — no PyYAML, no git, no network (`fetch` is exercised
#         through a stub `gh` placed first on PATH).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUT="$SCRIPT_DIR/requirement_contract.py"
[ -f "$SUT" ] || { echo "cannot run: $SUT not found" >&2; exit 2; }
command -v python3 >/dev/null || { echo "cannot run: python3 not found" >&2; exit 2; }

RIG="$(mktemp -d)"
trap 'rm -rf "$RIG"' EXIT
RIG="$(cd "$RIG" && pwd)"

B_ACC='acceptance=완료 조건'
B_QA='qa_checklist=QA 통과 리스트'

# --- main fixture: the Epic template's shape, with every trap the parser must survive ---
cat >"$RIG/epic.md" <<'MD'
### 프로젝트 / 목표 버전 / 종류

- 프로젝트: Sample
- 종류: 기획 (`epic: ux`)

### 사용자 시나리오

A user does a thing and sees a result.

### 요구사항

<!-- guidance only — links, never definitions
- [ ] this line lives in a comment and is not an item -->
Definitions stay in the linked rows.

- [Row A](https://example.invalid/a) (policy) — one line

### QA 통과 리스트

<!-- - [ ] 항목 0 — template guidance, must not parse -->

**표시**

- [ ] 카트에 1잔을 담는다 → 적립 예정 1개가 표시된다
- [x] 완료 화면의 값이 주문서와 같다

**시점**

- [ ] 제조 완료 뒤 보유 수가 늘어난다

### 완료 조건

**적립**

- [ ] 1,000원 이상 주문에서 잔당 스탬프 1개가 적립된다
- [ ] 2잔 이상은 잔 수만큼 적립된다
  이어지는 설명 줄
- [ ] ~~옛 기준으로 적립된다~~

#### 발급

- [ ] 스탬프 10개가 모이면 쿠폰이 자동 발급된다
  - [ ] 부분 발급은 없다
- 체크박스 없는 항목
1. 번호 목록 항목

이 줄은 항목이 아니다.

```text
### 완료 조건
- [ ] 코드 블록 안의 가짜 항목
```

- [ ]
- [ ] 1,000원 이상 주문에서 잔당 스탬프 1개가 적립된다

### 비고

**미해결**

- 적립 제외 기준이 갈려 있다 — 앱은 1,000원 미만, 서버는 0원

## Schedule
<!-- 보드 값이 동기화됩니다 -->
- Start: _Not set_
MD

FAILURES=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }

# run <args...> → RC, OUT (stdout), ERR (stderr); JSON also saved to $RIG/out.json
run() {
  OUT=$(python3 "$SUT" "$@" 2>"$RIG/stderr.txt") && RC=0 || RC=$?
  ERR=$(cat "$RIG/stderr.txt")
  printf '%s' "$OUT" >"$RIG/out.json"
}
# q <python expression over d> — evaluate against the last JSON output
q() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))' "$RIG/out.json" "$1"; }

echo "requirement_contract.py — Epic body parser contract"
echo

# C1 — groups + counts: bold labels AND a deeper heading both open a group;
# ordinals run across groups; the comment-only and fenced items never count.
run parse "$RIG/epic.md" --binding "$B_ACC" --binding "$B_QA"
GOT="$(q '[(b["id"], b["found"], b["level"], b["item_count"], [(g["label"], len(g["items"])) for g in b["groups"]]) for b in d["bindings"]]')"
WANT="[('acceptance', True, 3, 8, [('적립', 3), ('발급', 5)]), ('qa_checklist', True, 3, 3, [('표시', 2), ('시점', 1)])]"
if [ "$RC" -eq 0 ] && [ "$GOT" = "$WANT" ]; then
  pass "C1 groups and counts (bold label + #### both group; ordinals span groups)"
else
  fail "C1 groups and counts" "rc=$RC
--- got ---
$GOT
--- want ---
$WANT"
fi

# C2 — HTML comments are blanked before anything is read: no item from a
# comment, and the section outline still carries the right line numbers.
if [ "$(q '"항목 0" in json.dumps(d, ensure_ascii=False)')" = "False" ] \
  && [ "$(q '[s["line"] for s in d["sections"] if s["heading"]=="완료 조건"]')" = "[31]" ]; then
  pass "C2 HTML comments yield nothing and line numbers stay stable"
else
  fail "C2 HTML comments" "$(q '[s["line"] for s in d["sections"]]')"
fi

# C3 — fenced code: the `### 완료 조건` inside the fence is not a heading
# (else the section would be matched twice) and the fenced item is not an item.
if [ "$(q 'len([s for s in d["sections"] if s["heading"]=="완료 조건"])')" = "1" ] \
  && [ "$(q '"코드 블록 안의" in json.dumps([b["groups"] for b in d["bindings"]], ensure_ascii=False)')" = "False" ] \
  && [ "$(q 'any("fenced code" in w for w in d["warnings"])')" = "True" ]; then
  pass "C3 fenced code is neither heading nor item, and is warned about"
else
  fail "C3 fenced code" "$(q 'd["warnings"]')"
fi

# C4 — item fields: continuation joins, struck flagged, nested depth, checkbox
# vs plain vs ordered, checked state — the exact shape the quote block consumes.
GOT="$(q '[(i["ordinal"], i["group"], i["depth"], i["checkbox"], i["checked"], i["struck"], i["text"]) for g in d["bindings"][0]["groups"] for i in g["items"]]')"
WANT="[(1, '적립', 0, True, False, False, '1,000원 이상 주문에서 잔당 스탬프 1개가 적립된다'), (2, '적립', 0, True, False, False, '2잔 이상은 잔 수만큼 적립된다 이어지는 설명 줄'), (3, '적립', 0, True, False, True, '~~옛 기준으로 적립된다~~'), (4, '발급', 0, True, False, False, '스탬프 10개가 모이면 쿠폰이 자동 발급된다'), (5, '발급', 1, True, False, False, '부분 발급은 없다'), (6, '발급', 0, False, None, False, '체크박스 없는 항목'), (7, '발급', 0, False, None, False, '번호 목록 항목'), (8, '발급', 0, True, False, False, '1,000원 이상 주문에서 잔당 스탬프 1개가 적립된다')]"
if [ "$GOT" = "$WANT" ]; then
  pass "C4 item fields (continuation, struck, depth, checkbox/plain/ordered, checked)"
else
  fail "C4 item fields" "--- got ---
$GOT
--- want ---
$WANT"
fi
if [ "$(q '[(i["ordinal"], i["checked"]) for g in d["bindings"][1]["groups"] for i in g["items"]]')" = "[(1, False), (2, True), (3, False)]" ]; then
  pass "C4b checked state survives"
else
  fail "C4b checked state" "$(q 'd["bindings"][1]')"
fi

# C5 — nothing is dropped silently: prose line, empty item, plain bullets,
# duplicate text each leave a warning that names the line.
W="$(q '"\n".join(d["warnings"])')"
if grep -qF 'line 47 is not a list item' <<<"$W" \
  && grep -qF 'empty list item ignored (line 54)' <<<"$W" \
  && grep -qF '2 list item(s) without a task-list checkbox' <<<"$W" \
  && grep -qF 'duplicate item text at lines 35 and 55' <<<"$W"; then
  pass "C5 prose / empty / plain / duplicate each warn with a line number"
else
  fail "C5 warnings" "$W"
fi

# C6 — the outline carries non-binding context: the classifier reads the
# 비고 / 미해결 note from `sections`, and binding sections are tagged.
if [ "$(q '[(s["heading"], s["binding"]) for s in d["sections"] if s["binding"]]')" = "[('QA 통과 리스트', 'qa_checklist'), ('완료 조건', 'acceptance')]" ] \
  && [ "$(q '"미해결" in [s for s in d["sections"] if s["heading"]=="비고"][0]["text"] and "0원" in [s for s in d["sections"] if s["heading"]=="비고"][0]["text"]')" = "True" ] \
  && [ "$(q '[s["heading"] for s in d["sections"]][-1]')" = "Schedule" ]; then
  pass "C6 sections outline: binding tags + non-binding context text"
else
  fail "C6 sections outline" "$(q '[(s["heading"], s["level"], s["binding"]) for s in d["sections"]]')"
fi

# C7 — missing binding section: exit 1, JSON still emitted, error names what
# IS there. This is the old-format Epic in the wild.
printf '%s\n' '### 요구사항' '' '- link' '' '### QA 통과 리스트' '' '- [ ] one' >"$RIG/old.md"
run parse "$RIG/old.md" --binding "$B_ACC" --binding "$B_QA"
if [ "$RC" -eq 1 ] \
  && [ "$(q '[(b["id"], b["found"], b["item_count"]) for b in d["bindings"]]')" = "[('acceptance', False, 0), ('qa_checklist', True, 1)]" ] \
  && [ "$(q 'd["errors"]')" = "['binding section not found: acceptance (완료 조건) — headings present: ### 요구사항, ### QA 통과 리스트']" ]; then
  pass "C7 missing binding section → exit 1, JSON kept, headings listed"
else
  fail "C7 missing section" "rc=$RC errors=$(q 'd["errors"]') stderr=$ERR"
fi

# C8 — empty binding section (heading present, guidance comment only): exit 1.
printf '%s\n' '### 완료 조건' '' '<!-- - [ ] 조건 1 -->' '' '### QA 통과 리스트' '' '- [ ] one' >"$RIG/empty.md"
run parse "$RIG/empty.md" --binding "$B_ACC" --binding "$B_QA"
if [ "$RC" -eq 1 ] && [ "$(q 'd["errors"]')" = "['binding section has no list items: acceptance (완료 조건) (line 1)']" ]; then
  pass "C8 empty binding section → exit 1 with a named error"
else
  fail "C8 empty section" "rc=$RC errors=$(q 'd["errors"]')"
fi

# C9 — heading match is forgiving where humans vary: 「」, trailing colon,
# level, case; a duplicate heading is used-first-and-warned, not fatal; and a
# deeper heading inside a section is a group of that section (the level-3
# `### 완료 조건` here belongs to the level-2 qa section → its 2nd item).
printf '%s\n' '## 「완료 조건」:' '' '- [ ] a' '' '## qa 통과 리스트' '' '- [ ] b' '' '### 완료 조건' '' '- [ ] c' >"$RIG/norm.md"
run parse "$RIG/norm.md" --binding "$B_ACC" --binding "$B_QA"
if [ "$RC" -eq 0 ] \
  && [ "$(q '[(b["found"], b["matched_heading"], b["level"], b["item_count"]) for b in d["bindings"]]')" = "[(True, '「완료 조건」:', 2, 1), (True, 'qa 통과 리스트', 2, 2)]" ] \
  && [ "$(q 'any("2 headings match" in w for w in d["warnings"])')" = "True" ]; then
  pass "C9 heading normalisation (「」, colon, level, case) + duplicate-heading warning"
else
  fail "C9 heading normalisation" "rc=$RC $(q '[(b["found"], b["matched_heading"], b["level"]) for b in d["bindings"]]') warnings=$(q 'd["warnings"]')"
fi

# C10 — stdin and CRLF: `-` reads stdin; a CRLF body parses to identical items.
run parse "$RIG/epic.md" --binding "$B_ACC" --compact
LF_ITEMS="$(q '[i["text"] for g in d["bindings"][0]["groups"] for i in g["items"]]')"
python3 -c 'import sys; open(sys.argv[2],"wb").write(open(sys.argv[1],"rb").read().replace(b"\n", b"\r\n"))' "$RIG/epic.md" "$RIG/epic-crlf.md"
OUT=$(python3 "$SUT" parse - --binding "$B_ACC" --compact <"$RIG/epic-crlf.md" 2>"$RIG/stderr.txt") && RC=0 || RC=$?
printf '%s' "$OUT" >"$RIG/out.json"
if [ "$RC" -eq 0 ] && [ "$(q '[i["text"] for g in d["bindings"][0]["groups"] for i in g["items"]]')" = "$LF_ITEMS" ] \
  && [ "$(wc -l <<<"$OUT" | tr -d ' ')" = "1" ]; then
  pass "C10 stdin (-) + CRLF body parse identically; --compact is one line"
else
  fail "C10 stdin/CRLF" "rc=$RC"
fi

# C11 — usage errors exit 2 with a message, never a traceback: no --binding,
# malformed --binding, duplicate id, bad --repo.
run parse "$RIG/epic.md"
U1=$RC; E1=$ERR
run parse "$RIG/epic.md" --binding "nonsense"
U2=$RC
run parse "$RIG/epic.md" --binding "$B_ACC" --binding "acceptance=Other"
U3=$RC
run fetch --repo "not a repo" --issue 1 --binding "$B_ACC"
U4=$RC
if [ "$U1$U2$U3$U4" = "2222" ] && grep -qF -- '--binding ID=HEADING is required' <<<"$E1" && ! grep -qF 'Traceback' <<<"$E1"; then
  pass "C11 usage errors exit 2 (missing/malformed/duplicate --binding, bad --repo)"
else
  fail "C11 usage errors" "rc=$U1$U2$U3$U4 stderr=$E1"
fi

# C12 — fetch through a stub gh: `source` is populated from the gh JSON, the
# body is parsed the same way, and the exact gh invocation is pinned.
mkdir -p "$RIG/bin"
python3 - "$RIG/epic.md" "$RIG/gh.json" <<'PYX'
import json, sys
body = open(sys.argv[1], encoding="utf-8").read()
json.dump({
    "number": 3755, "title": "[EPIC] Sample", "body": body, "state": "OPEN",
    "url": "https://example.invalid/acme/tracker/issues/3755",
    "labels": [{"name": "ux"}, {"name": "type: feature"}],
    "milestone": {"title": "Sample v1.0"}, "updatedAt": "2026-09-07T01:02:03Z",
}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PYX
cat >"$RIG/bin/gh" <<SH2
#!/usr/bin/env bash
printf '%s\n' "\$*" >"$RIG/gh-args.txt"
cat "$RIG/gh.json"
SH2
chmod +x "$RIG/bin/gh"
OUT=$(PATH="$RIG/bin:$PATH" python3 "$SUT" fetch --repo acme/tracker --issue 3755 --binding "$B_ACC" --binding "$B_QA" 2>"$RIG/stderr.txt") && RC=0 || RC=$?
printf '%s' "$OUT" >"$RIG/out.json"
if [ "$RC" -eq 0 ] \
  && [ "$(q '(d["source"]["tracker"], d["source"]["repo"], d["source"]["number"], d["source"]["labels"], d["source"]["milestone"], d["source"]["updated_at"])')" = "('github', 'acme/tracker', 3755, ['ux', 'type: feature'], 'Sample v1.0', '2026-09-07T01:02:03Z')" ] \
  && [ "$(q 'bool(__import__("re").fullmatch(r"\d{4}-\d{2}-\d{2}", d["source"]["as_of"])) and d["source"]["fetched_at"].startswith(d["source"]["as_of"])')" = "True" ] \
  && [ "$(q '[b["item_count"] for b in d["bindings"]]')" = "[8, 3]" ] \
  && [ "$(cat "$RIG/gh-args.txt")" = "issue view 3755 --repo acme/tracker --json number,title,body,url,state,labels,milestone,updatedAt" ]; then
  pass "C12 fetch: source populated, body parsed, gh invocation pinned"
else
  fail "C12 fetch" "rc=$RC args=$(cat "$RIG/gh-args.txt" 2>/dev/null) source=$(q 'd["source"]') stderr=$(cat "$RIG/stderr.txt")"
fi

# C13 — fetch when gh fails: exit 2, gh's stderr relayed, no traceback.
cat >"$RIG/bin/gh" <<'SH2'
#!/usr/bin/env bash
echo "GraphQL: Could not resolve to an Issue (404)" >&2
exit 1
SH2
OUT=$(PATH="$RIG/bin:$PATH" python3 "$SUT" fetch --repo acme/tracker --issue 999999 --binding "$B_ACC" 2>"$RIG/stderr.txt") && RC=0 || RC=$?
ERR=$(cat "$RIG/stderr.txt")
if [ "$RC" -eq 2 ] && grep -qF 'gh exited 1 for acme/tracker#999999' <<<"$ERR" && grep -qF 'Could not resolve' <<<"$ERR" && ! grep -qF 'Traceback' <<<"$ERR"; then
  pass "C13 fetch failure → exit 2, gh stderr relayed, no traceback"
else
  fail "C13 fetch failure" "rc=$RC stderr=$ERR"
fi

# C14 — canonical `text`: NFD (decomposed Hangul, as some editors emit) and
# ragged whitespace normalise to the same string a clean NFC body yields —
# otherwise a quote taken on one machine drifts against the same ticket read
# on another.
python3 - "$RIG/nfd.md" <<'PYX'
import sys, unicodedata
body = "### 완료 조건\n\n- [ ]   결제   금액이\t1,000원 \n- [ ] 두 번째\n"
open(sys.argv[1], "w", encoding="utf-8").write(unicodedata.normalize("NFD", body))
PYX
run parse "$RIG/nfd.md" --binding "$B_ACC"
if [ "$RC" -eq 0 ] && [ "$(q '[i["text"] for g in d["bindings"][0]["groups"] for i in g["items"]]')" = "['결제 금액이 1,000원', '두 번째']" ] \
  && [ "$(q 'all(__import__("unicodedata").is_normalized("NFC", i["text"]) for g in d["bindings"][0]["groups"] for i in g["items"])')" = "True" ]; then
  pass "C14 canonical text: NFD → NFC, whitespace runs collapsed, edges trimmed"
else
  fail "C14 canonical text" "rc=$RC $(q '[i["text"] for g in d["bindings"][0]["groups"] for i in g["items"]]')"
fi

# C15 — a body that is not UTF-8 is a usage error (exit 2, message), never a
# traceback; and the UTF-8 read/write path does not depend on the locale.
printf '### x\n- [ ] \xea\xb0\n' >"$RIG/latin.md"
run parse "$RIG/latin.md" --binding "$B_ACC"
U5=$RC; E5=$ERR
OUT=$(LC_ALL=C LANG=C python3 "$SUT" parse "$RIG/epic.md" --binding "$B_ACC" --compact 2>"$RIG/stderr.txt") && RC=0 || RC=$?
printf '%s' "$OUT" >"$RIG/out.json"
if [ "$U5" -eq 2 ] && grep -qF 'cannot read body' <<<"$E5" && ! grep -qF 'Traceback' <<<"$E5" \
  && [ "$RC" -eq 0 ] && [ "$(q 'd["bindings"][0]["item_count"]')" = "8" ]; then
  pass "C15 non-UTF-8 body → exit 2 without traceback; C locale reads/writes UTF-8 fine"
else
  fail "C15 encoding contract" "rc=$U5/$RC stderr=$E5 $(cat "$RIG/stderr.txt")"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all 15 cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
