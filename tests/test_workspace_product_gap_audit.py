from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_workspace_product.py"
MANIFEST = ROOT / "docs" / "audits" / "workspace_product_gap_audit.json"
REPORT = ROOT / "docs" / "audits" / "workspace_product_gap_audit.md"


class WorkspaceProductGapAuditTests(unittest.TestCase):
    def test_generated_audit_is_current_and_valid(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
        self.assertEqual(
            0,
            completed.returncode,
            completed.stdout + "\n" + completed.stderr,
        )

    def test_every_canonical_section_has_one_or_more_rows(self) -> None:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        sections = {
            int(item["section"])
            for item in data["requirements"]
            if item["section"] is not None
        }
        self.assertEqual(set(range(1, 17)), sections)

    def test_non_verified_rows_have_bounded_follow_up(self) -> None:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        follow_up = {
            issue
            for item in data["requirements"]
            if item["status"] != "verified"
            for issue in item["follow_up"]
        }
        self.assertTrue({410, 417, 426, 561, 562, 563}.issubset(follow_up))
        self.assertNotIn(430, follow_up)

    def test_report_distinguishes_code_extensions_from_live_acceptance(self) -> None:
        report = REPORT.read_text(encoding="utf-8")
        self.assertIn("#561", report)
        self.assertIn("#562", report)
        self.assertIn("#563", report)
        self.assertIn("#426", report)
        self.assertIn("не закрываются зелёным CI автоматически", report)


if __name__ == "__main__":
    unittest.main()
