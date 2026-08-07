#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "да"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "нет"})


class ImageSecretEnvError(RuntimeError):
    pass


def parse_env(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise ImageSecretEnvError(f"operator env отсутствует или небезопасен: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in {"BYESU_MEDIA_GEN_API_KEY", "CODEX_IMAGE_BYESU_FALLBACK_ENABLED"}:
            continue
        if key in values:
            raise ImageSecretEnvError(f"duplicate operator env key: {key}")
        values[key] = value.strip().strip('"').strip("'")
    return values


def fallback_enabled(values: dict[str, str]) -> bool:
    raw = values.get("CODEX_IMAGE_BYESU_FALLBACK_ENABLED", "false").strip().casefold()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise ImageSecretEnvError(
        "CODEX_IMAGE_BYESU_FALLBACK_ENABLED должен быть boolean"
    )


def render(values: dict[str, str]) -> str:
    key = values.get("BYESU_MEDIA_GEN_API_KEY", "").strip()
    if key and len(key) < 20:
        raise ImageSecretEnvError("BYESU_MEDIA_GEN_API_KEY слишком короткий")
    if fallback_enabled(values) and not key:
        raise ImageSecretEnvError(
            "BYESU_MEDIA_GEN_API_KEY обязателен при включённом Byesu image fallback"
        )
    if not key:
        return ""
    if any(marker in key for marker in ("\n", "\r", "\x00")):
        raise ImageSecretEnvError("BYESU_MEDIA_GEN_API_KEY содержит недопустимый символ")
    return f"BYESU_MEDIA_GEN_API_KEY={key}\n"


def write_secret_env(source: Path, target: Path) -> None:
    body = render(parse_env(source))
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists() and target.is_symlink():
        raise ImageSecretEnvError(f"target secret env является symlink: {target}")
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.",
        dir=target.parent,
        text=True,
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, target)
        os.chmod(target, 0o600)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    source = Path(os.environ.get("HERMES_OPERATOR_ENV", "/srv/velvet/.env.hermes"))
    target = Path(
        os.environ.get(
            "HERMES_IMAGE_SECRET_ENV",
            "/srv/hermes-coders/secrets/velvet-media.env",
        )
    )
    write_secret_env(source, target)
    print("Velvet Media Gen secret projection prepared without printing values.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ImageSecretEnvError, OSError) as error:
        print(f"Hermes image secret env preparation failed: {error}", file=os.sys.stderr)
        raise SystemExit(2)
