#!/usr/bin/env python3
from __future__ import annotations

import stat
import sys
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent
RUNTIME_SOURCES = (
    "codex_delegate.py",
    "codex_first_runner.py",
    "codex_first_safe_runner.py",
    "codex_provider_chain_runner.py",
    "codex_tier_runner.py",
    "compose.runtime.yaml",
)


class RuntimeSourceError(RuntimeError):
    pass


def validate_runtime_sources(root: Path = SOURCE_DIR) -> None:
    for name in RUNTIME_SOURCES:
        path = root / name
        if not path.is_file():
            raise RuntimeSourceError(f"Отсутствует runtime source: {path}")
        mode = stat.S_IMODE(path.stat().st_mode)
        if not mode & stat.S_IROTH:
            raise RuntimeSourceError(
                f"Bind-mounted runtime source недоступен container UID: {path} ({mode:04o})"
            )


def main() -> int:
    validate_runtime_sources()
    print("Hermes coder runtime source permissions: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeSourceError as error:
        print(f"Hermes coder runtime source guard failed: {error}", file=sys.stderr)
        raise SystemExit(2)
