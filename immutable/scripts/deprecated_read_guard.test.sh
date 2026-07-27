#!/usr/bin/env bash
# deprecated_read_guard.test.sh — regression test for `deprecated_read_guard.sh`,
# the plugin's PostToolUse(Read) withholding gate for deprecated SDD docs.
#
# WHY THIS FILE EXISTS
# The gate replaces a Read's tool_response so a `deprecated: true` doc's body never
# reaches the model. Two failure modes make an untested gate worse than none:
#
#   1. WRONG SHAPE — the emitted `updatedToolOutput` must be the Read tool_response
#      OBJECT ({type,file:{filePath,content,numLines,startLine,totalLines}}), never a
#      plain string. A plain string is a SILENT no-op: the hook fires, emits valid
#      JSON, exits 0, the harness drops it, and the model reads the real body — zero
#      error on any stream (measured 2026-07-16). Anyone "simplifying" the emission
#      back to a string must land here first.
#   2. WRONG PARSE — the pre-gate pickers used a line grep, which is wrong in BOTH
#      directions on real YAML: `deprecated: True` and `deprecated:  true` are live
#      YAML a grep for '^deprecated: true' reads as ACTIVE; a fenced example body
#      line starting `deprecated: true` reads as DEPRECATED. The gate parses with
#      PyYAML; these cases pin that it stays that way.
#
# Withholding is aggressive, so scope discipline gets its own section: out-of-tree
# files, non-.md, and frontmatter-less docs must sail through untouched.
#
# Usage:  bash immutable/scripts/deprecated_read_guard.test.sh          (hermetic unit)
#         bash immutable/scripts/deprecated_read_guard.test.sh --e2e    (headless claude -p
#                 proof via --plugin-dir; slow, networked, needs the claude CLI)
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  bash, jq, python3 + PyYAML — the set the guard itself assumes.
#
# The unit run proves the guard's own verdicts. Only the --e2e run proves the
# harness ACCEPTS the emission: fired-and-dropped and never-fired are otherwise
# indistinguishable from outside, which is exactly how the wrong-shape no-op hid.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="$SCRIPT_DIR/deprecated_read_guard.sh"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

[ -f "$GUARD" ] || { echo "cannot run: $GUARD not found" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "cannot run: guard needs jq" >&2; exit 2; }
# Without PyYAML the gate is INERT by design (fail-open with a warning). That state
# must fail this harness loudly, not pass as a column of green PASS rows.
python3 -c 'import yaml' 2>/dev/null \
  || { echo "cannot run: python3 cannot import yaml — the gate is inert on this machine" >&2; exit 2; }

# Unit runs stay deterministic even if the caller exports the knobs.
unset IMMUTABLE_DEPRECATED_GUARD_LOG IMMUTABLE_DEPRECATED_GUARD_DISABLE

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
# macOS TMPDIR carries a trailing slash, so mktemp yields `.../T//x`. The guard's
# python Path() collapses the double slash; normalize here or every path-equality
# assertion (W5) mismatches on pure string inequality.
ROOT="$(cd "$ROOT" && pwd)"

mkdoc() {  # mkdoc <path> <line>...
  local p="$1"; shift
  mkdir -p "$(dirname "$p")"
  printf '%s\n' "$@" > "$p"
}

SPEC="$ROOT/spec"
mkdir -p "$SPEC/.immutable-prd"
printf 'repo_mode: single-repo\n' > "$SPEC/.immutable-prd/config.yml"
D="$SPEC/pitches/order"

mkdoc "$D/a-dead.md"  '---' 'domain: order' 'supersedes: null' 'deprecated: true' '---' '' \
                      'The system MUST use the CANARY-DEAD-ALPHA handshake.'
mkdoc "$D/b-live.md"  '---' 'domain: order' 'supersedes: a-dead.md' 'deprecated: false' '---' '' \
                      'The system MUST use the CANARY-LIVE-BETA handshake.'
mkdoc "$D/cap.md"     '---' 'domain: order' 'supersedes: null' 'deprecated: True' '---' '' \
                      'CANARY-CAP body.'
mkdoc "$D/spaced.md"  '---' 'domain: order' 'supersedes: null' 'deprecated:  true' '---' '' \
                      'CANARY-SPACED body.'
mkdoc "$D/fenced.md"  '---' 'domain: order' 'supersedes: null' 'deprecated: false' '---' '' \
                      'A schema example follows:' '' '```yaml' 'deprecated: true' '```'
mkdoc "$D/nofm.md"    'Plain markdown, no frontmatter at all.'
mkdoc "$D/scalarfm.md" '---' 'just a scalar, not a mapping' '---' '' 'Body.'
mkdoc "$D/solo.md"    '---' 'domain: order' 'supersedes: null' 'deprecated: true' '---' '' \
                      'CANARY-SOLO body with no successor.'
mkdoc "$D/fan.md"     '---' 'domain: order' 'supersedes: null' 'deprecated: true' '---' '' \
                      'CANARY-FAN body, superseded by a refactor-split.'
mkdoc "$D/fan1.md"    '---' 'domain: order' 'supersedes: fan.md' 'deprecated: false' '---' '' \
                      'Split part one.'
mkdoc "$D/fan2.md"    '---' 'domain: order' 'supersedes: fan.md' 'deprecated: true' '---' '' \
                      'Split part two, itself already superseded.'
mkdoc "$D/notes.txt"  '---' 'deprecated: true' '---' '' 'Not markdown, must pass.'
mkdoc "$ROOT/outside/dead.md" '---' 'deprecated: true' '---' '' 'CANARY-OUTSIDE no .immutable-prd ancestor.'

run() {  # run <file_path> -> sets OUT, RC (guard reads all of stdin; no early-exit, no SIGPIPE)
  OUT=$(jq -nc --arg p "$1" '{tool_name:"Read",tool_input:{file_path:$p}}' | "$GUARD" 2>/dev/null) \
    && RC=0 || RC=$?
}

P=0; FAILURES=0
ok()  { printf 'PASS  %s\n' "$1"; P=$((P+1)); }
bad() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES+1)); }

expect_pass() {  # expect_pass <label> <file_path>
  run "$2"
  if [ "$RC" -eq 0 ] && [ -z "$OUT" ]; then ok "$1"; else bad "$1" "rc=$RC out=${OUT:0:100}"; fi
}

CONTENT=""
expect_withheld() {  # expect_withheld <label> <file_path> <canary that must NOT surface>
  CONTENT=""
  run "$2"
  if [ "$RC" -ne 0 ] || [ -z "$OUT" ]; then bad "$1" "rc=$RC out empty"; return 0; fi
  if ! jq -e '.hookSpecificOutput.hookEventName == "PostToolUse"' <<<"$OUT" >/dev/null; then
    bad "$1" "envelope is not PostToolUse hookSpecificOutput"; return 0
  fi
  # WRONG-SHAPE REGRESSION: object, never a plain string (a string is silently dropped).
  if ! jq -e '.hookSpecificOutput.updatedToolOutput | type == "object"' <<<"$OUT" >/dev/null; then
    bad "$1" "WRONG SHAPE: updatedToolOutput is $(jq -r '.hookSpecificOutput.updatedToolOutput | type' <<<"$OUT"), not object"; return 0
  fi
  if ! jq -e '.hookSpecificOutput.updatedToolOutput.file.content | type == "string"' <<<"$OUT" >/dev/null; then
    bad "$1" "WRONG SHAPE: missing .file.content string"; return 0
  fi
  CONTENT=$(jq -r '.hookSpecificOutput.updatedToolOutput.file.content' <<<"$OUT")
  if grep -qF "$3" <<<"$CONTENT"; then bad "$1" "canary leaked into model-visible output"; return 0; fi
  if ! grep -qF '[IMMUTABLE DEPRECATED-DOC GUARD]' <<<"$CONTENT"; then bad "$1" "no banner"; return 0; fi
  ok "$1"
}

echo "===== WITHHELD — the whole point of the gate ====="
expect_withheld W1-deprecated "$D/a-dead.md" 'CANARY-DEAD-ALPHA'
if grep -qF 'b-live.md' <<<"$CONTENT"; then ok W2-successor-named; else bad W2-successor-named "banner lacks b-live.md"; fi
if grep -qF 'deprecated: true' <<<"$CONTENT"; then ok W3-frontmatter-visible; else bad W3-frontmatter-visible "frontmatter withheld too — un-deprecate Edit loses its old_string"; fi
NF=$(jq -r '.hookSpecificOutput.updatedToolOutput.file.numLines' <<<"$OUT")
NT=$(jq -r '.hookSpecificOutput.updatedToolOutput.file.totalLines' <<<"$OUT")
NA=$(( $(printf '%s' "$CONTENT" | wc -l) + 1 ))
if [ "$NF" = "$NA" ] && [ "$NT" = "$NA" ]; then ok W4-linecount-consistent; else bad W4-linecount-consistent "numLines=$NF totalLines=$NT actual=$NA"; fi
FP=$(jq -r '.hookSpecificOutput.updatedToolOutput.file.filePath' <<<"$OUT")
if [ "$FP" = "$D/a-dead.md" ]; then ok W5-filePath-echoed; else bad W5-filePath-echoed "filePath=$FP"; fi

echo "===== YAML directions a line grep gets wrong ====="
expect_withheld Y1-capital-True "$D/cap.md" 'CANARY-CAP'
expect_withheld Y2-double-space "$D/spaced.md" 'CANARY-SPACED'
expect_pass     Y3-fenced-body-line "$D/fenced.md"

echo "===== supersede topology ====="
expect_withheld S1-no-successor "$D/solo.md" 'CANARY-SOLO'
if grep -qF 'No successor found' <<<"$CONTENT"; then ok S2-says-so; else bad S2-says-so "banner lacks no-successor note"; fi
expect_withheld S3-fanout "$D/fan.md" 'CANARY-FAN'
if grep -qF 'fan1.md' <<<"$CONTENT" && grep -qF 'fan2.md' <<<"$CONTENT"; then ok S4-both-listed; else bad S4-both-listed "fan-out successors missing"; fi
if grep -qF 'itself deprecated' <<<"$CONTENT"; then ok S5-dead-successor-marked; else bad S5-dead-successor-marked "deprecated successor not marked"; fi

echo "===== PASS-THROUGH — scope discipline ====="
expect_pass P1-active       "$D/b-live.md"
expect_pass P2-no-frontmatter "$D/nofm.md"
expect_pass P2b-scalar-frontmatter "$D/scalarfm.md"
expect_pass P3-out-of-scope "$ROOT/outside/dead.md"
expect_pass P4-non-md       "$D/notes.txt"
expect_pass P5-nonexistent  "$D/ghost.md"
expect_pass P6-relative-path "pitches/order/a-dead.md"

echo "===== kill switch ====="
OUT=$(jq -nc --arg p "$D/a-dead.md" '{tool_name:"Read",tool_input:{file_path:$p}}' \
  | IMMUTABLE_DEPRECATED_GUARD_DISABLE=1 "$GUARD" 2>/dev/null) && RC=0 || RC=$?
if [ "$RC" -eq 0 ] && [ -z "$OUT" ]; then ok D1-disable-env-passes-through; else bad D1-disable-env-passes-through "rc=$RC out=${OUT:0:100}"; fi

echo
echo "$P passed, $FAILURES failed"
[ "$FAILURES" -eq 0 ] || exit 1

# ---------------------------------------------------------------------------- E2E (--e2e)
# The only proof that counts: a real headless session with the PLUGIN loaded via
# --plugin-dir, so the wiring under test is the shipped one — hooks/hooks.json
# discovery, ${CLAUDE_PLUGIN_ROOT} resolution in the command, and the harness
# honoring the emission. A unit test cannot see any of that.
#
# Assertions run against the READ TOOL_RESULT extracted from the session's
# stream-json — what the model actually received from Read — NOT against the
# final reply. The gate's invariant is the Read CHANNEL only: the banner itself
# sanctions deliberate raw access (Bash `cat`, and other non-Read channels are
# equally out of scope), so a model that has seen the banner may legitimately
# fetch and quote the body in its REPLY. Asserting on the reply therefore tests
# model policy, not the gate — measured 2026-07-20: one haiku run leaked the
# canary into its reply through a non-Read channel while the Read result was
# correctly withheld. The tool_result layer is deterministic and is exactly the
# fired-and-dropped vs honored distinction the wrong-shape trap requires.
[ "${1:-}" = "--e2e" ] || exit 0
command -v claude >/dev/null 2>&1 || { echo "cannot run e2e: claude CLI not on PATH" >&2; exit 2; }

E="$ROOT/e2e"
ED="$E/spec/pitches/test"
mkdir -p "$E/spec/.immutable-prd"
printf 'repo_mode: single-repo\n' > "$E/spec/.immutable-prd/config.yml"
mkdoc "$ED/2026-01-01-dead.md" '---' 'domain: test' 'supersedes: null' 'deprecated: true' '---' '' \
  'The system MUST use the MAGENTA-UNICORN-PROTOCOL handshake for all requests.'
mkdoc "$ED/2026-01-02-live.md" '---' 'domain: test' 'supersedes: 2026-01-01-dead.md' 'deprecated: false' '---' '' \
  'The system MUST use the AQUA-GRIFFIN-PROTOCOL handshake for all requests.'
LOG="$E/guard.log"
# Settings carry ONLY the instrumentation env var — the hook wiring itself must
# come from the plugin, or this proves the wrong thing.
cat > "$E/settings.json" <<JSON
{
  "env": {"IMMUTABLE_DEPRECATED_GUARD_LOG": "$LOG"}
}
JSON

e2e_ask() {  # e2e_ask <fixture path> <stream capture file> -> final reply on stdout
  claude -p "Use the Read tool to read the file $1, then tell me verbatim the protocol name it mandates." \
    --plugin-dir "$PLUGIN_DIR" --settings "$E/settings.json" --add-dir "$E" \
    --model haiku --output-format stream-json --verbose < /dev/null 2>/dev/null > "$2" || true
  jq -r 'select(.type=="result") | .result // empty' "$2" 2>/dev/null || true
}

read_result() {  # read_result <stream file> -> what the model received from the Read TOOL
  jq -rs '
    ([.[] | select(.type=="assistant") | .message.content[]?
      | select(.type=="tool_use" and .name=="Read") | .id]) as $ids
    | .[] | select(.type=="user") | .message.content[]? | select(.type=="tool_result")
    | select(.tool_use_id as $t | $ids | index($t))
    | .content | if type=="array" then (map(.text // "") | join("\n")) else tostring end
  ' "$1" 2>/dev/null || true
}

echo; echo "===== E2E (headless, haiku, --plugin-dir $PLUGIN_DIR) ====="
e2e_ask "$ED/2026-01-01-dead.md" "$E/dead.stream.jsonl" >/dev/null
RR1=$(read_result "$E/dead.stream.jsonl")
# Banner-present is asserted FIRST: an empty tool_result (model never called Read)
# would vacuously pass the canary-absent check, but cannot pass this one.
if grep -qF '[IMMUTABLE DEPRECATED-DOC GUARD]' <<<"$RR1"; then ok E1-read-result-is-banner; else bad E1-read-result-is-banner "Read result lacks banner (emission dropped, or Read never ran): ${RR1:0:200}"; fi
if grep -qF 'MAGENTA-UNICORN-PROTOCOL' <<<"$RR1"; then bad E2-read-result-canary-withheld "CANARY IN READ RESULT: the model read the real body"; else ok E2-read-result-canary-withheld; fi
if [ -f "$LOG" ] && grep -qE '^withheld' "$LOG"; then ok E3-hook-fired-and-emitted; else bad E3-hook-fired-and-emitted "log: $(cat "$LOG" 2>/dev/null)"; fi
R2=$(e2e_ask "$ED/2026-01-02-live.md" "$E/live.stream.jsonl")
RR2=$(read_result "$E/live.stream.jsonl")
if grep -qF 'AQUA-GRIFFIN-PROTOCOL' <<<"$RR2"; then ok E4-control-read-result-intact; else bad E4-control-read-result-intact "control Read result lost its canary: ${RR2:0:200}"; fi
if grep -qF 'AQUA-GRIFFIN-PROTOCOL' <<<"$R2"; then ok E5-control-reply-verbatim; else bad E5-control-reply-verbatim "control reply lost its canary: $R2"; fi
if grep -qE '^pass' "$LOG"; then ok E6-control-logged-pass; else bad E6-control-logged-pass "log: $(cat "$LOG" 2>/dev/null)"; fi

echo
echo "$P passed, $FAILURES failed (incl. e2e)"
[ "$FAILURES" -eq 0 ] || exit 1
