from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def load_patch_module() -> ModuleType:
    path = ROOT / "tools/temp_apply_network_failure_fixes.py"
    spec = importlib.util.spec_from_file_location("temp_apply_network_failure_fixes", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load temporary patch module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dedent_one(value: str) -> str:
    return "\n".join(
        line[1:] if line.startswith(" ") else line
        for line in value.split("\n")
    )


def compatible_replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    source = target.read_text(encoding="utf-8")
    candidates = [(old, new)]
    if "logger_name = 'velvet_bot.presentation.telegram.router'" in old:
        candidates.extend(
            [
                (
                    old.replace("           OR (", "          OR ("),
                    new.replace("           OR (", "          OR ("),
                ),
                (_dedent_one(old), _dedent_one(new)),
            ]
        )
    for expected, replacement in candidates:
        if expected in source:
            target.write_text(source.replace(expected, replacement, 1), encoding="utf-8")
            return
    raise RuntimeError(f"Expected block not found in {path}: {old[:160]!r}")


def main() -> None:
    patch = load_patch_module()
    patch.replace = compatible_replace
    patch.patch_runtime_stability()
    patch.patch_codex()
    patch.patch_dependencies()
    patch.patch_git_ops()
    patch.patch_bootstrap()
    patch.patch_tests()
    (ROOT / "tools/temp_patch_error.txt").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
