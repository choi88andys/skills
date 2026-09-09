#!/usr/bin/env bash
# plugin_manifest.test.sh — the plugin's packaging invariants, as a test.
#
# WHY THIS FILE EXISTS
# This plugin keeps its skills at the plugin root (`immutable/<name>/SKILL.md`),
# not under the conventional `skills/` directory, so the skill list must be
# ENUMERATED in a manifest. Until v0.11.0 it was enumerated only in the
# marketplace file — which is fine for a marketplace install and fatal for
# every other load path: `claude --plugin-dir <plugin>` reads plugin.json
# alone, found no `skills`, registered ZERO skills, and — because a
# --plugin-dir plugin with the same name shadows the installed one — removed
# `/immutable:*` from the session entirely. `claude plugin validate` passed in
# that state (measured 2026-09-08 with two byte-identical copies differing only
# in the `skills` field). The first pre-release dogfood run through
# --plugin-dir is what hit it.
#
# Every rule below is one of CLAUDE.md's "Gotchas" that has shipped as a real
# bug at least once. They are cheap to check and nothing else checks them.
#
# Usage:  bash immutable/scripts/plugin_manifest.test.sh
# Exit:   0 all cases passed · 1 a case failed · 2 the test could not run.
# Needs:  python3; the strings-parity case additionally needs PyYAML and is
#         reported as SKIP (not PASS) without it.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="$(cd "$PLUGIN/.." && pwd)"
PJ="$PLUGIN/.claude-plugin/plugin.json"
MJ="$REPO/.claude-plugin/marketplace.json"
[ -f "$PJ" ] && [ -f "$MJ" ] || { echo "cannot run: manifests not found ($PJ, $MJ)" >&2; exit 2; }
command -v python3 >/dev/null || { echo "cannot run: python3 not found" >&2; exit 2; }

FAILURES=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n        %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }
skip() { printf 'SKIP  %s\n        %s\n' "$1" "$2"; }

echo "plugin manifests — packaging invariants (CLAUDE.md Gotchas)"
echo

# One python pass computes every fact; bash only judges them.
FACTS="$(python3 - "$PJ" "$MJ" "$PLUGIN" <<'PYX'
import json, os, sys
pj, mj, plugin = sys.argv[1:4]
p = json.load(open(pj, encoding="utf-8")); m = json.load(open(mj, encoding="utf-8"))
entry = next((e for e in m.get("plugins", []) if e.get("name") == p.get("name")), None)
on_disk = sorted(d for d in os.listdir(plugin) if os.path.isfile(os.path.join(plugin, d, "SKILL.md")))
norm = lambda xs: sorted(x[2:] if x.startswith("./") else x for x in (xs or []))
print("plugin_skills=" + ",".join(norm(p.get("skills"))))
print("market_skills=" + ",".join(norm(entry.get("skills")) if entry else []))
print("disk_skills=" + ",".join(on_disk))
print("has_skills_field=" + ("1" if "skills" in p else "0"))
print("desc_equal=" + ("1" if entry and p.get("description") == entry.get("description") else "0"))
print("keywords_equal=" + ("1" if entry and sorted(p.get("keywords") or []) == sorted(entry.get("keywords") or []) else "0"))
print("version=" + str(p.get("version", "")))
print("entry_found=" + ("1" if entry else "0"))
PYX
)"
get() { sed -n "s/^$1=//p" <<<"$FACTS"; }

# C1 — the plugin describes its own skills: plugin.json carries `skills`, and it
# names exactly the directories on disk. This is the --plugin-dir zero-skills bug.
if [ "$(get has_skills_field)" = "1" ] && [ "$(get plugin_skills)" = "$(get disk_skills)" ] && [ -n "$(get disk_skills)" ]; then
  pass "C1 plugin.json skills == skill dirs on disk ($(get disk_skills | tr ',' ' '))"
else
  fail "C1 plugin.json skills vs disk" "field present=$(get has_skills_field) plugin=[$(get plugin_skills)] disk=[$(get disk_skills)]"
fi

# C2 — the marketplace entry lists the same skills (v0.6.2 shipped five missing).
if [ "$(get entry_found)" = "1" ] && [ "$(get market_skills)" = "$(get disk_skills)" ]; then
  pass "C2 marketplace.json skills == skill dirs on disk"
else
  fail "C2 marketplace.json skills vs disk" "entry=$(get entry_found) market=[$(get market_skills)] disk=[$(get disk_skills)]"
fi

# C3 — description and keywords mirrored verbatim between the two manifests.
if [ "$(get desc_equal)" = "1" ] && [ "$(get keywords_equal)" = "1" ]; then
  pass "C3 description + keywords mirrored between plugin.json and marketplace.json"
else
  fail "C3 manifest mirror" "description equal=$(get desc_equal) keywords equal=$(get keywords_equal)"
fi

# C4 — a version is declared once, in plugin.json, and looks like semver.
if [[ "$(get version)" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  pass "C4 plugin.json version is semver ($(get version))"
else
  fail "C4 plugin.json version" "got [$(get version)]"
fi

# C5 — strings catalogs: en ↔ ko key parity, ja deliberately empty (v0.7.4 bug).
if python3 -c 'import yaml' 2>/dev/null; then
  PAR="$(python3 - "$PLUGIN/strings" <<'PYX'
import sys, yaml, pathlib
d = pathlib.Path(sys.argv[1])
en = yaml.safe_load(open(d/"strings.en.yml", encoding="utf-8"))["strings"]
ko = yaml.safe_load(open(d/"strings.ko.yml", encoding="utf-8"))["strings"]
ja = yaml.safe_load(open(d/"strings.ja.yml", encoding="utf-8")).get("strings") or {}
print("ko_missing=" + ",".join(sorted(set(en) - set(ko))))
print("en_missing=" + ",".join(sorted(set(ko) - set(en))))
print("ja_keys=" + str(len(ja)))
PYX
)"
  km="$(sed -n 's/^ko_missing=//p' <<<"$PAR")"; em="$(sed -n 's/^en_missing=//p' <<<"$PAR")"; jk="$(sed -n 's/^ja_keys=//p' <<<"$PAR")"
  if [ -z "$km" ] && [ -z "$em" ] && [ "$jk" = "0" ]; then
    pass "C5 strings: en ↔ ko key parity, ja scaffold empty"
  else
    fail "C5 strings parity" "ko missing=[$km] en missing=[$em] ja keys=$jk"
  fi
else
  skip "C5 strings parity" "PyYAML not installed (pip install pyyaml)"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all cases passed."
  exit 0
fi
echo "$FAILURES case(s) failed."
exit 1
