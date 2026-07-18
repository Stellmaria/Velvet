from __future__ import annotations

import ast
import inspect
import json
import unittest
from pathlib import Path

import velvet_bot.handlers.multi_story_kr as multi_story

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


def _broad(node: ast.ExceptHandler) -> bool:
    value = node.type
    if isinstance(value, ast.Name):
        return value.id == "Exception"
    if isinstance(value, ast.Tuple):
        return any(
            isinstance(item, ast.Name) and item.id == "Exception"
            for item in value.elts
        )
    return False


def _callback(node: ast.AsyncFunctionDef) -> bool:
    return any("callback_query" in _dotted(item) for item in node.decorator_list)


def _ack(node: ast.Await) -> bool:
    name = _dotted(node.value)
    leaf = name.rsplit(".", 1)[-1].casefold()
    return name.endswith("callback.answer") or (
        "callback" in leaf and ("answer" in leaf or "acknowledge" in leaf)
    )


def _passes_callback(node: ast.Await) -> bool:
    if not isinstance(node.value, ast.Call):
        return False
    args = [*node.value.args, *(item.value for item in node.value.keywords)]
    return any(isinstance(item, ast.Name) and item.id == "callback" for item in args)


def _actual() -> tuple[int, int, int, int, int, int, int]:
    broad: list[tuple[str, int]] = []
    callbacks: list[tuple[str, int, str]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _broad(node):
                broad.append((path.as_posix(), node.lineno))
            if isinstance(node, ast.AsyncFunctionDef) and _callback(node):
                awaits = sorted(
                    (
                        item
                        for item in ast.walk(node)
                        if isinstance(item, ast.Await)
                    ),
                    key=lambda item: (item.lineno, item.col_offset),
                )
                ack = next((item for item in awaits if _ack(item)), None)
                pre = [
                    item
                    for item in awaits
                    if ack is None or item.lineno < ack.lineno
                ]
                delegated = (
                    ack is None
                    and len(awaits) == 1
                    and _passes_callback(awaits[0])
                )
                if delegated:
                    risk = "delegated"
                elif ack is None:
                    risk = "missing_ack"
                elif not pre:
                    risk = "early_ack"
                elif len(pre) == 1:
                    risk = "guarded_ack"
                else:
                    risk = "late_ack"
                callbacks.append((path.as_posix(), node.lineno, risk))
    risky = [
        item for item in callbacks if item[2] in {"missing_ack", "late_ack"}
    ]
    guarded = [item for item in callbacks if item[2] == "guarded_ack"]
    delegated = [item for item in callbacks if item[2] == "delegated"]
    return (
        len(broad),
        len({path for path, _ in broad}),
        len(callbacks),
        len(risky),
        len({path for path, _, _ in risky}),
        len(guarded),
        len(delegated),
    )


class P2StabilityInventoryTests(unittest.TestCase):
    def test_inventory_matches_current_ast(self) -> None:
        data = json.loads(
            (ROOT / "docs/p2_stability_inventory.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            _actual(),
            (
                data["broad_exception_total"],
                data["broad_exception_files"],
                data["callback_total"],
                data["risky_callback_total"],
                data["risky_callback_files"],
                data["guarded_callback_total"],
                data["delegated_callback_total"],
            ),
        )

    def test_multi_story_ack_precedes_heavy_render(self) -> None:
        for function, renderer in (
            (multi_story.handle_admin_open_multi_story, "_render_admin_picker"),
            (multi_story.handle_public_open_multi_story, "_render_public_picker"),
        ):
            source = inspect.getsource(function)
            self.assertLess(
                source.index("await callback.answer()"),
                source.index(f"await {renderer}("),
            )
            self.assertLess(
                source.index("await get_character_directory_item("),
                source.index("await callback.answer()"),
            )

    def test_phase18_plan_is_not_stale(self) -> None:
        for name in ("development_status.md", "project_memory.md"):
            text = (ROOT / "docs" / name).read_text(encoding="utf-8")
            self.assertNotIn("Следующий срез: **18AN", text)
            self.assertNotIn("Фаза 18AN:", text)


if __name__ == "__main__":
    unittest.main()
