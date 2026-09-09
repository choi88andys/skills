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
# Needs:  python3 only — no PyYAML, no git, no network (`fetch` and `drift`
#         are exercised through a stub `gh` placed first on PATH, and through
#         a custom --fetch-command adapter).

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
run fetch --repo "not a repo" --id 1 --binding "$B_ACC"
U4=$RC
if [ "$U1$U2$U3$U4" = "2222" ] && grep -qF -- '--binding ID=HEADING is required' <<<"$E1" && ! grep -qF 'Traceback' <<<"$E1"; then
  pass "C11 usage errors exit 2 (missing/malformed/duplicate --binding, bad --repo)"
else
  fail "C11 usage errors" "rc=$U1$U2$U3$U4 stderr=$E1"
fi

# C12 — fetch through a stub gh: `source` is populated from the GraphQL
# answer, the body is parsed the same way, the version coordinate is the
# body's last-edit time, and the exact gh invocation is pinned.
mkdir -p "$RIG/bin"
# gh_json <body-file> <out> <lastEditedAt|null> [<editedAt>=<body-file> ...]
gh_json() {
  python3 - "$@" <<'PYX'
import json, sys
body = open(sys.argv[1], encoding="utf-8").read()
last = None if sys.argv[3] == "null" else sys.argv[3]
edits = []
for spec in sys.argv[4:]:
    at, _, path = spec.partition("=")
    edits.append({"editedAt": at, "diff": open(path, encoding="utf-8").read()})
issue = {
    "number": 3755, "title": "[EPIC] Sample", "body": body, "state": "OPEN",
    "url": "https://example.invalid/acme/tracker/issues/3755",
    "createdAt": "2026-09-07T06:41:48Z", "lastEditedAt": last,
    "labels": {"nodes": [{"name": "ux"}, {"name": "type: feature"}]},
    "milestone": {"title": "Sample v1.0"},
    "userContentEdits": {"totalCount": len(edits), "nodes": edits},
}
json.dump({"data": {"repository": {"issue": issue}}}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PYX
}
gh_json "$RIG/epic.md" "$RIG/gh.json" "2026-09-08T05:25:01Z" "2026-09-07T06:41:48Z=$RIG/old.md" "2026-09-08T05:25:01Z=$RIG/epic.md"
cat >"$RIG/bin/gh" <<SH2
#!/usr/bin/env bash
printf '%s\n' "\$@" >"$RIG/gh-args.txt"
cat "$RIG/gh.json"
SH2
chmod +x "$RIG/bin/gh"
fetch_stub() {  # fetch_stub <subcommand args...>
  OUT=$(PATH="$RIG/bin:$PATH" python3 "$SUT" "$@" 2>"$RIG/stderr.txt") && RC=0 || RC=$?
  ERR=$(cat "$RIG/stderr.txt")
  printf '%s' "$OUT" >"$RIG/out.json"
}
fetch_stub fetch --repo acme/tracker --id 3755 --binding "$B_ACC" --binding "$B_QA"
if [ "$RC" -eq 0 ] \
  && [ "$(q '(d["source"]["tracker"], d["source"]["repo"], d["source"]["id"], d["source"]["labels"], d["source"]["milestone"], d["source"]["version"])')" = "('github', 'acme/tracker', '3755', ['ux', 'type: feature'], 'Sample v1.0', '2026-09-08T05:25:01Z')" ] \
  && [ "$(q 'bool(__import__("re").fullmatch(r"\d{4}-\d{2}-\d{2}", d["source"]["read_at"])) and d["source"]["fetched_at"].startswith(d["source"]["read_at"])')" = "True" ] \
  && [ "$(q '[b["item_count"] for b in d["bindings"]]')" = "[8, 3]" ] \
  && [ "$(sed -n '1,3p' "$RIG/gh-args.txt" | tr '\n' ' ')" = "api graphql -f " ] \
  && grep -qF 'owner=acme' "$RIG/gh-args.txt" && grep -qF 'name=tracker' "$RIG/gh-args.txt" && grep -qF 'number=3755' "$RIG/gh-args.txt"; then
  pass "C12 fetch (GitHub adapter): source + version from lastEditedAt, gh api graphql pinned"
else
  fail "C12 fetch" "rc=$RC args=$(tr '\n' ' ' <"$RIG/gh-args.txt" 2>/dev/null | cut -c1-120) source=$(q 'd["source"]') stderr=$ERR"
fi

# C13 — fetch when gh fails: exit 2, gh's stderr relayed, no traceback.
cat >"$RIG/bin/gh" <<'SH2'
#!/usr/bin/env bash
echo "GraphQL: Could not resolve to an Issue (404)" >&2
exit 1
SH2
fetch_stub fetch --repo acme/tracker --id 999999 --binding "$B_ACC"
if [ "$RC" -eq 2 ] && grep -qF 'exited 1 while trying to fetch acme/tracker#999999' <<<"$ERR" && grep -qF 'Could not resolve' <<<"$ERR" && ! grep -qF 'Traceback' <<<"$ERR"; then
  pass "C13 fetch failure → exit 2, gh stderr relayed, no traceback"
else
  fail "C13 fetch failure" "rc=$RC stderr=$ERR"
fi

# C14 — canonical `text`: NFD (decomposed Hangul, as some editors emit) and
# ragged whitespace normalise to the same string a clean NFC body yields —
# otherwise a version read on one machine drifts against the same ticket read
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

# C16 — a custom adapter: `--fetch-command` is shlex-split, `{repo}`/`{id}`
# swapped per argv element, run without a shell; its JSON becomes `source`.
mkdir -p "$RIG/tickets"
python3 - "$RIG/epic.md" "$RIG/tickets/T-42.json" <<'PYX'
import json, sys
json.dump({"id": "T-42", "title": "Jira-ish", "url": "https://example.invalid/T-42",
           "body": open(sys.argv[1], encoding="utf-8").read(), "version": "rev-7",
           "labels": ["ux"], "milestone": None, "state": "Open"},
          open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PYX
run fetch --id T-42 --tracker jira --fetch-command "cat $RIG/tickets/{id}.json" --binding "$B_ACC"
if [ "$RC" -eq 0 ] && [ "$(q '(d["source"]["tracker"], d["source"]["repo"], d["source"]["id"], d["source"]["version"], d["bindings"][0]["item_count"])')" = "('jira', None, 'T-42', 'rev-7', 8)" ]; then
  pass "C16 custom --fetch-command adapter (no gh, no shell) feeds source + body"
else
  fail "C16 custom adapter" "rc=$RC stderr=$ERR $(q 'd["source"]')"
fi

# C17 — adapter contract is enforced: no `version` → exit 2 naming the gap; an
# id carrying shell syntax is refused before any command runs.
printf '{"id":"T-1","body":"### x\\n- [ ] a"}' >"$RIG/tickets/T-1.json"
run fetch --id T-1 --fetch-command "cat $RIG/tickets/{id}.json" --binding "$B_ACC"
U6=$RC; E6=$ERR
run fetch --id 'T-1;rm' --fetch-command "cat $RIG/tickets/{id}.json" --binding "$B_ACC"
U7=$RC; E7=$ERR
if [ "$U6" -eq 2 ] && grep -qF '`version` (non-empty string) missing' <<<"$E6" \
  && [ "$U7" -eq 2 ] && grep -qF -- '--id may contain only' <<<"$E7" && ! grep -qF 'Traceback' <<<"$E6$E7"; then
  pass "C17 adapter output without version → exit 2; unsafe --id refused → exit 2"
else
  fail "C17 adapter contract" "rc=$U6/$U7 stderr=$E6 | $E7"
fi

# C18 — drift, same version: no drift, every item counted unchanged, exit 0.
cp "$RIG/epic.md" "$RIG/epic-v1.md"
gh_json "$RIG/epic.md" "$RIG/gh.json" "2026-09-08T05:25:01Z" "2026-09-07T06:41:48Z=$RIG/epic-v1.md" "2026-09-08T05:25:01Z=$RIG/epic.md"
cat >"$RIG/bin/gh" <<SH2
#!/usr/bin/env bash
cat "$RIG/gh.json"
SH2
fetch_stub drift --repo acme/tracker --id 3755 --version "2026-09-08T05:25:01Z" --binding "$B_ACC" --binding "$B_QA"
if [ "$RC" -eq 0 ] && [ "$(q '(d["drift"], d["binding_changed"], d["history_available"], [(b["id"], b["unchanged"], len(b["added"]), len(b["removed"])) for b in d["bindings"]])')" = "(False, False, True, [('acceptance', 8, 0, 0), ('qa_checklist', 3, 0, 0)])" ]; then
  pass "C18 drift, same version → exit 0, nothing changed"
else
  fail "C18 drift same version" "rc=$RC $(q 'd')"
fi

# C19 — drift with history: one acceptance item reworded → removed 1 / added 1,
# QA untouched, binding_changed true, exit 1. The recorded body is looked up in
# the edit log by version, so the diff is item-level, not "something moved".
sed 's/1,000원 이상 주문에서 잔당 스탬프 1개가 적립된다/0원 초과 주문에서 잔당 스탬프 1개가 적립된다/' "$RIG/epic.md" >"$RIG/epic-v2.md"
gh_json "$RIG/epic-v2.md" "$RIG/gh.json" "2026-09-09T01:00:00Z" "2026-09-07T06:41:48Z=$RIG/epic-v1.md" "2026-09-08T05:25:01Z=$RIG/epic.md" "2026-09-09T01:00:00Z=$RIG/epic-v2.md"
fetch_stub drift --repo acme/tracker --id 3755 --version "2026-09-08T05:25:01Z" --binding "$B_ACC" --binding "$B_QA"
if [ "$RC" -eq 1 ] && [ "$(q '(d["drift"], d["history_available"], d["binding_changed"], d["recorded_version"], d["current_version"])')" = "(True, True, True, '2026-09-08T05:25:01Z', '2026-09-09T01:00:00Z')" ] \
  && [ "$(q '[(b["id"], b["unchanged"], [a["text"] for a in b["added"]], [r["ordinal"] for r in b["removed"]]) for b in d["bindings"]]')" = "[('acceptance', 6, ['0원 초과 주문에서 잔당 스탬프 1개가 적립된다', '0원 초과 주문에서 잔당 스탬프 1개가 적립된다'], [1, 8]), ('qa_checklist', 3, [], [])]" ]; then
  pass "C19 drift with history → item-level added/removed (multiset), exit 1"
else
  fail "C19 drift with history" "rc=$RC $(q '[(b["id"], b["unchanged"], b["added"], b["removed"]) for b in d["bindings"]]') stderr=$ERR"
fi

# C20 — drift where only NON-binding text changed (비고 edited): versions differ,
# but history proves no binding item moved → binding_changed false, exit 0.
sed 's/서버는 0원/서버는 0원 (확인 중)/' "$RIG/epic.md" >"$RIG/epic-v3.md"
gh_json "$RIG/epic-v3.md" "$RIG/gh.json" "2026-09-09T02:00:00Z" "2026-09-08T05:25:01Z=$RIG/epic.md" "2026-09-09T02:00:00Z=$RIG/epic-v3.md"
fetch_stub drift --repo acme/tracker --id 3755 --version "2026-09-08T05:25:01Z" --binding "$B_ACC" --binding "$B_QA"
if [ "$RC" -eq 0 ] && [ "$(q '(d["drift"], d["binding_changed"], d["history_available"], [b["unchanged"] for b in d["bindings"]])')" = "(True, False, True, [8, 3])" ]; then
  pass "C20 drift outside the binding sections → drift true, binding_changed false, exit 0"
else
  fail "C20 non-binding drift" "rc=$RC $(q '(d["drift"], d["binding_changed"], d["history_available"])')"
fi

# C21 — drift with no history for the recorded version: cannot prove anything,
# so it is reported as changed (exit 1) with a warning, unchanged = null.
gh_json "$RIG/epic-v3.md" "$RIG/gh.json" "2026-09-09T02:00:00Z" "2026-09-09T02:00:00Z=$RIG/epic-v3.md"
fetch_stub drift --repo acme/tracker --id 3755 --version "2026-01-01T00:00:00Z" --binding "$B_ACC"
if [ "$RC" -eq 1 ] && [ "$(q '(d["drift"], d["history_available"], d["binding_changed"], d["bindings"][0]["unchanged"])')" = "(True, False, True, None)" ] \
  && [ "$(q 'any("no body is available for recorded version" in w for w in d["warnings"])')" = "True" ]; then
  pass "C21 drift without history for the recorded version → exit 1, unproven, warned"
else
  fail "C21 drift without history" "rc=$RC $(q 'd["warnings"]')"
fi

# ---- coverage: the ledger each pitch keeps vs. the ticket's items ----------
# Fixture ticket (epic.md): acceptance = 적립 (3 items) + 발급 (5 items);
# QA = 표시 (2) + 시점 (1). Total 11.
gh_json "$RIG/epic.md" "$RIG/gh.json" "2026-09-08T05:25:01Z" "2026-09-08T05:25:01Z=$RIG/epic.md"
cat >"$RIG/bin/gh" <<SH2
#!/usr/bin/env bash
cat "$RIG/gh.json"
SH2
mkdir -p "$RIG/pitches"
mkledger() {  # mkledger <file> <yaml-lines...>  — a pitch whose frontmatter cites 3755 with the given ledger lines
  local f="$RIG/pitches/$1"; shift
  { echo '---'; echo 'domain: reward'; echo 'supersedes: null'; echo 'deprecated: false'; echo 'references:'; echo '  tickets:'
    echo '    - tracker: github'; echo '      repo: acme/tracker'; echo '      id: 3755'; echo '      version: "2026-09-08T05:25:01Z"'
    printf '%s\n' "$@"; echo '---'; echo; echo '# body'; } >"$f"
}
mkledger p1.md '      covers:' '        acceptance:' '          - group: 적립' '          - group: 발급' '            items: [1, 2, 3, 4]' '        qa_checklist:' '          - group: 시점' '            shared: true' \
               '      delegates:' '        - binding: acceptance' '          group: 발급' '          items: [5]' '          to: Figma' '          why: 문구는 시안이 정한다'
mkledger p2.md '      covers:' '        qa_checklist:' '          - group: 표시' '          - group: 시점' '            shared: true'
cov() { fetch_stub coverage --repo acme/tracker --id 3755 --binding "$B_ACC" --binding "$B_QA" "$@"; }

# C22 — full coverage across two pitches: every item claimed once (one shared
# by agreement), a delegate counts as claimed, exit 0.
cov "$RIG/pitches/p1.md" "$RIG/pitches/p2.md"
if [ "$RC" -eq 0 ] && [ "$(q '(d["total"], d["covered"], len(d["uncovered"]), len(d["overlaps"]), len(d["stale"]), [(s["group"], sorted(s["claimed_by"])) for s in d["shared"]], [(p["covers"], p["delegates"]) for p in d["pitches"]])')" = "(11, 11, 0, 0, 0, [('시점', ['$RIG/pitches/p1.md', '$RIG/pitches/p2.md'])], [(8, 1), (3, 0)])" ]; then
  pass "C22 coverage: full set → exit 0; delegate counts; shared-by-agreement is not an overlap"
else
  fail "C22 coverage full" "rc=$RC $(q '(d["total"], d["covered"], d["uncovered"], d["overlaps"], d["stale"], d["shared"], d["pitches"])')"
fi

# C23 — defects: an unshared double claim is an overlap, a group the ticket
# lacks is stale, items nobody claims are uncovered; exit 1.
mkledger p3.md '      covers:' '        acceptance:' '          - group: 적립'
mkledger p4.md '      covers:' '        acceptance:' '          - group: 없는묶음' '          - group: 발급' '            items: [9]'
cov "$RIG/pitches/p1.md" "$RIG/pitches/p3.md" "$RIG/pitches/p4.md"
if [ "$RC" -eq 1 ] && [ "$(q '(d["covered"], [u["group"] for u in d["uncovered"]], len(d["overlaps"]), sorted(set(o["group"] for o in d["overlaps"])), len(d["stale"]))')" = "(9, ['표시', '표시'], 3, ['적립'], 2)" ] \
  && [ "$(q 'any("없는묶음" in s for s in d["stale"]) and any("item 9 not in" in s for s in d["stale"])')" = "True" ]; then
  pass "C23 coverage: overlap (3 items), stale group + stale item, uncovered 표시 ×2 → exit 1"
else
  fail "C23 coverage defects" "rc=$RC $(q '(d["covered"], d["uncovered"], d["overlaps"], d["stale"])')"
fi

# C24 — set membership and versions: a pitch citing another ticket is not in the
# set; a pitch with an older recorded version is reported (warning, not failure);
# a file without frontmatter is skipped with a warning.
mkledger p5.md '      covers: {}'; sed -i '' 's/id: 3755/id: 9999/' "$RIG/pitches/p5.md"
mkledger p6.md '      covers: {}'; sed -i '' 's/2026-09-08T05:25:01Z/2026-01-01T00:00:00Z/' "$RIG/pitches/p6.md"
printf '# no frontmatter\n' >"$RIG/pitches/p7.md"
cov "$RIG/pitches/p1.md" "$RIG/pitches/p2.md" "$RIG/pitches/p5.md" "$RIG/pitches/p6.md" "$RIG/pitches/p7.md"
if [ "$RC" -eq 0 ] && [ "$(q '(len(d["pitches"]), [m["pitch"].rsplit("/",1)[1] for m in d["version_mismatch"]], any("no readable frontmatter" in w for w in d["warnings"]), any("recorded a version other than the live one" in w for w in d["warnings"]))')" = "(3, ['p6.md'], True, True)" ]; then
  pass "C24 coverage: other-ticket pitch excluded, version mismatch warned, frontmatter-less file skipped"
else
  fail "C24 coverage membership" "rc=$RC $(q '(len(d["pitches"]), d["version_mismatch"], d["warnings"])')"
fi

# C25 — one item coordinate: `in_group` restarts at 1 in every group while
# `ordinal` runs on across the section, and a coverage row names the item by
# the same `in_group` the ledger's `items` uses. The second seven-pitch run's
# correction request cited a five-item group's item as "11" — the section-wide
# number, which a reader of the ticket cannot resolve.
run parse "$RIG/epic.md" --binding "$B_ACC" --binding "$B_QA"
GOT="$(q '[(it["group"], it["ordinal"], it["in_group"]) for b in d["bindings"] for g in b["groups"] for it in g["items"] if it["in_group"] == 1 or it["ordinal"] == 3]')"
WANT="[('적립', 1, 1), ('적립', 3, 3), ('발급', 4, 1), ('표시', 1, 1), ('시점', 3, 1)]"
RC_PARSE=$RC
mkledger p8.md '      covers:' '        acceptance:' '          - group: 발급' '            items: [2]'
cov "$RIG/pitches/p8.md"
GOT2="$(q '([(u["group"], u["in_group"], u["ordinal"]) for u in d["uncovered"] if u["group"] == "발급"], "item" in d["uncovered"][0])')"
if [ "$RC_PARSE" -eq 0 ] && [ "$GOT" = "$WANT" ] && [ "$GOT2" = "([('발급', 1, 4), ('발급', 3, 6), ('발급', 4, 7), ('발급', 5, 8)], False)" ]; then
  pass "C25 one item coordinate: in_group restarts per group; coverage rows carry it, not a separate 'item'"
else
  fail "C25 item coordinate" "parse: $GOT
coverage: $GOT2"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all 25 cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
