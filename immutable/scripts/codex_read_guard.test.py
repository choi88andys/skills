#!/usr/bin/env python3
"""Exercise the Codex read paths using disposable consumer files and fresh tokens."""
import json
import os
import secrets
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
READER = [sys.executable, "-B", str(SCRIPTS / "read_doc.py")]
SEARCH = [sys.executable, "-B", str(SCRIPTS / "search_docs.py")]


class ReadTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="immutable fixture ")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / ".immutable-prd").mkdir()
        self.docs = self.root / "order specs"
        self.docs.mkdir()
        self.dead, self.live = (secrets.token_hex(16) for _ in range(2))
        self.old = self.docs / "old pitch.md"
        self.current = self.docs / "current pitch.md"
        self.old.write_text(f"---\ndeprecated: True\n---\nrule {self.dead}\n")
        self.current.write_text(f"---\nsupersedes: old pitch.md\n---\nrule {self.live}\n")
        self.source = self.root / "source.py"
        self.source.write_text("rule = 42\n")

    def output(self, command):
        return subprocess.check_output(command, cwd=self.root, text=True)

    def check_banner(self, output):
        self.assertIn("Body withheld.", output)
        self.assertIn("order specs/current pitch.md", output)
        self.assertNotIn(self.dead, output)

    def test_lines(self):
        self.check_banner(self.output([*READER, "--lines", "4,4", "--", self.old]))
        self.assertEqual(f"rule {self.live}\n", self.output([*READER, "--lines", "4,$", "--", self.current]))

    def test_multiple_inputs(self):
        output = self.output([*READER, "--", self.source, self.old, self.current])
        self.check_banner(output)
        self.assertIn(self.source.read_text(), output)
        self.assertIn(self.current.read_text(), output)

    def test_audit(self):
        notice = self.output([*READER, "--", self.old])
        audit = next(line for line in notice.splitlines() if " --audit -- " in line)
        output = self.output(shlex.split(audit))
        self.assertTrue(output.startswith("[IMMUTABLE HISTORICAL AUDIT]"))
        self.assertIn(self.old.read_text(), output)
        self.assertTrue(output.rstrip().endswith("[END IMMUTABLE HISTORICAL AUDIT]"))

    def test_search(self):
        out = self.output([*SEARCH, "-ni", "-e", "RULE", "."])
        self.check_banner(out)
        self.assertIn(f"current pitch.md:4:rule {self.live}", out)
        self.assertIn("source.py:1:rule = 42", out)
        out = self.output([*SEARCH, "--glob=*.md", "never matches", self.docs])
        self.check_banner(out)
        self.assertNotIn(self.live, out)
        self.assertNotIn("source.py", out)

    def hook(self, command, cwd=None):
        event = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "cwd": str(cwd or self.root), "tool_input": {"command": command}}
        result = subprocess.run([sys.executable, "-B", SCRIPTS / "codex_read_guard.py"],
                                cwd=self.root, input=json.dumps(event), capture_output=True,
                                text=True, check=True)
        self.assertNotIn(self.dead, result.stdout + result.stderr)
        if not result.stdout:
            return None
        out = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual((out["hookEventName"], out["permissionDecision"]), ("PreToolUse", "deny"))
        return out["permissionDecisionReason"].split("\n", 1)[1]

    def manifest_hook(self, plugin_root, command):
        """Run the Codex manifest's hook command the way Codex does: through a shell."""
        manifest = json.loads((SCRIPTS.parent / ".codex-plugin/plugin.json").read_text())
        hook, = manifest["hooks"]["hooks"]["PreToolUse"][0]["hooks"]
        event = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "cwd": str(self.root), "tool_input": {"command": command}}
        return subprocess.run(["sh", "-c", hook["command"]], cwd=self.root, input=json.dumps(event),
                              capture_output=True, text=True,
                              env={**os.environ, "PLUGIN_ROOT": str(plugin_root)})

    def test_manifest_hook_passes_when_its_script_is_missing(self):
        old = shlex.quote(str(self.old.relative_to(self.root)))
        empty = self.root / "plugin without scripts"
        empty.mkdir()
        gone = self.manifest_hook(empty, f"cat {old}")
        self.assertEqual((gone.returncode, gone.stdout, gone.stderr), (0, "", ""))
        live = self.manifest_hook(SCRIPTS.parent, f"cat {old}")
        self.assertEqual(live.returncode, 0)
        self.assertEqual(json.loads(live.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_denied_reads_and_independent_retries(self):
        old = shlex.quote(str(self.old.relative_to(self.root)))
        forms = [
            f"cat {old}", f"cat -- source.py {old}", shlex.join(["cat", str(self.old)]),
            f"sed -n '4p' {old}", f"sed -n -e '4,4p' -- {old}", f"sed -n '40,$p' {old}",
            f"rg -n 'rule' {old}", f"rg -Fw -e rule {old} source.py",
            "rg -n rule", "rg -i -g '*.md' RuLe .", "rg --glob '*.md' rule 'order specs'",
            "rg --hidden --glob=*.md -- RULE .", "rg -S rule 'order specs' source.py",
            f"printf '%s' 'safe; cat example' && cat {old}", f"false || cat {old}",
            f"true; cat {old}", f"pwd\ncat {old}", f"cat {old} | head -n 1",
            "cd -- 'order specs' && cat 'old pitch.md'",
            "cd 'order specs' && rg --word-regexp --ignore-case --line-number rule",
            "rg --files | rg --fixed-strings --smart-case rule 'order specs'",
        ]
        for command in forms:
            with self.subTest(command=command):
                retry = self.hook(command)
                self.assertIsNotNone(retry)
                self.assertIsNone(self.hook(retry))
                self.check_banner(self.output(["sh", "-c", retry]))

    def test_cwd_and_active(self):
        retry = self.hook("cat 'current pitch.md'", self.docs)
        self.assertEqual(self.output(["sh", "-c", retry]), self.current.read_text())
        retry = self.hook("rg -n rule .", self.docs)
        output = self.output(["sh", "-c", retry])
        self.check_banner(output)
        self.assertIn(f":4:rule {self.live}", output)

    def test_unrelated_commands(self):
        old = shlex.quote(str(self.old))
        (self.root / "src").mkdir()
        (self.root / "src/main.py").write_text("hello")
        for command in [
            "cat source.py", "sed -n '1,5p' src/main.py", "rg old src",
            "rg -g '*.py' rule .", "rg --files", "rg --files . | rg -n 'pitch.md'",
            "rg 'order specs/old pitch.md' source.py", f"rg -e {old} src/main.py",
            f"printf '%s' {old}", """echo "quoted ; cat 'order specs/old pitch.md'" """,
            f"git status -- {old}", f"pwd # cat {old}", f"cat <<'TEXT'\ncat {old}\nTEXT",
            shlex.join([*map(str, READER), "--", str(self.old)]),
            shlex.join([*map(str, READER), "--audit", "--", str(self.old)]),
        ]:
            with self.subTest(command=command):
                self.assertIsNone(self.hook(command))

    def test_quoted_operand_and_compound_side_effect(self):
        folder = self.root / "the team's $draft; v1"
        self.docs.rename(folder)
        renamed = folder / self.old.name
        retry = self.hook("touch side-effect && " + shlex.join(["cat", str(renamed)]))
        self.assertFalse((self.root / "side-effect").exists())
        self.assertIsNone(self.hook(retry))
        output = self.output(["sh", "-c", retry])
        self.assertIn("Body withheld.", output)
        self.assertIn(str(folder.name) + "/current pitch.md", output)
        self.assertNotIn(self.dead, output)
        self.assertFalse((self.root / "side-effect").exists())

    def test_directory_selection(self):
        subprocess.run(["git", "init", "--quiet"], cwd=self.root, check=True)
        self.docs.rename(self.root / ".archive")
        self.assertIsNone(self.hook("rg rule ."))
        retry = self.hook("rg --hidden -g '*.md' -g '!current*' rule .")
        out = self.output(["sh", "-c", retry])
        self.assertIn("Body withheld.", out)
        self.assertIn(".archive/current pitch.md", out)
        self.assertNotIn(self.live, out)
        self.assertNotIn(self.dead, out)
        (self.root / ".gitignore").write_text(".archive/\n")
        self.assertIsNone(self.hook("rg --hidden rule ."))

    def test_parent_relative_scope(self):
        with tempfile.TemporaryDirectory(dir=self.root.parent) as sibling:
            plain = Path(sibling)
            outside = plain / "other.md"
            outside.write_text(f"---\ndeprecated: true\n---\n{secrets.token_hex(16)}\n")
            relative = "../" + plain.name + "/other.md"
            self.assertIsNone(self.hook(shlex.join(["cat", relative])))
            self.assertIsNone(self.hook(shlex.join(["rg", "rule", "../" + plain.name])))
            self.assertEqual(self.output([*READER, "--", relative]), outside.read_text())

            # A symlink before '..' changes which parent the kernel reaches.
            (plain / "child").mkdir()
            (self.root / "through").symlink_to(plain / "child", target_is_directory=True)
            (self.root / "other.md").write_text("different file\n")
            self.assertIsNone(self.hook("cat through/../other.md"))
            self.assertEqual(self.output([*READER, "--", "through/../other.md"]), outside.read_text())

            # A Markdown alias inside the marker still gets checked after '..'.
            (self.root / "alias.md").symlink_to(outside)
            retry = self.hook("cat 'order specs/../alias.md'")
            result = self.output(["sh", "-c", retry])
            self.assertIn("Body withheld.", result)
            self.assertNotIn(outside.read_text().splitlines()[-1], result)

    def test_nested_scope_and_symlink(self):
        link = self.root.parent / (self.root.name + " alias")
        link.symlink_to(self.old)
        self.addCleanup(link.unlink)
        self.check_banner(self.output(["sh", "-c", self.hook(shlex.join(["cat", str(link)]))]))
        with tempfile.TemporaryDirectory() as plain:
            outside = Path(plain) / "plain.md"
            outside.write_text(self.old.read_text())
            self.assertIsNone(self.hook("rg rule .", outside.parent))
            self.assertIsNone(self.hook("cat plain.md", outside.parent))
        # Start above the marker, but constrain discovery to this fixture alone.
        retry = self.hook(shlex.join(["rg", "rule", self.root.name]), self.root.parent)
        self.check_banner(self.output(["sh", "-c", retry]))


class ConfiguredScopeTests(ReadTests):
    """A repo whose config names its document folders: only those are guarded."""

    def setUp(self):
        super().setUp()
        self.docs = self.docs.rename(self.root / "adr")
        self.old, self.current = self.docs / self.old.name, self.docs / self.current.name
        self.config = self.root / ".immutable-prd" / "config.yml"
        self.config.write_text("version: 3\nrepo_mode: two-repo-app\nteam_language: ko\nadr_path: adr/\n")
        # A Markdown file outside the document folder, carrying the flag by accident.
        self.notes = self.root / "docs" / "notes.md"
        self.notes.parent.mkdir()
        self.notes.write_text(f"---\ndeprecated: true\n---\nnote {secrets.token_hex(16)}\n")
        (self.root / "CLAUDE.md").write_text("instructions\n")

    def check_banner(self, output):
        self.assertIn("Body withheld.", output)
        self.assertIn("adr/current pitch.md", output)
        self.assertNotIn(self.dead, output)

    # Inherited tests that name the old folder or move it are covered by ReadTests.
    test_denied_reads_and_independent_retries = None
    test_quoted_operand_and_compound_side_effect = None
    test_directory_selection = None
    test_parent_relative_scope = None

    def test_files_outside_document_folders_read_raw(self):
        for command in ["cat CLAUDE.md", "cat docs/notes.md", "sed -n '1,4p' docs/notes.md",
                        "rg -n note docs", "rg -g '*.md' instructions CLAUDE.md docs"]:
            with self.subTest(command=command):
                self.assertIsNone(self.hook(command))
        self.assertEqual(self.output([*READER, "--", self.notes]), self.notes.read_text())

    def test_document_folder_stays_guarded(self):
        retry = self.hook("cat 'adr/old pitch.md'")
        self.assertIsNotNone(retry)
        self.check_banner(self.output(["sh", "-c", retry]))

    def test_unreadable_config_guards_every_markdown_file(self):
        for broken in ["repo_mode: [unclosed\n", "repo_mode: two-repo-app\n", "- a list\n"]:
            with self.subTest(config=broken):
                self.config.write_text(broken)
                self.assertIsNotNone(self.hook("cat docs/notes.md"))


if __name__ == "__main__":
    unittest.main()
