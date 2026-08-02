from __future__ import annotations

import argparse
import json
from pathlib import Path

from velvet_bot.domains.telegram_storage.encryption import (
    decrypt_file,
    inspect_encrypted_file,
    keyring_from_env,
    reencrypt_file,
    sha256_file,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect, restore or re-encrypt Velvet encrypted backups."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("paths", nargs="+", type=Path)

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("paths", nargs="+", type=Path)

    decrypt_parser = subparsers.add_parser("decrypt")
    decrypt_parser.add_argument("source", type=Path)
    decrypt_parser.add_argument("destination", type=Path)

    reencrypt_parser = subparsers.add_parser("reencrypt")
    reencrypt_parser.add_argument("source", type=Path)
    reencrypt_parser.add_argument("destination", type=Path)
    return parser


def _inspect(path: Path) -> dict[str, object]:
    header = inspect_encrypted_file(path)
    return {
        "path": str(path),
        "format_version": header.version,
        "key_id": header.key_id,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def main() -> int:
    args = _parser().parse_args()
    if args.command == "inspect":
        print(json.dumps([_inspect(path) for path in args.paths], indent=2))
        return 0

    keyring = keyring_from_env()
    if args.command == "check":
        failed = False
        rows: list[dict[str, object]] = []
        for path in args.paths:
            data = _inspect(path)
            key_id = data["key_id"]
            available = keyring.has_key(str(key_id) if key_id is not None else None)
            data["key_available"] = available
            rows.append(data)
            failed = failed or not available
        print(json.dumps(rows, indent=2))
        return 2 if failed else 0

    if args.command == "decrypt":
        decrypt_file(args.source, args.destination, keyring)
        print(
            json.dumps(
                {
                    "source": str(args.source),
                    "destination": str(args.destination),
                    "plaintext_sha256": sha256_file(args.destination),
                },
                indent=2,
            )
        )
        return 0

    if args.command == "reencrypt":
        if args.source.resolve() == args.destination.resolve():
            raise SystemExit("Re-encryption requires a separate destination path.")
        reencrypt_file(args.source, args.destination, keyring)
        header = inspect_encrypted_file(args.destination)
        print(
            json.dumps(
                {
                    "source_retained": str(args.source),
                    "destination": str(args.destination),
                    "format_version": header.version,
                    "key_id": header.key_id,
                    "encrypted_sha256": sha256_file(args.destination),
                },
                indent=2,
            )
        )
        return 0

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
