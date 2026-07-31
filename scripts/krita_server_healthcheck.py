from __future__ import annotations

import os
import sys
from pathlib import Path


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _krita_is_running() -> bool:
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ")
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        if b"/usr/bin/krita" in command or command.strip().startswith(b"krita "):
            return True
    return False


def main() -> int:
    if not _krita_is_running():
        return _fail("Krita process is not running")

    home = Path(os.getenv("HOME", "/home/velvet"))
    config = home / ".config" / "kritarc"
    desktop = home / ".local" / "share" / "krita" / "pykrita" / "velvet_logo.desktop"
    module = home / ".local" / "share" / "krita" / "pykrita" / "velvet_logo" / "__init__.py"

    try:
        config_text = config.read_text(encoding="utf-8")
    except OSError as error:
        return _fail(f"Krita config is unavailable: {error}")
    if "enable_velvet_logo=true" not in config_text.replace(" ", "").casefold():
        return _fail("Velvet Krita plugin is not enabled")
    if not desktop.is_file() or not module.is_file():
        return _fail("Velvet Krita plugin files are missing")

    bridge_dir = Path(os.getenv("KRITA_BRIDGE_DIR", "/app/runtime/krita"))
    required = ("requests", "responses", "outputs", "sources", "previews", "assets")
    for name in required:
        path = bridge_dir / name
        if not path.is_dir():
            return _fail(f"Krita bridge directory is missing: {path}")

    probe = bridge_dir / ".krita-healthcheck"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        return _fail(f"Krita bridge is not writable: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
