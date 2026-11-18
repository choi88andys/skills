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
    # An explicit inline hook map opts out of Codex auto-loading Claude's Read hook.
    codex["hooks"] = {"hooks": {}}
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
