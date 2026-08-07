#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

_MEDIA_KEY = "BYESU_MEDIA_GEN_API_KEY"
_FALLBACK_KEY = "CODEX_IMAGE_BYESU_FALLBACK_ENABLED"
_ALLOWED_KEYS = (
    _MEDIA_KEY,
    _FALLBACK_KEY,
    "CODEX_IMAGE_BYESU_BASE_URL",
    "CODEX_IMAGE_BYESU_TIMEOUT_SECONDS",
)
_BOOLEAN_KEYS = {_FALLBACK_KEY}
_INTEGER_RANGES = {
    "CODEX_IMAGE_BYESU_TIMEOUT_SECONDS": (60, 1_800),
}
_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "да"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "нет"})


class ImageRuntimeEnvError(RuntimeError):
    pass


def parse_env(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise ImageRuntimeEnvError(f"operator env отсутствует или небезопасен: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in _ALLOWED_KEYS:
            continue
        if key in values:
            raise ImageRuntimeEnvError(f"duplicate operator env key: {key}")
        values[key] = value.strip().strip('"').strip("'")
    return values


def normalize_value(name: str, value: str) -> str:
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ImageRuntimeEnvError(f"{name} содержит недопустимый символ")
    if name == _MEDIA_KEY:
        normalized = value.strip()
        if len(normalized) < 20:
            raise ImageRuntimeEnvError(f"{_MEDIA_KEY} отсутствует или слишком короткий")
        return normalized
    if name in _BOOLEAN_KEYS:
        normalized = value.strip().casefold()
        if normalized in _TRUE_VALUES:
            return "true"
        if normalized in _FALSE_VALUES:
            return "false"
        raise ImageRuntimeEnvError(f"{name} должен быть boolean")
    if name in _INTEGER_RANGES:
        try:
            parsed = int(value)
        except ValueError as error:
            raise ImageRuntimeEnvError(f"{name} должен быть целым числом") from error
        minimum, maximum = _INTEGER_RANGES[name]
        if not minimum <= parsed <= maximum:
            raise ImageRuntimeEnvError(
                f"{name} должен быть в диапазоне {minimum}..{maximum}"
            )
        return str(parsed)
    if name == "CODEX_IMAGE_BYESU_BASE_URL":
        parsed = urlparse(value.strip())
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ImageRuntimeEnvError(
                "CODEX_IMAGE_BYESU_BASE_URL должен быть безопасным HTTPS URL"
            )
        return value.strip().rstrip("/")
    raise ImageRuntimeEnvError(f"неразрешённый image runtime key: {name}")


def build_environment(
    source_path: Path,
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = parse_env(source_path)
    environment = dict(base_environment or {})
    normalized: dict[str, str] = {}
    for name in _ALLOWED_KEYS:
        if name in source and source[name].strip():
            normalized[name] = normalize_value(name, source[name])
    if normalized.get(_FALLBACK_KEY) == "true" and _MEDIA_KEY not in normalized:
        raise ImageRuntimeEnvError(
            f"{_MEDIA_KEY} обязателен при включённом Byesu image fallback"
        )
    environment.update(normalized)
    return environment


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: compose_image_runtime_env.py COMMAND [ARG ...]"
        )
    source_path = Path(
        os.environ.get("HERMES_OPERATOR_ENV", "/srv/velvet/.env.hermes")
    )
    environment = build_environment(source_path, os.environ)
    os.execvpe(sys.argv[1], sys.argv[1:], environment)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImageRuntimeEnvError as error:
        print(f"Hermes image runtime env projection failed: {error}", file=sys.stderr)
        raise SystemExit(2)
