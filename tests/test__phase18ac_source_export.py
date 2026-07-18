from __future__ import annotations

import base64
import unittest
from pathlib import Path


class Phase18ACSourceExportTests(unittest.TestCase):
    def test_export_modified_telegram_import_source(self) -> None:
        path = Path(__file__).resolve().parents[1] / "velvet_bot" / "telegram_export_import.py"
        source = path.read_text(encoding="utf-8")
        old = "database._require_pool().acquire()"
        new = "database.acquire()"
        self.assertEqual(4, source.count(old))
        modified = source.replace(old, new)
        self.assertEqual(0, modified.count(old))
        self.assertEqual(4, modified.count(new))
        encoded = base64.b64encode(modified.encode("utf-8")).decode("ascii")
        print("PHASE18AC_SOURCE_BEGIN")
        print(encoded)
        print("PHASE18AC_SOURCE_END")


if __name__ == "__main__":
    unittest.main()
