#!/usr/bin/env python3
"""Project the canonical Claude plugin metadata into both marketplace formats."""
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report stale files without writing")
    args = parser.parse_args()
    plugin = Path(__file__).resolve().parents[1]
    repo = plugin.parent
    manifest = json.loads((plugin / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    market_path = repo / ".claude-plugin/marketplace.json"
    market = json.loads(market_path.read_text(encoding="utf-8"))
    # Keep the Claude marketplace's own identity, ordering and unrelated entries.
    entry, = (p for p in market["plugins"] if p["source"] == "./" + plugin.name)
    entry.update({k: manifest[k] for k in ("name", "description", "keywords", "skills")})

    # This Codex format accepts explicit skill roots. Both clients open the
    # same nine files, including when their installer copies the package.
    codex = {k: manifest[k] for k in ("name", "version", "description", "skills", "keywords")}
    # An explicit hook map replaces default discovery of Claude's native Read hook.
    # A plugin update can leave a running session's PLUGIN_ROOT without the script
    # for a while; python3 then exits 2, which Codex reads as a deny, so every Bash
    # call of that session was refused (2026-11-24, the 0.21.4 cache during the
    # 0.22.0 update). Codex runs the command through a shell, so a missing script
    # passes instead: a read guard that is briefly absent costs less than a session
    # that can run nothing.
    guard = '"${PLUGIN_ROOT}/scripts/codex_read_guard.py"'
    codex["hooks"] = {"hooks": {"PreToolUse": [{
        "matcher": "^Bash$",
        "hooks": [{"type": "command",
                   "command": f"if [ -f {guard} ]; then exec python3 -B {guard}; fi; cat >/dev/null; exit 0"}],
    }]}}
    catalog = {
        "name": market["name"],
        "plugins": [{
            "name": entry["name"],
            "source": {"source": "local", "path": entry["source"]},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        }],
    }
    outputs = {
        market_path: market,
        plugin / ".codex-plugin/plugin.json": codex,
        repo / ".agents/plugins/marketplace.json": catalog,
    }
    stale = []
    for path, data in outputs.items():
        content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue
        if args.check:
            stale.append(str(path.relative_to(repo)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    if stale:
        sys.exit("Run python3 immutable/scripts/sync_manifests.py to refresh " + ", ".join(stale))


if __name__ == "__main__":
    main()
