from __future__ import annotations

import ast
import json
import re
import unittest
from collections import Counter, defaultdict
from pathlib import Path


ROOTS = (Path("velvet_bot"), Path("velvet_supervisor"))


def _python_files() -> list[Path]:
    return sorted(path for root in ROOTS for path in root.rglob("*.py"))


def _module_name(path: Path) -> str:
    return ".".join(path.with_suffix("").parts)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}".strip(".")
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


class ProjectArchitectureProbe(unittest.TestCase):
    def test_emit_full_architecture_report(self) -> None:
        files = _python_files()
        modules = {_module_name(path): path for path in files}
        imports: dict[str, set[str]] = defaultdict(set)
        callback_prefixes: dict[str, list[str]] = defaultdict(list)
        handler_imports: list[str] = []
        catch_all_routes: list[str] = []
        broad_exceptions: list[str] = []
        private_db_access: list[str] = []
        monkeypatches: list[str] = []
        raw_callbacks: list[str] = []
        model_copies: list[str] = []
        long_modules: list[tuple[int, str]] = []

        for path in files:
            source = path.read_text(encoding="utf-8")
            line_count = len(source.splitlines())
            if line_count >= 500:
                long_modules.append((line_count, str(path)))
            tree = ast.parse(source, filename=str(path))
            module = _module_name(path)

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imports[module].add(node.module)
                    if (
                        module.startswith("velvet_bot.handlers.")
                        and node.module.startswith("velvet_bot.handlers.")
                        and node.module != module
                    ):
                        handler_imports.append(
                            f"{path}:{node.lineno} -> {node.module}"
                        )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports[module].add(alias.name)

                if isinstance(node, ast.ClassDef):
                    if any(_call_name(base).endswith("CallbackData") for base in node.bases):
                        for keyword in node.keywords:
                            if (
                                keyword.arg == "prefix"
                                and isinstance(keyword.value, ast.Constant)
                                and isinstance(keyword.value.value, str)
                            ):
                                callback_prefixes[keyword.value.value].append(
                                    f"{module}.{node.name}"
                                )

                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for decorator in node.decorator_list:
                        if not isinstance(decorator, ast.Call):
                            continue
                        name = _call_name(decorator.func)
                        if name.endswith("router.message") and not decorator.args and not decorator.keywords:
                            catch_all_routes.append(f"{path}:{node.lineno} {node.name}")

                if isinstance(node, ast.ExceptHandler):
                    if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                        broad_exceptions.append(f"{path}:{node.lineno}")

                if isinstance(node, ast.Attribute):
                    if node.attr in {"_require_pool", "_pool", "_connection", "_settings"}:
                        private_db_access.append(f"{path}:{node.lineno} .{node.attr}")

                if isinstance(node, ast.Call) and _call_name(node.func) == "setattr":
                    monkeypatches.append(f"{path}:{node.lineno} setattr")

                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                            if target.value.id.endswith(("module", "ui", "center", "directory")):
                                monkeypatches.append(
                                    f"{path}:{node.lineno} {target.value.id}.{target.attr}"
                                )

                if isinstance(node, ast.Call) and _call_name(node.func).endswith("InlineKeyboardButton"):
                    for keyword in node.keywords:
                        if (
                            keyword.arg == "callback_data"
                            and isinstance(keyword.value, ast.Constant)
                            and isinstance(keyword.value.value, str)
                            and ":" in keyword.value.value
                        ):
                            raw_callbacks.append(
                                f"{path}:{node.lineno} {keyword.value.value}"
                            )

                if isinstance(node, ast.Call) and _call_name(node.func).endswith("model_copy"):
                    model_copies.append(f"{path}:{node.lineno}")

        duplicate_prefixes = {
            prefix: owners
            for prefix, owners in callback_prefixes.items()
            if len(owners) > 1
        }

        migration_numbers: dict[str, list[str]] = defaultdict(list)
        for path in sorted(Path("migrations").glob("*.sql")):
            match = re.match(r"(\d+)_", path.name)
            if match:
                migration_numbers[match.group(1)].append(path.name)
        duplicate_migrations = {
            number: names
            for number, names in migration_numbers.items()
            if len(names) > 1
        }

        cycles: set[tuple[str, str]] = set()
        for module, targets in imports.items():
            for target in targets:
                if target in modules and module in imports.get(target, set()):
                    cycles.add(tuple(sorted((module, target))))

        report = {
            "python_files": len(files),
            "total_lines": sum(len(path.read_text(encoding="utf-8").splitlines()) for path in files),
            "long_modules_ge_500": sorted(long_modules, reverse=True),
            "duplicate_callback_prefixes": duplicate_prefixes,
            "duplicate_migration_numbers": duplicate_migrations,
            "direct_handler_imports": sorted(set(handler_imports)),
            "catch_all_message_routes": sorted(set(catch_all_routes)),
            "broad_exception_handlers_count": len(broad_exceptions),
            "broad_exception_samples": sorted(set(broad_exceptions))[:80],
            "private_internal_access_count": len(private_db_access),
            "private_internal_access_samples": sorted(set(private_db_access))[:80],
            "monkeypatch_sites": sorted(set(monkeypatches)),
            "raw_callback_literals": sorted(set(raw_callbacks)),
            "message_model_copy_sites": sorted(set(model_copies)),
            "direct_two_module_cycles": sorted(cycles),
        }
        self.fail("PROJECT_AUDIT_REPORT\n" + json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    unittest.main()
