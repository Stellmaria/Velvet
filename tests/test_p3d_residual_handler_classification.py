from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDLERS = ROOT / "velvet_bot/handlers"
MODULE_ALIAS_MARKER = "P3_COMPAT_MODULE_ALIAS"


def residual_handler_implementations() -> set[str]:
    return {
        path.name
        for path in HANDLERS.glob("*.py")
        if path.name != "__init__.py"
        and MODULE_ALIAS_MARKER not in path.read_text(encoding="utf-8")
    }


class P3DResidualHandlerClassificationTests(unittest.TestCase):
    def test_residual_implementations_are_explicitly_classified(self) -> None:
        # Discovery sentinel. The first CI run prints the exact residual set; the
        # next commit replaces this sentinel with the reviewed classification.
        self.assertEqual({"watermark.py"}, residual_handler_implementations())


if __name__ == "__main__":
    unittest.main()
