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
# Needs:  python3, plus PyYAML for the cases that read pitch frontmatter or a
#         profile (`coverage`, and `drift` with pitch files). No git, no
#         network (`fetch` and `drift` are exercised through a stub `gh`
#         placed first on PATH, and through a custom --fetch-command adapter).

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
PASSES=0
pass() { printf 'PASS  %s\n' "$1"; PASSES=$((PASSES + 1)); }
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

# --- Gap B: section requiredness is data, read by both halves (v0.12) -------
# A binding section a team declares OPTIONAL and the ticket does not supply is
# a warning, not an error. Measured 2026-09-17 in the pilot's tracker: of 5
# sampled Epics, 2 carry the first binding section but not the second, so any
# reconciliation touching them exited 1 regardless of the pitches under review.
# Refusing is right at authoring time (the author fills the ticket) and wrong
# in CI (the build turns red through no fault of the pitch).

# C26 — optional section absent: exit 0, a warning, found/item_count intact,
# and an `absent[]` row. The same body with the section REQUIRED still errors
# (C7's contract), so optionality is the only difference.
run parse "$RIG/old.md" --binding "$B_ACC" --binding "$B_QA" --optional-binding acceptance
if [ "$RC" -eq 0 ] \
  && [ "$(q '[(b["id"], b["required"], b["found"], b["item_count"]) for b in d["bindings"]]')" = "[('acceptance', False, False, 0), ('qa_checklist', True, True, 1)]" ] \
  && [ "$(q 'd["errors"]')" = "[]" ] \
  && [ "$(q '[(a["id"], a["required"], a["why"]) for a in d["absent"]]')" = "[('acceptance', False, 'section not found')]" ] \
  && [ "$(q 'any("optional binding section absent: acceptance" in w for w in d["warnings"])')" = "True" ]; then
  pass "C26 optional section absent → exit 0, warning + absent[] row, no error"
else
  fail "C26 optional absent" "rc=$RC errors=$(q 'd["errors"]') absent=$(q 'd["absent"]') warnings=$(q 'd["warnings"]')"
fi

# C27 — optional section present but never filled in (heading + guidance
# comment only): same treatment, and `why` says which of the two it was.
run parse "$RIG/empty.md" --binding "$B_ACC" --binding "$B_QA" --optional-binding acceptance
if [ "$RC" -eq 0 ] && [ "$(q 'd["errors"]')" = "[]" ] \
  && [ "$(q '[(a["id"], a["why"]) for a in d["absent"]]')" = "[('acceptance', 'section has no list items')]" ] \
  && [ "$(q 'any("optional binding section has no list items" in w for w in d["warnings"])')" = "True" ]; then
  pass "C27 optional section present-but-empty → exit 0, absent[] says which"
else
  fail "C27 optional empty" "rc=$RC errors=$(q 'd["errors"]') absent=$(q 'd["absent"]')"
fi

# C28 — `--optional-binding` names an id, never a heading: an unknown id and a
# repeated one are usage errors (exit 2), because a typo that silently made a
# required section optional is the fail-open shape this whole change removes.
run parse "$RIG/epic.md" --binding "$B_ACC" --optional-binding qa_checklist
U1=$RC; E1=$ERR
run parse "$RIG/epic.md" --binding "$B_ACC" --optional-binding acceptance --optional-binding acceptance
U2=$RC
if [ "$U1$U2" = "22" ] && grep -qF -- "--optional-binding names 'qa_checklist'" <<<"$E1" && ! grep -qF 'Traceback' <<<"$E1"; then
  pass "C28 --optional-binding usage errors exit 2 (undeclared id, repeated id)"
else
  fail "C28 optional-binding usage" "rc=$U1$U2 stderr=$E1"
fi

# C29 — the reconciling half reads the same field. A ticket that never got its
# QA section: coverage exits 0 when the section is declared optional and 1 when
# it is not, reports the absence in `absent[]` and in a warning either way, and
# a pitch that DOES claim the absent section is stale with a message naming the
# absence rather than "that binding does not exist".
printf '%s\n' '### 완료 조건' '' '**적립**' '' '- [ ] 잔당 스탬프 1개가 적립된다' '- [ ] 2잔 이상은 잔 수만큼 적립된다' >"$RIG/acc-only.md"
gh_json "$RIG/acc-only.md" "$RIG/gh-noqa.json" "2026-09-08T05:25:01Z" "2026-09-08T05:25:01Z=$RIG/acc-only.md"
cat >"$RIG/bin/gh" <<SH2
#!/usr/bin/env bash
cat "$RIG/gh-noqa.json"
SH2
mkledger p9.md '      covers:' '        acceptance:' '          - group: 적립'
fetch_stub coverage --repo acme/tracker --id 3755 --binding "$B_ACC" --binding "$B_QA" --optional-binding qa_checklist "$RIG/pitches/p9.md"
OPT_RC=$RC
OPT_STATE="$(q '(d["total"], d["covered"], [(a["id"], a["required"], a["why"]) for a in d["absent"]], len(d["stale"]), any("reconciled without optional binding qa_checklist" in w for w in d["warnings"]))')"
fetch_stub coverage --repo acme/tracker --id 3755 --binding "$B_ACC" --binding "$B_QA" "$RIG/pitches/p9.md"
REQ_RC=$RC
REQ_ERRORS="$(q 'd["errors"]')"
fetch_stub coverage --repo acme/tracker --id 3755 --binding "$B_ACC" --binding "$B_QA" --optional-binding qa_checklist "$RIG/pitches/p9.md" "$RIG/pitches/p2.md"
CLAIM_RC=$RC
if [ "$OPT_RC" -eq 0 ] && [ "$OPT_STATE" = "(2, 2, [('qa_checklist', False, 'section not found')], 0, True)" ] \
  && [ "$REQ_RC" -eq 1 ] && grep -qF 'binding section not found: qa_checklist' <<<"$REQ_ERRORS" \
  && [ "$CLAIM_RC" -eq 1 ] && [ "$(q 'sum("supplies no items for it" in s for s in d["stale"])')" = "2" ]; then
  pass "C29 coverage: optional absent section → exit 0 + absent[]; required → exit 1; a claim on it is stale and says why"
else
  fail "C29 coverage optionality" "optional rc=$OPT_RC state=$OPT_STATE
required rc=$REQ_RC errors=$REQ_ERRORS
claim rc=$CLAIM_RC stale=$(q 'd["stale"]')"
fi

# C30 — drift reports the absence too. A ticket whose optional section is gone
# still drift-checks the one it has; silence about the missing half is how the
# check would go quietly fail-open.
fetch_stub drift --repo acme/tracker --id 3755 --version "2026-09-08T05:25:01Z" \
  --binding "$B_ACC" --binding "$B_QA" --optional-binding qa_checklist
if [ "$RC" -eq 0 ] \
  && [ "$(q '(d["drift"], d["binding_changed"], [(a["id"], a["required"]) for a in d["absent"]], [(b["id"], b["required"], b["unchanged"]) for b in d["bindings"]])')" = "(False, False, [('qa_checklist', False)], [('acceptance', True, 2), ('qa_checklist', False, 0)])" ]; then
  pass "C30 drift: absent[] carried, required flag on every binding row, exit 0"
else
  fail "C30 drift absent" "rc=$RC $(q '(d["drift"], d["absent"], d["bindings"])')"
fi

# ---- drift per pitch (v0.19): a change fails only the pitch that owns it ----
# The incident: a designer swapped one quoted UI string in two items of an Epic
# four active pitches cite. The one pitch owning those items had delegated them
# to Figma; the other three own neither. The single-version form failed the
# ticket for all four, and clearing it meant superseding all four. With pitch
# files, drift judges each pitch against its own recorded version on the items
# it covers or delegates, and a `meaning_unchanged` ledger entry lets an owned
# edit stand without a new version. Fixture shape only; the text is synthetic.
PROFILE="$SCRIPT_DIR/../examples/_profiles/default-ko.yml"
DP="$RIG/dp"
mkdir -p "$DP/pitches"
V1="2026-09-16T05:33:03Z"; V2="2026-11-13T07:26:00Z"; V3="2026-11-14T01:00:00Z"
V4="2026-11-14T02:00:00Z"; V5="2026-11-15T01:00:00Z"; V6="2026-11-15T02:00:00Z"
cat >"$DP/v1.md" <<'MD'
### 완료 조건

**가입**

- [ ] 휴대폰 번호로 인증번호를 받는다
- [ ] 인증번호 6자리를 입력하면 가입이 완료된다

**오류·재발급**

- [ ] 인증번호가 틀리면 "올바르게 다시 입력해주세요"가 안내되고 입력 화면이 유지된다
- [ ] 재발급은 30초 뒤에 할 수 있다

**결제 잠금**

- [ ] 결제 전 본인 확인을 한 번 더 한다

**내 정보**

- [ ] 이름과 생년월일을 고칠 수 있다

**첫 진입**

- [ ] 첫 진입 시 안내 화면이 한 번 보인다

### QA 통과 리스트

**인증 오류·재발급**

- [ ] 틀린 인증번호를 넣는다 → "올바르게 다시 입력해주세요"가 보이고 입력 화면이 유지된다
- [ ] 30초 전에 재발급을 누른다 → 버튼이 비활성이다

**첫 진입**

- [ ] 처음 연다 → 안내 화면이 보인다
MD
# dp_body <out> <base> <old>=<new>...  — a version of the body with whole substrings replaced
dp_body() {
  python3 - "$@" <<'PYX'
import sys
out, base = sys.argv[1], open(sys.argv[2], encoding="utf-8").read()
for spec in sys.argv[3:]:
    old, _, new = spec.partition("=>")
    assert old in base, old
    base = base.replace(old, new)
open(out, "w", encoding="utf-8").write(base)
PYX
}
# dp_ticket <current version> <version>=<body file>...  — the adapter's JSON, history included
dp_ticket() {
  python3 - "$DP/ticket.json" "$@" <<'PYX'
import json, sys
out, current = sys.argv[1], sys.argv[2]
hist = [{"version": v, "body": open(p, encoding="utf-8").read()} for v, _, p in (s.partition("=") for s in sys.argv[3:])]
json.dump({"id": "4127", "title": "t", "url": "https://example.invalid/4127", "version": current,
           "body": next(h["body"] for h in hist if h["version"] == current), "history": hist},
          open(out, "w", encoding="utf-8"), ensure_ascii=False)
PYX
}
dp_pitch() {  # dp_pitch <file> <recorded version> <deprecated> <ticket-record ledger lines...>
  local f="$DP/pitches/$1" v="$2" dep="$3"; shift 3
  { echo '---'; echo 'domain: auth'; echo 'supersedes: null'; echo "deprecated: $dep"; echo 'references:'; echo '  tickets:'
    echo '    - tracker: github'; echo '      repo: acme/tracker'; echo '      id: "4127"'; echo "      version: \"$v\""
    printf '%s\n' "$@"; echo '---'; echo; echo '# body'; } >"$f"
}
dp_ledger() {  # dp_ledger <file> <entry lines...>
  local f="$DP/$1"; shift
  { echo 'schema: 1'; echo 'acknowledgements:'; printf '%s\n' "$@"; } >"$f"
}
# dp <drift args...> — run from $DP so a ledger's relative `pitch` resolves as in a repo root
dp() {
  OUT=$(cd "$DP" && python3 "$SUT" drift --repo acme/tracker --id 4127 --fetch-command "cat $DP/ticket.json" \
    --binding "$B_ACC" --binding "$B_QA" "$@" 2>"$RIG/stderr.txt") && RC=0 || RC=$?
  ERR=$(cat "$RIG/stderr.txt")
  printf '%s' "$OUT" >"$RIG/out.json"
}
ROWS='[(p["path"].split("/")[-1], p["verdict"], len(p["failing"]), len(p["acknowledged"]), len(p["literal_only"]), p["unowned"]) for p in d["pitches"]]'
CH='[(c["binding"], c["group"], c["in_group"], c["claim"], c["change"], c["literal_only"]) for p in d["pitches"] for c in p[KEY]]'
chq() { q "${CH/KEY/\"$1\"}"; }
dp_pitch signup.md "$V1" false '      covers:' '        acceptance:' '          - group: 가입' '          - group: 오류·재발급' '            items: [2]' \
  '        qa_checklist:' '          - group: 인증 오류·재발급' '            items: [2]' \
  '      delegates:' '        - binding: acceptance' '          group: 오류·재발급' '          items: [1]' '          to: Figma' \
  '          why: 오류 안내 문구는 시안이 진실 소스 — 동작은 본 Pitch 가 정한다' \
  '        - binding: qa_checklist' '          group: 인증 오류·재발급' '          items: [1]' '          to: Figma'
dp_pitch lock.md "$V1" false '      covers:' '        acceptance:' '          - group: 결제 잠금'
dp_pitch myinfo.md "$V1" false '      covers:' '        acceptance:' '          - group: 내 정보'
dp_pitch onboarding.md "$V1" false '      covers:' '        acceptance:' '          - group: 첫 진입' '        qa_checklist:' '          - group: 첫 진입'
ALL4="pitches/signup.md pitches/lock.md pitches/myinfo.md pitches/onboarding.md"
COPY_EDIT=('"올바르게 다시 입력해주세요"=>"올바른 인증번호를 입력해주세요"')
dp_body "$DP/v2.md" "$DP/v1.md" "${COPY_EDIT[@]}"

# D1 — the incident's shape: a copy edit to two items one pitch delegated to
# Figma. Every citing pitch passes with zero pitch changes: the delegating one
# reports two literal-only changes, the other three own neither item (2
# unowned each), and all four are listed in version_mismatch as information.
dp_ticket "$V2" "$V1=$DP/v1.md" "$V2=$DP/v2.md"
# shellcheck disable=SC2086
dp --profile "$PROFILE" $ALL4
if [ "$RC" -eq 0 ] && [ "$(q 'd["verdict"]')" = "pass" ] \
  && [ "$(q "$ROWS")" = "[('signup.md', 'pass', 0, 0, 2, 0), ('lock.md', 'pass', 0, 0, 0, 2), ('myinfo.md', 'pass', 0, 0, 0, 2), ('onboarding.md', 'pass', 0, 0, 0, 2)]" ] \
  && [ "$(chq literal_only)" = "[('acceptance', '오류·재발급', 1, 'delegates', 'modified', True), ('qa_checklist', '인증 오류·재발급', 1, 'delegates', 'modified', True)]" ] \
  && [ "$(q '[(m["pitch"].split("/")[-1], m["owned_changes"]) for m in d["version_mismatch"]]')" = "[('signup.md', 2), ('lock.md', 0), ('myinfo.md', 0), ('onboarding.md', 0)]" ]; then
  pass "D1 #4127 shape: delegated literal-only edit → all four citing pitches pass, nothing superseded"
else
  fail "D1 delegated literal-only" "rc=$RC $(q "$ROWS") literal=$(chq literal_only) err=$ERR"
fi

# D2 — the same swap plus a behaviour change ("입력 화면이 유지된다" →
# "처음으로 돌아간다"): the substance moved, so the delegating pitch fails,
# and only it. Delegation hands over the literal, not the substance.
dp_body "$DP/v3.md" "$DP/v1.md" '"올바르게 다시 입력해주세요"가 안내되고 입력 화면이 유지된다=>"올바른 인증번호를 입력해주세요"가 안내되고 처음으로 돌아간다'
dp_ticket "$V3" "$V1=$DP/v1.md" "$V3=$DP/v3.md"
# shellcheck disable=SC2086
dp --profile "$PROFILE" $ALL4
D2_RC=$RC; D2_ROWS="$(q "$ROWS")"; D2_FAIL="$(chq failing)"; D2_NEW="$(q 'd["pitches"][0]["failing"][0]["new"]["text"].endswith("처음으로 돌아간다")')"
# … and the delegated item moved out of its group with the swap (to a group
# nobody claims) is a removal for the delegating pitch, not a copy edit: the
# literal-only pairing never crosses groups.
dp_body "$DP/v3b.md" "$DP/v1.md" \
  '- [ ] 인증번호가 틀리면 "올바르게 다시 입력해주세요"가 안내되고 입력 화면이 유지된다
=>' \
  '**결제 잠금**=>**기타**

- [ ] 인증번호가 틀리면 "올바른 인증번호를 입력해주세요"가 안내되고 입력 화면이 유지된다

**결제 잠금**'
dp_ticket "$V3" "$V1=$DP/v1.md" "$V3=$DP/v3b.md"
dp --profile "$PROFILE" pitches/signup.md
if [ "$D2_RC" -eq 1 ] \
  && [ "$D2_ROWS" = "[('signup.md', 'fail', 1, 0, 0, 0), ('lock.md', 'pass', 0, 0, 0, 1), ('myinfo.md', 'pass', 0, 0, 0, 1), ('onboarding.md', 'pass', 0, 0, 0, 1)]" ] \
  && [ "$D2_FAIL" = "[('acceptance', '오류·재발급', 1, 'delegates', 'modified', False)]" ] && [ "$D2_NEW" = "True" ] \
  && [ "$RC" -eq 1 ] && [ "$(chq failing)" = "[('acceptance', '오류·재발급', 1, 'delegates', 'removed', False)]" ]; then
  pass "D2 delegated substance change (or a move out of its group) → fails the delegating pitch only"
else
  fail "D2 delegated substance" "rc=$D2_RC rows=$D2_ROWS failing=$D2_FAIL | moved rc=$RC $(chq failing)"
fi

# D3 — a covered item reworded fails its owner only; and a pitch that COVERS
# (not delegates) the copy-edited item fails on the literal-only edit too:
# covering owns the literal as well as the substance.
dp_body "$DP/v4.md" "$DP/v1.md" '결제 전 본인 확인을 한 번 더 한다=>결제 전 본인 확인을 두 번 한다'
dp_ticket "$V4" "$V1=$DP/v1.md" "$V4=$DP/v4.md"
# shellcheck disable=SC2086
dp --profile "$PROFILE" $ALL4
D3_ROWS="$(q "$ROWS")"; D3_FAIL="$(chq failing)"; D3_RC=$RC
dp_pitch signup-covers.md "$V1" false '      covers:' '        acceptance:' '          - group: 오류·재발급'
dp_ticket "$V2" "$V1=$DP/v1.md" "$V2=$DP/v2.md"
dp --profile "$PROFILE" pitches/signup-covers.md
if [ "$D3_RC" -eq 1 ] \
  && [ "$D3_ROWS" = "[('signup.md', 'pass', 0, 0, 0, 1), ('lock.md', 'fail', 1, 0, 0, 0), ('myinfo.md', 'pass', 0, 0, 0, 1), ('onboarding.md', 'pass', 0, 0, 0, 1)]" ] \
  && [ "$D3_FAIL" = "[('acceptance', '결제 잠금', 1, 'covers', 'modified', False)]" ] \
  && [ "$RC" -eq 1 ] && [ "$(chq failing)" = "[('acceptance', '오류·재발급', 1, 'covers', 'modified', True)]" ]; then
  pass "D3 covered change → fails only its owner; a covered literal-only edit fails too"
else
  fail "D3 covered change" "rc=$D3_RC rows=$D3_ROWS failing=$D3_FAIL | covers-literal rc=$RC $(chq failing)"
fi

# D4 — ownership of an ADDED item follows the live ticket, as coverage reads
# it: an item added to a group a pitch claims whole is that pitch's, an item
# in a group nobody claims is `unowned` everywhere (coverage's uncovered[]),
# and a non-owner whose recorded version is stale passes and is reported.
dp_body "$DP/v5.md" "$DP/v1.md" \
  '- [ ] 인증번호 6자리를 입력하면 가입이 완료된다=>- [ ] 인증번호 6자리를 입력하면 가입이 완료된다
- [ ] 가입 직후 환영 알림이 온다' \
  '**결제 잠금**=>**알림**

- [ ] 마케팅 알림은 동의한 사람에게만 보낸다

**결제 잠금**'
dp_ticket "$V5" "$V1=$DP/v1.md" "$V5=$DP/v5.md"
# shellcheck disable=SC2086
dp --profile "$PROFILE" $ALL4
if [ "$RC" -eq 1 ] \
  && [ "$(q "$ROWS")" = "[('signup.md', 'fail', 1, 0, 0, 1), ('lock.md', 'pass', 0, 0, 0, 2), ('myinfo.md', 'pass', 0, 0, 0, 2), ('onboarding.md', 'pass', 0, 0, 0, 2)]" ] \
  && [ "$(chq failing)" = "[('acceptance', '가입', 3, 'covers', 'added', False)]" ] \
  && [ "$(q '[(m["pitch"].split("/")[-1], m["verdict"], m["owned_changes"]) for m in d["version_mismatch"]][-1]')" = "('onboarding.md', 'pass', 0)" ]; then
  pass "D4 added items: whole-group claim owns it, unclaimed group is unowned; stale non-owner passes and is reported"
else
  fail "D4 added items" "rc=$RC $(q "$ROWS") failing=$(chq failing) mismatch=$(q 'd["version_mismatch"]')"
fi

# D5 — an acknowledgement resolves the owned change: lock.md re-read the
# ticket at V4 and its reworded item kept its meaning. Exit 0, no new version.
# The entry's relative `pitch` matches an ABSOLUTE pitch argument too — the
# form `validate_docs.py --list-active --json` hands a consumer.
ACK_LOCK="  - {tracker: github, repo: acme/tracker, id: \"4127\", pitch: pitches/lock.md, binding: acceptance, group: 결제 잠금, in_group: 1, from_version: \"$V1\", to_version: \"$V4\", kind: meaning_unchanged, reason: 횟수 표현만 다듬었다 — 결제 전 추가 확인이라는 요구는 같다, decided_by: owner, date: 2026-11-16}"
dp_ledger ack.yml "$ACK_LOCK"
dp_ticket "$V4" "$V1=$DP/v1.md" "$V4=$DP/v4.md"
dp --profile "$PROFILE" --ledger ack.yml "$DP/pitches/lock.md" "$DP/pitches/signup.md"
ABS="$(q '(d["verdict"], [len(p["acknowledged"]) for p in d["pitches"]])')"
# shellcheck disable=SC2086
dp --profile "$PROFILE" --ledger ack.yml $ALL4
if [ "$RC" -eq 0 ] && [ "$(q 'd["verdict"]')" = "pass" ] && [ "$(q 'd["stale"]')" = "[]" ] \
  && [ "$ABS" = "('pass', [1, 0])" ] \
  && [ "$(q '[(c["group"], c["in_group"], c["by"]) for p in d["pitches"] for c in p["acknowledged"]]')" = "[('결제 잠금', 1, 'acknowledgements[1]')]" ] \
  && [ "$(q '(d["ledger"]["found"], d["ledger"]["entries"], d["ledger"]["problems"])')" = "(True, 1, [])" ]; then
  pass "D5 meaning_unchanged entry resolves the owned change → pass without superseding"
else
  fail "D5 acknowledgement" "rc=$RC $(q "$ROWS") stale=$(q 'd["stale"]') ledger=$(q 'd["ledger"]')"
fi

# D6 — the entry goes stale when the ticket moves past to_version AND touches
# that item (the change is unacknowledged again, and the entry is named stale);
# an edit elsewhere leaves it standing.
dp_body "$DP/v6.md" "$DP/v4.md" '결제 전 본인 확인을 두 번 한다=>결제 전 본인 확인을 세 번 한다'
dp_ticket "$V6" "$V1=$DP/v1.md" "$V4=$DP/v4.md" "$V6=$DP/v6.md"
# shellcheck disable=SC2086
dp --profile "$PROFILE" --ledger ack.yml $ALL4
D6_RC=$RC; D6_ROWS="$(q "$ROWS")"; D6_STALE="$(q '[(s["index"], s["pitch"], s["why"]) for s in d["stale"]]')"
dp_body "$DP/v6b.md" "$DP/v4.md" '이름과 생년월일을 고칠 수 있다=>이름과 생년월일과 이메일을 고칠 수 있다'
dp_ticket "$V6" "$V1=$DP/v1.md" "$V4=$DP/v4.md" "$V6=$DP/v6b.md"
# shellcheck disable=SC2086
dp --profile "$PROFILE" --ledger ack.yml $ALL4
if [ "$D6_RC" -eq 1 ] \
  && [ "$D6_ROWS" = "[('signup.md', 'pass', 0, 0, 0, 1), ('lock.md', 'fail', 1, 0, 0, 0), ('myinfo.md', 'pass', 0, 0, 0, 1), ('onboarding.md', 'pass', 0, 0, 0, 1)]" ] \
  && [ "$D6_STALE" = "[(1, 'pitches/lock.md', 'the ticket moved past to_version and changed that item')]" ] \
  && [ "$RC" -eq 1 ] && [ "$(q 'd["stale"]')" = "[]" ] \
  && [ "$(q "$ROWS")" = "[('signup.md', 'pass', 0, 0, 0, 2), ('lock.md', 'pass', 0, 1, 0, 1), ('myinfo.md', 'fail', 1, 0, 0, 1), ('onboarding.md', 'pass', 0, 0, 0, 2)]" ]; then
  pass "D6 acknowledgement stale after a further edit to the same item; an edit elsewhere leaves it standing"
else
  fail "D6 stale on re-edit" "same item: rc=$D6_RC rows=$D6_ROWS stale=$D6_STALE | elsewhere: rc=$RC $(q "$ROWS") stale=$(q 'd["stale"]')"
fi

# D7 — an acknowledgement for a superseded pitch is stale, whether the
# deprecated file is passed or left out (the consumer passes active pitches
# only); the successor, which recorded the live version, passes on its own.
dp_pitch lock.md "$V1" true '      covers:' '        acceptance:' '          - group: 결제 잠금'
dp_pitch lock2.md "$V4" false '      covers:' '        acceptance:' '          - group: 결제 잠금'
dp_ticket "$V4" "$V1=$DP/v1.md" "$V4=$DP/v4.md"
dp --profile "$PROFILE" --ledger ack.yml pitches/lock.md pitches/lock2.md pitches/signup.md
D7_RC=$RC; D7="$(q '([p["path"].split("/")[-1] for p in d["pitches"]], [(s["index"], s["why"].split(" (")[0]) for s in d["stale"]])')"
dp --profile "$PROFILE" --ledger ack.yml pitches/lock2.md pitches/signup.md
if [ "$D7_RC" -eq 1 ] && [ "$D7" = "(['lock2.md', 'signup.md'], [(1, 'the pitch is not an active pitch citing this ticket among the files given')])" ] \
  && [ "$RC" -eq 1 ] && [ "$(q 'len(d["stale"]), d["pitches"][0]["verdict"]')" = "(1, 'pass')" ]; then
  pass "D7 acknowledgement for a superseded pitch → stale (deprecated file passed or not)"
else
  fail "D7 superseded pitch" "rc=$D7_RC $D7 | active-only rc=$RC stale=$(q 'd["stale"]')"
fi
dp_pitch lock.md "$V1" false '      covers:' '        acceptance:' '          - group: 결제 잠금'

# D8 — the single-version form is untouched: no pitch files, `--version`
# given → the v0.18 output shape and verdict (the incident's copy edit still
# fails it, exit 1). Mixing the forms, or `--profile`/`--ledger` without
# pitch files, or neither form, is a usage error (exit 2) before any fetch.
dp_ticket "$V2" "$V1=$DP/v1.md" "$V2=$DP/v2.md"
dp --version "$V1"
L_RC=$RC; L_KEYS="$(q 'sorted(d)')"; L_STATE="$(q '(d["binding_changed"], [(b["id"], len(b["added"]), len(b["removed"])) for b in d["bindings"]])')"
dp --version "$V1" pitches/lock.md; U1=$RC; E1=$ERR
dp --version "$V1" --profile "$PROFILE"; U2=$RC; E2=$ERR
dp; U3=$RC; E3=$ERR
if [ "$L_RC" -eq 1 ] \
  && [ "$L_KEYS" = "['absent', 'binding_changed', 'bindings', 'current_version', 'drift', 'errors', 'history_available', 'recorded_version', 'schema', 'source', 'warnings']" ] \
  && [ "$L_STATE" = "(True, [('acceptance', 1, 1), ('qa_checklist', 1, 1)])" ] \
  && [ "$U1$U2$U3" = "222" ] && grep -qF -- '--version is the single-version form' <<<"$E1" \
  && grep -qF -- '--profile / --ledger go with pitch files' <<<"$E2" && grep -qF 'drift needs --version RECORDED' <<<"$E3" \
  && ! grep -qF Traceback <<<"$E1$E2$E3"; then
  pass "D8 legacy drift --version without pitches unchanged; mixed or empty forms → exit 2"
else
  fail "D8 legacy form" "rc=$L_RC keys=$L_KEYS state=$L_STATE usage=$U1$U2$U3 $E1 | $E2 | $E3"
fi

# D9 — fail closed: pitch files none of which cites the ticket judge nothing
# (exit 1, said in errors); a recorded version the edit log cannot produce is
# unproven (fail, history_available false); no --profile means no
# wording_strip, so the D1 copy edit fails its delegating pitch, with a warning.
dp_pitch other.md "$V1" false '      covers: {}'; sed -i '' 's/id: "4127"/id: "9999"/' "$DP/pitches/other.md"
dp_pitch ancient.md "2026-01-01T00:00:00Z" false '      covers:' '        acceptance:' '          - group: 가입'
dp --profile "$PROFILE" pitches/other.md; N_RC=$RC; N_ERR="$(q 'd["errors"]')"
dp --profile "$PROFILE" pitches/ancient.md; H_RC=$RC; H="$(q '[(p["verdict"], p["history_available"]) for p in d["pitches"]]')"
# shellcheck disable=SC2086
dp $ALL4
if [ "$N_RC" -eq 1 ] && grep -qF 'none of the 1 pitch file(s) given' <<<"$N_ERR" \
  && [ "$H_RC" -eq 1 ] && [ "$H" = "[('fail', False)]" ] \
  && [ "$RC" -eq 1 ] && [ "$(chq failing)" = "[('acceptance', '오류·재발급', 1, 'delegates', 'modified', False), ('qa_checklist', '인증 오류·재발급', 1, 'delegates', 'modified', False)]" ] \
  && [ "$(q 'any(w.startswith("no --profile") for w in d["warnings"])')" = "True" ]; then
  pass "D9 fail closed: nothing cited, unproven history, no --profile → exit 1, each named"
else
  fail "D9 fail closed" "none=$N_RC $N_ERR | history=$H_RC $H | no-profile rc=$RC $(chq failing)"
fi

# D10 — the new entry kind is read as strictly as the wording kind: an
# unquoted version (YAML makes it a date-time), a wording key (`rule`), an
# absolute pitch path and from = to (padding aside) are problems, and an entry with a problem
# acknowledges nothing — the valid ACK_LOCK beside them still resolves.
dp_ticket "$V4" "$V1=$DP/v1.md" "$V4=$DP/v4.md"
dp_ledger bad.yml "$ACK_LOCK" \
  "  - {tracker: github, id: \"4127\", pitch: pitches/myinfo.md, binding: acceptance, group: 내 정보, in_group: 1, from_version: \"$V1\", to_version: $V4, kind: meaning_unchanged, reason: x, decided_by: owner, date: 2026-11-16}" \
  "  - {tracker: github, id: \"4127\", pitch: pitches/myinfo.md, binding: acceptance, group: 내 정보, in_group: 1, rule: deferral, from_version: \"$V1\", to_version: \"$V4\", kind: meaning_unchanged, reason: x, decided_by: owner, date: 2026-11-16}" \
  "  - {tracker: github, id: \"4127\", pitch: $DP/pitches/myinfo.md, binding: acceptance, group: 내 정보, in_group: 1, from_version: \"$V1\", to_version: \"$V4\", kind: meaning_unchanged, reason: x, decided_by: owner, date: 2026-11-16}" \
  "  - {tracker: github, id: \"4127\", pitch: pitches/myinfo.md, binding: acceptance, group: 내 정보, in_group: 1, from_version: \"$V4\", to_version: \"$V4\", kind: meaning_unchanged, reason: x, decided_by: owner, date: 2026-11-16}" \
  "  - {tracker: github, id: \"4127\", pitch: pitches/myinfo.md, binding: acceptance, group: 내 정보, in_group: 1, from_version: \"$V4 \", to_version: \"$V4\", kind: meaning_unchanged, reason: x, decided_by: owner, date: 2026-11-16}"
# shellcheck disable=SC2086
dp --profile "$PROFILE" --ledger bad.yml $ALL4
P="$(q 'd["ledger"]["problems"]')"
if [ "$RC" -eq 0 ] && [ "$(q 'len(d["ledger"]["problems"]), d["ledger"]["entries"]')" = "(5, 1)" ] \
  && grep -qF 'acknowledgements[6]: `from_version` and `to_version` are the same version' <<<"$P" \
  && grep -qF 'acknowledgements[2]: `to_version` must be the version coordinate as a quoted string' <<<"$P" \
  && grep -qF "acknowledgements[3]: unknown key(s) ['rule'] for kind meaning_unchanged" <<<"$P" \
  && grep -qF 'acknowledgements[4]: `pitch` must be the pitch file' <<<"$P" \
  && grep -qF 'acknowledgements[5]: `from_version` and `to_version` are the same version' <<<"$P" \
  && [ "$(q 'd["pitches"][1]["acknowledged"][0]["by"]')" = "acknowledgements[1]" ]; then
  pass "D10 meaning_unchanged entries read strictly (unquoted version, wording key, absolute path, from = to)"
else
  fail "D10 ledger shape" "rc=$RC problems=$P"
fi

# D11–D15 pin what an independent review of the first draft reproduced as
# fail-open or crashing; each case failed on that draft.

# D11 — an acknowledgement names ONE item: a pitch covering two groups, an
# entry for 내 정보 1 at Va (where it read "T"), and a live ticket that put
# 내 정보 1 back and wrote "T" into 첫 진입 1 instead. The entry is stale (that
# item changed after to_version) and the 첫 진입 edit fails — matching on the
# text alone let the entry resolve the other group's change.
VA="2026-11-14T03:00:00Z"; VB="2026-11-14T04:00:00Z"
dp_body "$DP/va.md" "$DP/v1.md" '이름과 생년월일을 고칠 수 있다=>이름과 생년월일을 바로 고칠 수 있다'
dp_body "$DP/vb.md" "$DP/v1.md" '첫 진입 시 안내 화면이 한 번 보인다=>이름과 생년월일을 바로 고칠 수 있다'
dp_pitch two.md "$V1" false '      covers:' '        acceptance:' '          - group: 내 정보' '          - group: 첫 진입'
dp_ledger two.yml "  - {tracker: github, id: \"4127\", pitch: pitches/two.md, binding: acceptance, group: 내 정보, in_group: 1, from_version: \"$V1\", to_version: \"$VA\", kind: meaning_unchanged, reason: x, decided_by: owner, date: 2026-11-16}"
dp_ticket "$VB" "$V1=$DP/v1.md" "$VA=$DP/va.md" "$VB=$DP/vb.md"
dp --profile "$PROFILE" --ledger two.yml pitches/two.md
if [ "$RC" -eq 1 ] && [ "$(q '[(s["index"], s["why"]) for s in d["stale"]]')" = "[(1, 'the ticket moved past to_version and changed that item')]" ] \
  && [ "$(chq failing)" = "[('acceptance', '첫 진입', 1, 'covers', 'modified', False)]" ] && [ "$(chq acknowledged)" = "[]" ]; then
  pass "D11 an acknowledgement resolves only the item at its coordinate, never a look-alike elsewhere"
else
  fail "D11 ack coordinate" "rc=$RC stale=$(q 'd["stale"]') failing=$(chq failing) ack=$(chq acknowledged)"
fi

# D12 — ownership moves are changes: (a) an item moved verbatim into another
# pitch's group is removed for one and added for the other; (b) two items a
# group's numbered claims point at swap places — each claim now reaches the
# other pitch's requirement (`reassigned`, coverage cannot see it); (c) a
# sentence two groups both hold leaves one of them — the owner of THAT group
# fails, not the owner of the copy that stayed.
VC="2026-11-14T05:00:00Z"; VD="2026-11-14T06:00:00Z"
dp_body "$DP/vc.md" "$DP/v1.md" \
  '- [ ] 결제 전 본인 확인을 한 번 더 한다
=>' \
  '- [ ] 이름과 생년월일을 고칠 수 있다=>- [ ] 이름과 생년월일을 고칠 수 있다
- [ ] 결제 전 본인 확인을 한 번 더 한다'
dp_ticket "$VC" "$V1=$DP/v1.md" "$VC=$DP/vc.md"
dp --profile "$PROFILE" pitches/lock.md pitches/myinfo.md
D12A="$(q '[(p["path"].split("/")[-1], [(c["change"], c["group"], c["in_group"]) for c in p["failing"]]) for p in d["pitches"]]')"; D12A_RC=$RC
dp_pitch n1.md "$V1" false '      covers:' '        acceptance:' '          - group: 가입' '            items: [1]'
dp_pitch n2.md "$V1" false '      covers:' '        acceptance:' '          - group: 가입' '            items: [2]'
dp_body "$DP/vd.md" "$DP/v1.md" \
  '- [ ] 휴대폰 번호로 인증번호를 받는다
- [ ] 인증번호 6자리를 입력하면 가입이 완료된다=>- [ ] 인증번호 6자리를 입력하면 가입이 완료된다
- [ ] 휴대폰 번호로 인증번호를 받는다'
dp_ticket "$VD" "$V1=$DP/v1.md" "$VD=$DP/vd.md"
dp --profile "$PROFILE" pitches/n1.md pitches/n2.md
D12B="$(q '[(p["path"].split("/")[-1], sorted({c["change"] for c in p["failing"]}), len(p["failing"])) for p in d["pitches"]]')"; D12B_RC=$RC
dp_body "$DP/vdup1.md" "$DP/v1.md" \
  '- [ ] 이름과 생년월일을 고칠 수 있다=>- [ ] 이름과 생년월일을 고칠 수 있다
- [ ] 바꾼 내용은 바로 저장된다' \
  '- [ ] 첫 진입 시 안내 화면이 한 번 보인다=>- [ ] 첫 진입 시 안내 화면이 한 번 보인다
- [ ] 바꾼 내용은 바로 저장된다'
dp_body "$DP/vdup2.md" "$DP/vdup1.md" \
  '- [ ] 첫 진입 시 안내 화면이 한 번 보인다
- [ ] 바꾼 내용은 바로 저장된다=>- [ ] 첫 진입 시 안내 화면이 한 번 보인다'
dp_pitch dmy.md "$VC" false '      covers:' '        acceptance:' '          - group: 내 정보'
dp_pitch dfirst.md "$VC" false '      covers:' '        acceptance:' '          - group: 첫 진입'
dp_ticket "$VD" "$VC=$DP/vdup1.md" "$VD=$DP/vdup2.md"
dp --profile "$PROFILE" pitches/dmy.md pitches/dfirst.md
if [ "$D12A_RC" -eq 1 ] && [ "$D12A" = "[('lock.md', [('removed', '결제 잠금', 1)]), ('myinfo.md', [('added', '내 정보', 2)])]" ] \
  && [ "$D12B_RC" -eq 1 ] && [ "$D12B" = "[('n1.md', ['reassigned'], 2), ('n2.md', ['reassigned'], 2)]" ] \
  && [ "$RC" -eq 1 ] && [ "$(q "$ROWS")" = "[('dmy.md', 'pass', 0, 0, 0, 1), ('dfirst.md', 'fail', 1, 0, 0, 0)]" ] \
  && [ "$(chq failing)" = "[('acceptance', '첫 진입', 2, 'covers', 'removed', False)]" ]; then
  pass "D12 ownership moves fail the pitches they touch: cross-group move, reordered numbered claims, a duplicate leaving one group"
else
  fail "D12 ownership moves" "move rc=$D12A_RC $D12A | reorder rc=$D12B_RC $D12B | dup rc=$RC $(q "$ROWS") $(chq failing)"
fi

# D13 — the literal a delegation hands over is QUOTED copy. The bundled
# wording_strip also blanks a provenance parenthetical for the lint's sake, but
# a correction written into one — 「(2026-11-14 정정 — 세 번 틀리면 처음 화면으로
# 돌아간다)」 — changes the substance, so the delegating pitch fails.
dp_body "$DP/ve.md" "$DP/v1.md" '"가 안내되고 입력 화면이 유지된다=>"가 안내되고 입력 화면이 유지된다 (2026-11-14 정정 — 세 번 틀리면 처음 화면으로 돌아간다)'
dp_ticket "$VD" "$V1=$DP/v1.md" "$VD=$DP/ve.md"
dp --profile "$PROFILE" pitches/signup.md
if [ "$RC" -eq 1 ] && [ "$(chq failing)" = "[('acceptance', '오류·재발급', 1, 'delegates', 'modified', False)]" ] && [ "$(chq literal_only)" = "[]" ]; then
  pass "D13 a correction added in a stripped parenthetical is substance, not a literal-only edit"
else
  fail "D13 parenthetical" "rc=$RC failing=$(chq failing) literal=$(chq literal_only)"
fi

# D14 — only a modified item keeps a meaning to acknowledge: an entry naming
# an item ADDED to a group the pitch covers is stale and says why, and the
# addition still fails the pitch.
dp_ledger add.yml "  - {tracker: github, id: \"4127\", pitch: pitches/signup.md, binding: acceptance, group: 가입, in_group: 3, from_version: \"$V1\", to_version: \"$V5\", kind: meaning_unchanged, reason: x, decided_by: owner, date: 2026-11-16}"
dp_ticket "$V5" "$V1=$DP/v1.md" "$V5=$DP/v5.md"
dp --profile "$PROFILE" --ledger add.yml pitches/signup.md
if [ "$RC" -eq 1 ] && [ "$(q '[s["why"].split(" —")[0] for s in d["stale"]]')" = "['the change it names is \`added\`']" ] \
  && [ "$(chq failing)" = "[('acceptance', '가입', 3, 'covers', 'added', False)]" ]; then
  pass "D14 an acknowledgement for an added item is stale; the addition still fails"
else
  fail "D14 ack on added" "rc=$RC stale=$(q 'd["stale"]') failing=$(chq failing)"
fi

# D15 — a malformed ticket record (`delegates: 5`, `tickets: 5`) is the
# validator's to refuse; drift, coverage and gate read past it with no traceback.
# A crash must show as this case failing, not abort the run, hence the `||`.
dp_pitch bad-del.md "$V1" false '      delegates: 5'
{ echo '---'; echo 'domain: auth'; echo 'supersedes: null'; echo 'deprecated: false'; echo 'references:'; echo '  tickets: 5'; echo '---'; echo; echo '# x'; } >"$DP/pitches/bad-tickets.md"
dp_ticket "$V2" "$V1=$DP/v1.md" "$V2=$DP/v2.md"
dp --profile "$PROFILE" pitches/signup.md pitches/bad-del.md pitches/bad-tickets.md
DR_RC=$RC; DR_ERR=$ERR; DR="$(q "$ROWS" 2>/dev/null || echo unparsable)"
(cd "$DP" && python3 "$SUT" coverage --repo acme/tracker --id 4127 --fetch-command "cat $DP/ticket.json" --binding "$B_ACC" --binding "$B_QA" pitches/bad-del.md pitches/bad-tickets.md) >"$RIG/out.json" 2>"$RIG/stderr.txt" && CV_RC=0 || CV_RC=$?
CV_ERR=$(cat "$RIG/stderr.txt"); CV="$(q 'any("delegates must be a list" in s for s in d["stale"])' 2>/dev/null || echo unparsable)"
(cd "$DP" && python3 "$SUT" gate --mode on --profile "$PROFILE" --repo acme/tracker --fetch-command "cat $DP/ticket.json" --binding "$B_ACC" --binding "$B_QA" pitches/bad-tickets.md) >"$RIG/out.json" 2>"$RIG/stderr.txt" && GT_RC=0 || GT_RC=$?
GT_ERR=$(cat "$RIG/stderr.txt")
if [ "$DR_RC" -eq 0 ] && [ "$DR" = "[('signup.md', 'pass', 0, 0, 2, 0), ('bad-del.md', 'pass', 0, 0, 0, 2)]" ] \
  && [ "$CV_RC" -eq 1 ] && [ "$CV" = "True" ] && [ "$GT_RC" -eq 0 ] && [ "$(q 'd["tickets"]' 2>/dev/null || echo unparsable)" = "[]" ] \
  && ! grep -qF Traceback <<<"$DR_ERR$CV_ERR$GT_ERR"; then
  pass "D15 malformed ticket records: drift, coverage and gate read past them, no traceback"
else
  fail "D15 malformed records" "drift rc=$DR_RC $DR $DR_ERR | coverage rc=$CV_RC $CV $CV_ERR | gate rc=$GT_RC $GT_ERR"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
