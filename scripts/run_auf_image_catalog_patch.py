from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHER_PATH = ROOT / "scripts" / "patch_auf_image_catalog.py"

spec = importlib.util.spec_from_file_location("auf_image_catalog_patcher", PATCHER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load AUF image catalog patcher")
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

_original_replace_once = patcher.replace_once


def _replace_once(path: str, old: str, new: str) -> None:
    if (
        path == "velvet_bot/app/auf_photo_model_modes.py"
        and old == "        for resolution in model.supported_photo_resolutions\n"
    ):
        _original_replace_once(
            path,
            "        ]\n"
            "        for resolution in model.supported_photo_resolutions\n"
            "    ]\n"
            "    rows.extend(\n",
            "        ]\n"
            "        for resolution in _available_resolutions(model, mode)\n"
            "    ]\n"
            "    rows.extend(\n",
        )
        return
    _original_replace_once(path, old, new)


patcher.replace_once = _replace_once
patcher.main()
