from __future__ import annotations

import base64
import json
import unittest

from scripts.inventory_repository_layout import build_inventory, render_markdown


def _encoded(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


_inventory = build_inventory(label="p3e-repository-layout-complete")
print("KRITA_P3E_JSON_B64=" + _encoded(json.dumps(_inventory, ensure_ascii=False, indent=2) + "\n"))
print("KRITA_P3E_MD_B64=" + _encoded(render_markdown(_inventory)))


class KritaInventoryDiagnosticTests(unittest.TestCase):
    def test_inventory_was_rendered(self) -> None:
        self.assertEqual("p3e-repository-layout-complete", _inventory["generated_from"])


if __name__ == "__main__":
    unittest.main()
