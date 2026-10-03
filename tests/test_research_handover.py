import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from strategy_lab.research.evidence import sha256
from strategy_lab.research.handover import inspect_archives, RESERVE


class HandoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, name="part.zip", members=None):
        p = self.root / name
        with zipfile.ZipFile(p, "x") as z:
            for member, contents in (members or [("corpus/input.csv", "id\nM0001\n")]):
                z.writestr(member, contents)
        return dict(name=name, bytes=p.stat().st_size, sha256=sha256(p))

    def test_valid_transport_does_not_claim_research_or_restoration(self):
        expected = self.archive()
        r = inspect_archives(self.root, [expected])
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["offsite_restore"], "NOT_VERIFIED")
        self.assertEqual(r["corpus_acceptance"], "NOT_VERIFIED")
        self.assertEqual(r["research_ids_completed"], 0)
        self.assertFalse((self.root / "corpus").exists())

    def test_missing_and_corruption_fail(self):
        expected = self.archive()
        p = self.root / expected["name"]
        p.write_bytes(p.read_bytes() + b"altered")
        self.assertEqual(inspect_archives(self.root, [expected])["status"], "BLOCKED")
        p.unlink()
        self.assertEqual(inspect_archives(self.root, [expected])["archives"][0]["reason"], "MISSING_OR_NONREGULAR_INPUT")

    def test_path_traversal_and_symlink_members_fail(self):
        for index, name in enumerate(["../escape", "/escape", "a\\escape"]):
            expected = self.archive(f"bad{index}.zip", [(name, "bad")])
            self.assertEqual(inspect_archives(self.root, [expected])["status"], "BLOCKED")
        link = zipfile.ZipInfo("link")
        link.external_attr = 0o120777 << 16
        expected = self.archive("link.zip", [(link, "target")])
        self.assertEqual(inspect_archives(self.root, [expected])["status"], "BLOCKED")

    def test_overlapping_parts_and_file_directory_conflict_fail(self):
        a, b = self.archive("a.zip"), self.archive("b.zip")
        self.assertEqual(inspect_archives(self.root, [a, b])["status"], "BLOCKED")
        c = self.archive("c.zip", [("corpus", "file")])
        self.assertEqual(inspect_archives(self.root, [a, c])["reason"], "FILE_DIRECTORY_CONFLICT")

    def test_expansion_limit_and_disk_floor(self):
        expected = self.archive()
        self.assertEqual(inspect_archives(self.root, [expected], max_expanded_bytes=1)["status"], "BLOCKED")
        with patch("strategy_lab.research.handover.shutil.disk_usage") as usage:
            usage.return_value.free = RESERVE - 1
            self.assertEqual(inspect_archives(self.root, [expected])["reason"], "DISK_RESERVE")

    def test_cli_never_overwrites_report(self):
        expected = self.root / "expected.json"
        expected.write_text(json.dumps([self.archive()]))
        report = self.root / "report.json"
        report.write_text("retained")
        r = subprocess.run([sys.executable, "-m", "strategy_lab.research.handover",
                            "--input-dir", str(self.root), "--expected", str(expected),
                            "--report", str(report)], capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(report.read_text(), "retained")


if __name__ == "__main__":
    unittest.main()
