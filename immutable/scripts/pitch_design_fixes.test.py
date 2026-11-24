"""Exercise evidence binding and delivery receipts without publishing to a tracker."""
import os
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pitch_design_fixes as fixes


class DesignFixes(unittest.TestCase):
    def setUp(self):
        self.source = dict(tracker="github", repo="example/work", id="8", version="v1")
        self.pin = "https://www.figma.com/design/Example/Page?node-id=1-2&version-id=100"
        self.contract = {"source": self.source, "sections": [{"heading": "Design", "text": self.pin}]}
        self.design = {"section": ["Design"], "pins": [{"url": self.pin, "screens": [{}]}]}
        self.pitch = Path("pitches/signup/2026-11-24-verification.md")
        self.row = dict(key="signup-duration", pin=self.pin, fact="Timer note says three minutes.",
                        quote="The code expires after ten minutes.", change="Update the timer note.")
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(directory.name)
        self.pitch.parent.mkdir(parents=True)
        self.pitch.write_text('---\nreferences: ' + json.dumps({"tickets": [self.source]}) +
                              '\n---\n\n[MUST] ' + self.row["quote"])

    def rows(self):
        return fixes.rows_for(self.contract, self.design, self.pitch, [self.row])

    def test_evidence(self):
        self.assertIn(str(self.pitch), self.rows()["signup-duration"]["pitch"])
        self.design["pins"][0]["error"] = "not read"
        with self.assertRaises(ValueError):
            self.rows()
        del self.design["pins"][0]["error"]
        self.contract["sections"][0]["text"] = "another ticket's pin"
        with self.assertRaises(ValueError):
            self.rows()
        self.contract["sections"][0]["text"] = self.pin
        self.row["quote"] = "unconfirmed"
        with self.assertRaises(ValueError):
            self.rows()

    def test_opt_in_and_receipt(self):
        items = self.rows()
        with patch.object(fixes, "gh", return_value="") as gh:
            self.assertFalse(fixes.deliver(self.source, items))
            self.assertEqual(gh.call_count, 1)
        comments = []
        dispatched = []
        def receiver(*args, stdin=None):
            if "workflow" in args:
                data = json.loads(stdin)
                dispatched.append(data)
                payload = json.loads(data["request"])
                digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                comments.append(json.dumps([f"<!-- design-fix {data['key']} {digest} {payload['pin']} -->\nEvidence",
                                            "https://example.org/8#comment"]))
                return "https://github.com/example/work/actions/runs/5"
            if "actions/workflows" in " ".join(args):
                return "active"
            return "\n".join(comments)
        with patch.object(fixes, "gh", side_effect=receiver):
            self.assertTrue(fixes.deliver(self.source, items))
            self.assertTrue(fixes.deliver(self.source, items))
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(dispatched[0]["issue"], "8")

    def test_accepted_run_without_comment_is_not_delivery(self):
        with patch.object(fixes, "gh", side_effect=["active", "", "run accepted", ""]), patch.object(fixes, "WAIT_SECONDS", 0):
            with self.assertRaisesRegex(ValueError, "no Epic comment"):
                fixes.deliver(self.source, self.rows())


if __name__ == "__main__":
    unittest.main()
