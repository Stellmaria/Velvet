#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMAGE_KEYS = (
    "HERMES_SANDBOX_VELVET_IMAGE",
    "HERMES_SANDBOX_MAX_IMAGE",
)
_PATH_KEYS = (
    "HERMES_SANDBOX_INSTALL_DIR",
    "HERMES_SANDBOX_PENDING_INSTALL_DIR",
)


def parse_lines(path: Path) -> tuple[list[str], dict[str, str]]:
    lines: list[str] = []
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            lines.append(raw)
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in values:
            raise RuntimeError(f"duplicate launcher env key: {key}")
        values[key] = value.strip()
        lines.append(raw)
    return lines, values


def validate_activation_paths(values: dict[str, str]) -> tuple[Path, Path]:
    missing = [key for key in _PATH_KEYS if not values.get(key)]
    if missing:
        raise RuntimeError("launcher.env misses activation keys: " + ", ".join(missing))
    current = Path(values[_PATH_KEYS[0]])
    pending = Path(values[_PATH_KEYS[1]])
    if not current.is_absolute() or current.name != "current":
        raise RuntimeError("launcher current path is not an absolute current symlink")
    releases = current.parent / "releases"
    if not pending.is_absolute() or pending.parent != releases:
        raise RuntimeError("pending launcher release is outside the fixed releases root")
    if pending.is_symlink() or not pending.is_dir():
        raise RuntimeError("pending launcher release is missing or unsafe")
    for name in (
        "launcher.py",
        "launcher_contract.py",
        "launcher_runtime.py",
        "sandbox_entrypoint.py",
    ):
        candidate = pending / name
        if candidate.is_symlink() or not candidate.is_file():
            raise RuntimeError(f"pending launcher release misses safe file: {name}")
    return current, pending


def restore_current(current: Path, previous: Path | None) -> None:
    recovery = current.parent / f".{current.name}.recovery.{os.getpid()}"
    recovery.unlink(missing_ok=True)
    if previous is None:
        current.unlink(missing_ok=True)
        return
    recovery.symlink_to(previous)
    os.replace(recovery, current)


def update(path: Path, velvet_image: str, max_image: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("launcher.env is missing or unsafe")
    replacements = dict(zip(_IMAGE_KEYS, (velvet_image, max_image), strict=True))
    for key, value in replacements.items():
        if not _IMAGE_ID.fullmatch(value):
            raise RuntimeError(f"{key} is not an immutable Docker image ID")
    stat_result = path.stat()
    lines, values = parse_lines(path)
    missing = [key for key in _IMAGE_KEYS if key not in values]
    if missing:
        raise RuntimeError("launcher.env misses image keys: " + ", ".join(missing))
    current, pending = validate_activation_paths(values)

    rendered: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in replacements:
                rendered.append(f"{key}={replacements[key]}")
                seen.add(key)
                continue
        rendered.append(raw)
    if seen != set(_IMAGE_KEYS):
        raise RuntimeError("launcher image keys were not replaced exactly once")

    previous = current.resolve() if current.is_symlink() else None
    fd, temp_name = tempfile.mkstemp(prefix=".launcher.env.", dir=path.parent, text=True)
    temp = Path(temp_name)
    link_temp = current.parent / f".{current.name}.{os.getpid()}"
    switched = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(rendered) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(temp, stat_result.st_uid, stat_result.st_gid)
        os.chmod(temp, stat_result.st_mode & 0o777)
        link_temp.unlink(missing_ok=True)
        link_temp.symlink_to(pending)
        os.replace(link_temp, current)
        switched = True
        try:
            os.replace(temp, path)
        except Exception:
            restore_current(current, previous)
            switched = False
            raise
    finally:
        temp.unlink(missing_ok=True)
        link_temp.unlink(missing_ok=True)
        if switched and current.resolve() != pending.resolve():
            restore_current(current, previous)
            raise RuntimeError("launcher current symlink verification failed")


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: pin_launcher_images.py ENV VELVET_IMAGE MAX_IMAGE")
    update(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
    print("Hermes launcher image IDs recorded and exact release activated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
