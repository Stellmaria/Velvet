#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
_KEY = "HERMES_SANDBOX_LAUNCHER_TOKEN"


class TokenError(RuntimeError):
    pass


def parse_env(path: Path) -> tuple[list[str], dict[str, str]]:
    if not path.is_file() or path.is_symlink():
        raise TokenError(f"project env is missing or unsafe: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in values:
            raise TokenError(f"duplicate env key in {path}: {key}")
        values[key] = value.strip().strip('"').strip("'")
    return lines, values


def atomic_write(path: Path, body: str, *, uid: int, gid: int, mode: int) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(temp, uid, gid)
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def ensure_project_token(path: Path) -> str:
    lines, values = parse_env(path)
    current = values.get(_KEY, "")
    if current and not _TOKEN.fullmatch(current):
        raise TokenError(f"invalid existing {_KEY} in {path}")
    token = current or secrets.token_urlsafe(32)
    if not _TOKEN.fullmatch(token):
        raise TokenError("generated launcher token has an unexpected format")
    rendered: list[str] = []
    replaced = False
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key == _KEY:
                rendered.append(f"{_KEY}={token}")
                replaced = True
                continue
        rendered.append(raw)
    if not replaced:
        rendered.append(f"{_KEY}={token}")
    stat_result = path.stat()
    atomic_write(
        path,
        "\n".join(rendered) + "\n",
        uid=stat_result.st_uid,
        gid=stat_result.st_gid,
        mode=stat_result.st_mode & 0o777,
    )
    return token


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: ensure_launcher_tokens.py VELVET_ENV MAX_ENV LAUNCHER_SECRETS_ENV"
        )
    velvet_path = Path(sys.argv[1])
    max_path = Path(sys.argv[2])
    secrets_path = Path(sys.argv[3])
    velvet = ensure_project_token(velvet_path)
    maximum = ensure_project_token(max_path)
    if velvet == maximum:
        raise TokenError("Velvet and Max launcher tokens must be distinct")
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"HERMES_SANDBOX_VELVET_TOKEN={velvet}\n"
        f"HERMES_SANDBOX_MAX_TOKEN={maximum}\n"
    )
    atomic_write(secrets_path, body, uid=0, gid=0, mode=0o600)
    print("Hermes launcher project credentials: ready and distinct")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TokenError as error:
        print(f"Hermes launcher token setup failed: {error}", file=sys.stderr)
        raise SystemExit(2)
