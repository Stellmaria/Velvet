from __future__ import annotations

import argparse
from pathlib import Path

from velvet_bot.domains.telegram_storage.models import (
    StorageKind,
    TelegramStorageSettings,
)

_STORAGE_KINDS: tuple[StorageKind, ...] = (
    "watermarks",
    "backups",
    "diagnostics",
    "exports",
    "codex",
    "releases",
    "rework",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Telegram Storage deletion roots and dry-run paths."
    )
    parser.add_argument("--kind", choices=_STORAGE_KINDS)
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Absolute path to include in a deletion dry-run. Repeat as needed.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = TelegramStorageSettings.from_env()
    if args.path and not args.kind:
        raise SystemExit("--path requires --kind")

    print("Telegram Storage deletion policies:")
    for kind in _STORAGE_KINDS:
        policy = settings.deletion_policy_for(kind)
        roots = ", ".join(str(path) for path in policy.allowed_roots)
        print(
            f"- {kind}: roots=[{roots}] "
            f"recursive={policy.allow_recursive_directories}"
        )

    if not args.path:
        print("Telegram Storage deletion preflight: OK")
        return 0

    assert args.kind is not None
    policy = settings.deletion_policy_for(args.kind)
    result = policy.plan(tuple(Path(value) for value in args.path))
    for item in result.planned:
        print(
            f"[PLAN] kind={item.kind} bytes={item.size_bytes} "
            f"root={item.root} path={item.path}"
        )
    for issue in result.issues:
        print(
            f"[REFUSE] stage={issue.stage} code={issue.code} path={issue.path}"
        )
    print(
        "Telegram Storage deletion dry-run: "
        f"planned={len(result.planned)} issues={len(result.issues)}"
    )
    return 0 if result.complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
