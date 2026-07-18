from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _broad(handler: ast.ExceptHandler) -> bool:
    value = handler.type
    if isinstance(value, ast.Name):
        return value.id == "Exception"
    if isinstance(value, ast.Tuple):
        return any(isinstance(item, ast.Name) and item.id == "Exception" for item in value.elts)
    return False


def _callback(node: ast.AsyncFunctionDef) -> bool:
    return any("callback_query" in _dotted(decorator) for decorator in node.decorator_list)


def _ack(node: ast.Await) -> bool:
    name = _dotted(node.value)
    return name.endswith("callback.answer") or name.endswith("_safe_callback_answer") or name.endswith("safe_callback_answer")


def _actual() -> tuple[int, int, int, int, int]:
    broad: list[tuple[str, int]] = []
    callbacks: list[tuple[str, int, str]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
  if isinstance(node, ast.ExceptHandler) and _broad(node):
      broad.append((path.as_posix(), node.lineno))
  if isinstance(node, ast.AsyncFunctionDef) and _callback(node):
      awaits = sorted(
          (item for item in ast.walk(node) if isinstance(item, ast.Await)),
          key=lambda item: (item.lineno, item.col_offset),
      )
      ack = next((item for item in awaits if _ack(item)), None)
      pre = [item for item in awaits if ack is None or item.lineno < ack.lineno]
      callbacks.append((path.as_posix(), node.lineno, "missing_ack" if ack is None else ("late_ack" if pre else "early_ack")))
    risky = [item for item in callbacks if item[2] != "early_ack"]
    return len(broad), len({path for path, _ in broad}), len(callbacks), len(risky), len({path for path, _, _ in risky})


class P2StabilityInventoryTests(unittest.TestCase):
    def test_inventory_matches_current_ast(self) -> None:
        data = json.loads((ROOT / "docs/p2_stability_inventory.json").read_text(encoding="utf-8"))
        self.assertEqual(
  _actual(),
  (
      data["broad_exception_total"],
      data["broad_exception_files"],
      data["callback_total"],
      data["risky_callback_total"],
      data["risky_callback_files"],
  ),
        )

    def test_phase18_plan_is_not_stale(self) -> None:
        for name in ("development_status.md", "project_memory.md"):
  text = (ROOT / "docs" / name).read_text(encoding="utf-8")
  self.assertNotIn("Следующий срез: **18AN", text)
  self.assertNotIn("Фаза 18AN:", text)


if __name__ == "__main__":
    unittest.main()
