#!/usr/bin/env bash
# deprecated_read_guard.sh — PostToolUse(Read) withholding gate for deprecated SDD docs.
# Wired by `hooks/hooks.json` at the plugin root; runs as
# `bash "${CLAUDE_PLUGIN_ROOT}/scripts/deprecated_read_guard.sh"` on every Read.
#
# THE INVARIANT: the body of a `deprecated: true` immutable-SDD document never reaches the
# model through the Read tool. The frontmatter (which carries the deprecation marker) stays
# visible; the body is replaced by a banner naming the superseding file(s).
#
# WHY WITHHOLD, not warn, not deny. /immutable enforces its deprecation invariant on the
# WRITE path (validate_docs.py + CI) and nothing on the read path. A deprecated pitch's body
# is textually indistinguishable from a live one — same template, same normative "MUST"
# prose — and the only marker is one frontmatter line. A session read one and implemented
# from it. CI cannot catch this class: every document is valid; the defect is in WHICH one
# was read, which leaves no artifact. A belief formed from a dead spec has no bad tool call
# to block — the Read, the code, the commit are each individually legitimate — so the only
# deterministic fix is to remove the input. `deny` is wrong (reading a deprecated doc is
# legitimate: audits, the supersede flow); `additionalContext` is insufficient (delivery is
# deterministic, heeding is probabilistic). Withholding does not depend on heeding.
#
# THE SHAPE TRAP (measured 2026-07-16): Read's tool_response is an OBJECT —
#   {"type":"text","file":{filePath,content,numLines,startLine,totalLines}}
# — and `updatedToolOutput` must mirror that shape exactly. A plain string is a SILENT
# no-op: the hook fires, emits valid JSON, exits 0, the harness drops it, and the model
# reads the real body anyway — zero error on any stream. The test sibling carries a
# wrong-shape regression so nobody "simplifies" this back.
#
# ESCAPES, deliberate: this gate covers the Read TOOL only. `cat` / `git show` via Bash
# read the raw body — that is the sanctioned audit path (deliberate, not accidental).
# Frontmatter stays visible so an Edit that un-deprecates (`deprecated: true` → removal)
# still has its exact old_string; the supersede flow itself only ever edits LIVE docs,
# which pass through untouched.
#
# Instrumentation: set IMMUTABLE_DEPRECATED_GUARD_LOG=<path> to append fired/withheld/pass
# lines — without it, a no-op hook and an ignored emission are indistinguishable from
# outside (that distinction is what cracked the shape trap).
set -euo pipefail

# Kill switch: set IMMUTABLE_DEPRECATED_GUARD_DISABLE=1 (e.g. in a settings `env` block)
# to turn the gate off without forking the plugin — the plugin system has no per-hook
# toggle, so this is the sanctioned off-switch. Disabling the whole plugin also works.
[ -z "${IMMUTABLE_DEPRECATED_GUARD_DISABLE:-}" ] || exit 0

# ---------------------------------------------------------------- L1: cheap bash pre-filter
# This spawns on EVERY Read in EVERY repo (plugin hooks fire session-wide, not per-cwd).
# Everything before the python3 hand-off must stay lean: one jq for the path, a case for
# the extension, a pure-bash ancestor walk.
input=$(cat)
fp=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
[ -n "$fp" ] || exit 0
case "$fp" in
  /*.md) ;;         # absolute markdown paths only — the Read tool always sends absolute
  *) exit 0 ;;
esac
[ -f "$fp" ] || exit 0

# In scope iff an ancestor directory owns a `.immutable-prd/` config dir — that is what
# marks an immutable SDD repo (spec root layout: .immutable-prd/ + pitches/ [+ adr/]).
d=$(dirname "$fp")
root=""
while [ -n "$d" ] && [ "$d" != "/" ] && [ "$d" != "." ]; do
  if [ -d "$d/.immutable-prd" ]; then root="$d"; break; fi
  d=$(dirname "$d")
done
[ -n "$root" ] || exit 0

# Frontmatter head-check: no leading `---`, no frontmatter, nothing to parse — skip the
# python spawn. (read exits non-zero at EOF-without-newline; that is fine, first is set.
# Pre-initialize: on an unreadable file the redirection fails, read never runs, and an
# unset `first` under set -u would kill the script instead of passing through.)
first=""
IFS= read -r first < "$fp" || true
first="${first%$'\r'}"  # a CRLF file's first line is `---\r`; python reads it as `---`
[ "$first" = "---" ] || exit 0

# The Python reader owns YAML parsing, successor discovery and the replacement text.
exec python3 -B "$(dirname "${BASH_SOURCE[0]}")/read_doc.py" --claude-hook "$root" -- "$fp"
