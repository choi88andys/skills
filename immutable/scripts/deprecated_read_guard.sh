#!/usr/bin/env bash
# deprecated_read_guard.sh — PostToolUse(Read) withholding gate for deprecated SDD docs.
# Wired by `hooks/hooks.json` at the plugin root; runs as
# `bash ${CLAUDE_PLUGIN_ROOT}/scripts/deprecated_read_guard.sh` on every Read.
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
[ "$first" = "---" ] || exit 0

# ------------------------------------------------- L2: real YAML parse + emission (python3)
# PyYAML is already a hard dependency of this plugin's validate_docs.py; this mirrors its
# FRONTMATTER_RE + yaml.safe_load exactly. Never a line grep: `deprecated: True` and
# `deprecated:  true` are live YAML that a grep for '^deprecated: true' reads as ACTIVE,
# and a fenced schema example's `deprecated: true` body line reads as DEPRECATED. Both
# directions were proven on fixtures (2026-07-16).
exec python3 - "$fp" "$root" <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    # Without PyYAML the gate is dead. Fail open for the Read (blocking every Read would
    # be worse) but say so deterministically — additionalContext delivery is guaranteed
    # even when heeding is not, and the plugin's own validate_docs.py is equally broken
    # in this state, so the operator hears about it at the first deprecated-doc read.
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "[immutable-deprecated-guard] PyYAML missing: the deprecated-doc "
                             "read gate is INERT (and the plugin's validate_docs.py is equally "
                             "broken). pip3 install pyyaml.",
    }}))
    sys.exit(0)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)  # validate_docs.py verbatim

path = Path(sys.argv[1])
root = Path(sys.argv[2])

LOG = os.environ.get("IMMUTABLE_DEPRECATED_GUARD_LOG", "")


def log(outcome: str, detail: str = "") -> None:
    if not LOG:
        return
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{outcome}\t{path}\t{detail}\n")
    except OSError:
        pass  # instrumentation must never change the verdict


def load_fm(p: Path):
    """Frontmatter dict, or None — same semantics as validate_docs.load_frontmatter."""
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None, ""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, ""
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None, ""
    # Scalar/list frontmatter (`---\njust text\n---`) parses fine but has no .get —
    # an AttributeError here would crash the hook and fail OPEN. Not-a-dict ≙ no frontmatter.
    if not isinstance(fm, dict):
        return None, ""
    return fm, m.group(0)


fm, fm_block = load_fm(path)
if fm is None or fm.get("deprecated") is not True:
    log("pass", "active-or-unparsed")
    sys.exit(0)

# Successors live in the SAME domain directory (cross-domain supersede is unsupported by
# the directory convention — validate_docs.check_supersede_chain_integrity). Fan-out is
# legal (one predecessor, N successors), so collect them all. A successor that is itself
# deprecated is listed with its state: Reading it fires this gate again, which names ITS
# successor — the chain walks itself.
successors = []
for sib in sorted(path.parent.glob("*.md")):
    if sib.name == path.name or sib.name in ("README.md", "TEMPLATE.md"):
        continue
    sfm, _ = load_fm(sib)
    if sfm is not None and sfm.get("supersedes") == path.name:
        successors.append((sib, sfm.get("deprecated") is True))

try:
    rel = path.relative_to(root)
except ValueError:
    rel = path

lines = [
    "",
    "[IMMUTABLE DEPRECATED-DOC GUARD] Body withheld.",
    "",
    f"`{rel}` is marked `deprecated: true` (frontmatter above is real and shown in full).",
    "Its body is a DEAD SPEC — textually indistinguishable from a live one — and was",
    "withheld so it cannot be mistaken for current requirements. Do NOT implement from it.",
    "",
]
if successors:
    lines.append("Superseded by (implement from these instead):")
    for sib, dead in successors:
        try:
            srel = sib.relative_to(root)
        except ValueError:
            srel = sib
        lines.append(f"  - {srel}" + ("  (itself deprecated — read it to follow the chain)" if dead else ""))
else:
    lines.append("No successor found in this directory — the supersede may be mid-flight,")
    lines.append("or the chain may end here. `git log` has the history.")
lines += [
    "",
    "Legitimate raw-body access (audit, supersede review): use Bash — `cat` or",
    "`git show`/`git log -p` — deliberately. This gate covers only the Read tool.",
    "To un-deprecate, Edit the `deprecated: true` frontmatter line visible above.",
]

content = fm_block + "\n".join(lines)
n = content.count("\n") + 1

# THE SHAPE: mirror Read's tool_response object exactly. A plain string here is silently
# dropped by the harness and the model reads the real body — the test sibling's
# wrong-shape regression pins this.
out = {
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "updatedToolOutput": {
            "type": "text",
            "file": {
                "filePath": str(path),
                "content": content,
                "numLines": n,
                "startLine": 1,
                "totalLines": n,
            },
        },
    }
}
print(json.dumps(out))
log("withheld", f"successors={len(successors)}")
PYEOF
