from __future__ import annotations

from pathlib import Path

import tools.temp_apply_network_failure_fixes as patch

ROOT = Path(__file__).resolve().parents[1]


def compatible_replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    source = target.read_text(encoding="utf-8")
    candidates = [(old, new)]
    if "logger_name = 'velvet_bot.presentation.telegram.router'" in old:
        candidates.append(
            (
                old.replace("           OR (", "          OR ("),
                new.replace("           OR (", "          OR ("),
            )
        )
    for expected, replacement in candidates:
        if expected in source:
            target.write_text(source.replace(expected, replacement, 1), encoding="utf-8")
            return
    raise RuntimeError(f"Expected block not found in {path}: {old[:160]!r}")


def main() -> None:
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
