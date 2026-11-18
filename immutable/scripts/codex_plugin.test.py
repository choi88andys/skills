#!/usr/bin/env python3
"""Install into a temporary Codex home. --e2e also checks a real model's tool results."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import tempfile


PLUGIN = Path(__file__).resolve().parents[1]


def test_reads(codex, home, consumer, installed, model):
    (consumer / ".immutable-prd").mkdir()
    tokens = {}
    for name in ("dead", "live"):
        tokens[name] = secrets.token_hex(16)
        (consumer / (name + ".md")).write_text(
            f"---\ndeprecated: {str(name == 'dead').lower()}\n"
            f"supersedes: {'dead.md' if name == 'live' else 'null'}\n---\n{tokens[name]}\n"
        )
    reader = shlex.join([sys.executable, "-B", str(installed / "scripts/read_doc.py"), "--"])
    prompt = (
        "Client integration test in a synthetic repo. Run these three shell commands "
        "separately, in order, waiting for each result. Use no other file read.\n"
        f"1. {reader} dead.md\n2. {reader} live.md\n3. cat dead.md\n"
        "The third command is the intentional raw audit. Report the three outcomes."
    )
    flags = ["--model", model] if model else []
    events = [json.loads(line) for line in codex(
        "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--json", *flags, prompt
    ).splitlines()]
    thread = next(e["thread_id"] for e in events if e["type"] == "thread.started")
    rollout, = (home / "sessions").rglob("*" + thread + ".jsonl")
    # Inspect actual response items. exec_command can return partial output,
    # with the rest delivered later by write_stdin. Ignore the model's prose.
    outputs = []
    for line in rollout.read_text().splitlines():
        item = json.loads(line)
        payload = item["payload"]
        if item["type"] == "response_item" and payload["type"] in (
            "function_call_output", "custom_tool_call_output"
        ):
            outputs.append(str(payload["output"]))
    banner = next(i for i, out in enumerate(outputs) if "Body withheld." in out and "live.md" in out)
    active = next(i for i, out in enumerate(outputs) if tokens["live"] in out)
    audit = next(i for i, out in enumerate(outputs) if tokens["dead"] in out)
    assert banner < active < audit, "unexpected model-visible deprecation, active or audit result"
    print("PASS: reader withheld the body, active read and deliberate raw audit delivered their tokens")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--e2e", action="store_true", help="requires Codex model access in the temporary home")
    parser.add_argument("--model", help="model for --e2e")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="immutable-test-") as tmp:
        home = Path(tmp) / "codex"
        consumer = Path(tmp) / "consumer"
        home.mkdir()
        consumer.mkdir()

        def codex(*args):
            return subprocess.check_output(
                ["codex", *args], cwd=consumer, env={**os.environ, "CODEX_HOME": str(home)},
                stdin=subprocess.DEVNULL, text=True, timeout=240,
            )

        manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        catalog = json.loads((PLUGIN.parent / ".agents/plugins/marketplace.json").read_text())
        codex("plugin", "marketplace", "add", str(PLUGIN.parent))
        selector = manifest["name"] + "@" + catalog["name"]
        installed = Path(json.loads(codex("plugin", "add", selector, "--json"))["installedPath"])
        assert home.resolve() in installed.resolve().parents
        prompt = json.loads(codex("debug", "prompt-input"))
        inventory = next(
            part["text"] for msg in prompt for part in msg.get("content", [])
            if "<skills_instructions>" in part.get("text", "")
        )
        expected = {Path(p).name for p in manifest["skills"]}
        paths = dict(re.findall(r"^- (immutable:[\w-]+): .* \(file: (.+)\)$", inventory, re.M))
        assert set(paths) == {"immutable:" + name for name in expected}, sorted(paths)
        aliases = dict(re.findall(r"^- `(r\d+)` = `(.+)`$", inventory, re.M))
        link = Path(tmp) / "linked skills"
        link.symlink_to(PLUGIN, target_is_directory=True)
        for skill, location in paths.items():
            prefix, _, tail = location.partition("/")
            path = Path(aliases[prefix]) / tail if prefix in aliases else Path(location)
            name = skill.split(":")[1]
            assert path.resolve() == (installed / name / "SKILL.md").resolve()
            assert path.read_bytes() == (PLUGIN / name / "SKILL.md").read_bytes()
            for entry in (path, link / name / "SKILL.md"):
                root = entry.resolve().parents[1]
                for asset in ("RUNTIME.md", "scripts/validate_docs.py", "strings/strings.ko.yml",
                              "examples/_profiles/default-en.yml", "adr/TEMPLATE.md"):
                    assert (root / asset).read_bytes() == (PLUGIN / asset).read_bytes()
        print("PASS: installed inventory and assets for " + ", ".join(sorted(expected)))
        if args.e2e:
            test_reads(codex, home, consumer, installed, args.model)


if __name__ == "__main__":
    main()
