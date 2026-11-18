#!/usr/bin/env python3
"""Install into a temporary Codex home. --e2e also checks a real model's tool results."""
import argparse
import ast
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


def tool_results(codex, home, prompt, model, sandbox):
    flags = ["--model", model] if model else []
    # The hook source under test is the checkout just copied to this temporary
    # home. This invocation-only trust setting creates no user trust record.
    events = [json.loads(line) for line in codex(
        "exec", "--skip-git-repo-check", "--sandbox", sandbox,
        "--dangerously-bypass-hook-trust", "--json", *flags, prompt
    ).splitlines()]
    thread = next(e["thread_id"] for e in events if e["type"] == "thread.started")
    rollout, = (home / "sessions").rglob("*" + thread + ".jsonl")
    transcript = rollout.read_text()
    outputs = []
    for line in transcript.splitlines():
        item = json.loads(line)
        payload = item["payload"]
        # Keep ALL delivered outputs in order, including partial exec output,
        # later write_stdin polls and nested code-mode tool results.
        if item["type"] == "response_item" and payload["type"] in (
            "function_call_output", "custom_tool_call_output"
        ):
            outputs.append(str(payload["output"]))
    assert outputs, "client delivered no tool results"
    return outputs, transcript


def test_reads(codex, home, consumer, installed, model):
    subprocess.run(["git", "init", "--quiet"], cwd=consumer, check=True)
    (consumer / ".immutable-prd").mkdir()
    (consumer / ".immutable-prd/config.yml").write_text(
        "version: 3\nrepo_mode: single-repo\nteam_language: en\npitches_path: pitches/\nadr_path: adr/\n"
    )
    docs = consumer / "pitches/order specs"
    docs.mkdir(parents=True)
    dead, live = secrets.token_hex(16), secrets.token_hex(16)
    old, current = docs / "checkout.md", docs / "current.md"
    old.write_text(f"---\ndeprecated: true\n---\nSet CHECKOUT_RULE to {dead}.\n")
    current.write_text(f"---\nsupersedes: checkout.md\n---\nSet CHECKOUT_RULE to {live}.\n")
    source = consumer / "checkout.py"
    source.write_text('CHECKOUT_RULE = "pending"\n')

    # Normal implementation task, no skill invocation and no reader suggested.
    # Pin an ordinary first read so a voluntary reader choice cannot pass.
    output, trace = tool_results(codex, home, (
        "Update CHECKOUT_RULE in checkout.py to the value required by the checkout pitch. "
        "Start with the repository's reference command: cat -- 'pitches/order specs/checkout.md'. "
        "Then finish the source change using the current requirements."
    ), model, "workspace-write")
    assert dead not in trace, "obsolete token reached the implementation session"
    denial = next(i for i, out in enumerate(output) if "Retry this read separately" in out
                  and str(installed / "scripts/read_doc.py") in out)
    notice = next(i for i, out in enumerate(output) if "Body withheld." in out
                  and "pitches/order specs/current.md" in out)
    successor = next(i for i, out in enumerate(output) if live in out)
    assert denial < notice <= successor, "expected denial, protected retry and successor"
    expected = ast.parse(f"CHECKOUT_RULE = {live!r}").body[0]
    assert any(ast.dump(stmt) == ast.dump(expected) for stmt in ast.parse(source.read_text()).body), (
        "implementation did not set CHECKOUT_RULE to the current requirement"
    )
    print("PASS: ordinary coding task recovered from the installed hook denial and implemented the successor",
          flush=True)

    # Independent session exercising line and directory search retries. The
    # pattern and line target body text, not the frontmatter or banner.
    output, trace = tool_results(codex, home, (
        "Check two checkout documentation lookups, separately and in order. "
        "First run sed -n '4,4p' 'pitches/order specs/checkout.md'. "
        "Then run cd 'pitches/order specs' && rg -ni -g '*.md' 'CHECKOUT_RULE' . "
        "If a lookup is intercepted, follow its retry before starting the next one. "
        "Report what the two lookups returned."
    ), model, "read-only")
    assert dead not in trace, "obsolete token reached the range/search session"
    for script in ("read_doc.py", "search_docs.py"):
        assert any("Retry this read separately" in out and str(installed / "scripts" / script) in out
                   for out in output), f"missing installed denial for {script}"
    assert sum("Body withheld." in out and "current.md" in out for out in output) >= 2
    assert any(live in out for out in output), "directory retry lost active matches"
    print("PASS: installed line-range and recursive search retries withheld the obsolete body", flush=True)

    # Historical review gets its own session. Force an early yield so at least
    # one real run also exercises result delivery after the initial tool return.
    audit = shlex.join(["python3", "-B", str(installed / "scripts/read_doc.py"), "--audit", "--", str(old)])
    output, _ = tool_results(codex, home, (
        "Historical supersede review of a synthetic fixture. Run exactly this shell command "
        "with yield_time_ms=100. Return the initial partial output before making a separate poll. "
        "Keep its historical context visible in the tool output.\n" + "echo AUDIT_STARTING && sleep 2 && " + audit
    ), model, "read-only")
    first = next(i for i, out in enumerate(output) if "AUDIT_STARTING" in out and re.search(r"session ID|session_id", out, re.I))
    delivered = "\n".join(output[first + 1:])
    assert dead not in "\n".join(output[:first + 1]), "expected the audit body in a later result"
    start = delivered.index("[IMMUTABLE HISTORICAL AUDIT]")
    assert start < delivered.index(dead) < delivered.index("[END IMMUTABLE HISTORICAL AUDIT]")
    print("PASS: separate historical review delivered the raw token with audit markers on a later poll")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--e2e", action="store_true", help="requires Codex model access in the temporary home")
    parser.add_argument("--model", help="model for --e2e")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="immutable-test-") as tmp:
        home = Path(tmp) / "codex home"
        consumer = Path(tmp) / "consumer"
        home.mkdir()
        consumer.mkdir()

        env = {**os.environ, "CODEX_HOME": str(home)}
        if args.e2e and os.environ.get("OPENAI_API_KEY"):
            env.setdefault("CODEX_API_KEY", os.environ["OPENAI_API_KEY"])

        def codex(*args):
            return subprocess.check_output(
                ["codex", *args], cwd=consumer, env=env,
                stdin=subprocess.DEVNULL, text=True, timeout=300,
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
        # Exercise every supported shell form and its exact retry from the
        # installed copy, including paths with spaces and filename-only searches.
        subprocess.run([sys.executable, "-B", installed / "scripts/codex_read_guard.test.py"],
                       cwd=consumer, check=True)
        if args.e2e:
            test_reads(codex, home, consumer, installed, args.model)


if __name__ == "__main__":
    main()
