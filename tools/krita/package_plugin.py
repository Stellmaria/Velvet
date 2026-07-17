from __future__ import annotations

from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "Velvet_Anatomy_Krita_Plugin_bridge.zip"

with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.write(ROOT / "velvet_logo.desktop", "velvet_logo.desktop")
    for path in sorted((ROOT / "velvet_logo").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            archive.write(path, path.relative_to(ROOT).as_posix())

print(OUTPUT)
