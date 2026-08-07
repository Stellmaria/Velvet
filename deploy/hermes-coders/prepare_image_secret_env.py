#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "да"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "нет"})
_MEDIA_KEY = "BYESU_MEDIA_GEN_API_KEY"
_FALLBACK_KEY = "CODEX_IMAGE_BYESU_FALLBACK_ENABLED"


class ImageSecretEnvError(RuntimeError):
    pass


def parse_operator_env(path: Path) -> dict[str, str]:
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
        if key not in {_MEDIA_KEY, _FALLBACK_KEY}:
            continue
        if key in values:
            raise ImageSecretEnvError(f"duplicate operator env key: {key}")
        values[key] = value.strip().strip('"').strip("'")
    return values


def fallback_enabled(values: dict[str, str]) -> bool:
    raw = values.get(_FALLBACK_KEY, "false").strip().casefold()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise ImageSecretEnvError(f"{_FALLBACK_KEY} должен быть boolean")


def validated_media_key(values: dict[str, str]) -> str:
    key = values.get(_MEDIA_KEY, "").strip()
    if key and len(key) < 20:
        raise ImageSecretEnvError(f"{_MEDIA_KEY} слишком короткий")
    if fallback_enabled(values) and not key:
        raise ImageSecretEnvError(
            f"{_MEDIA_KEY} обязателен при включённом Byesu image fallback"
        )
    if any(marker in key for marker in ("\n", "\r", "\x00")):
        raise ImageSecretEnvError(f"{_MEDIA_KEY} содержит недопустимый символ")
    return key


def rewrite_project_env(body: str, media_key: str) -> str:
    output: list[str] = []
    replaced = False
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        key = ""
        if "=" in stripped and not stripped.startswith("#"):
            candidate = stripped[7:].lstrip() if stripped.startswith("export ") else stripped
            key = candidate.split("=", 1)[0].strip()
        if key == _MEDIA_KEY:
            if not replaced and media_key:
                output.append(f"{_MEDIA_KEY}={media_key}")
                replaced = True
            continue
        output.append(raw_line)
    if media_key and not replaced:
        if output and output[-1].strip():
            output.append("")
        output.append(f"{_MEDIA_KEY}={media_key}")
    return "\n".join(output).rstrip() + "\n"


def write_secret_env(source: Path, target: Path) -> None:
    media_key = validated_media_key(parse_operator_env(source))
    if not target.is_file() or target.is_symlink():
        raise ImageSecretEnvError(f"Velvet project secret env отсутствует или небезопасен: {target}")
    body = rewrite_project_env(target.read_text(encoding="utf-8"), media_key)
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
            "/srv/hermes-coders/secrets/velvet.env",
        )
    )
    write_secret_env(source, target)
    print("Velvet Media Gen credential synchronized without printing values.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ImageSecretEnvError, OSError) as error:
        print(f"Hermes image secret env preparation failed: {error}", file=os.sys.stderr)
        raise SystemExit(2)
