#!/usr/bin/env python3
"""Exercise the Codex read paths using disposable consumer files and fresh tokens."""
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


if __name__ == "__main__":
    unittest.main()
