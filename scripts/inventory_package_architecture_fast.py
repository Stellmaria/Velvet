from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "inventory_package_architecture.py"

_owner_tree: ast.Module | None = None
_owner_ranges: tuple[tuple[int, int, int, str], ...] = ()
_owner_lines: dict[int, str] = {}


def _load_target() -> ModuleType:
    module_name = "_velvet_package_architecture_inventory"
    spec = importlib.util.spec_from_file_location(module_name, TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load package inventory script: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _fast_owner(tree: ast.Module, line: int) -> str:
    """Return the narrowest function/class owner without re-walking the AST.

    The original inventory helper walks the complete module AST for every call,
    string literal and foreign assignment.  This adapter keeps the exact
    narrowest-span semantics while indexing each module only once.
    """

    global _owner_tree, _owner_ranges, _owner_lines

    if tree is not _owner_tree:
        ranges: list[tuple[int, int, int, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            start = int(node.lineno)
            end = int(getattr(node, "end_lineno", start) or start)
            ranges.append((start, end, end - start, node.name))
        _owner_tree = tree
        _owner_ranges = tuple(ranges)
        _owner_lines = {}

    cached = _owner_lines.get(line)
    if cached is not None:
        return cached

    owner = "<module>"
    span = 10**9
    for start, end, candidate_span, candidate_owner in _owner_ranges:
        if start <= line <= end and candidate_span < span:
            owner = candidate_owner
            span = candidate_span
    _owner_lines[line] = owner
    return owner


def main() -> int:
    module = _load_target()
    module._owner = _fast_owner
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())
