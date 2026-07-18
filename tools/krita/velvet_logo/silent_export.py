from __future__ import annotations

from pathlib import Path

from krita import InfoObject


def silent_png_export(document, path: Path) -> None:
    """Export a PNG in batch mode without showing Krita's options dialog."""

    path.parent.mkdir(parents=True, exist_ok=True)
    info = InfoObject()
    info.setProperty("alpha", True)
    info.setProperty("compression", 3)
    info.setProperty("forceSRGB", False)
    info.setProperty("indexed", False)
    info.setProperty("interlaced", False)
    info.setProperty("saveSRGBProfile", True)
    info.setProperty("transparencyFillcolor", [0, 0, 0])

    batchmode = getattr(document, "batchmode", None)
    set_batchmode = getattr(document, "setBatchmode", None)
    wait_for_done = getattr(document, "waitForDone", None)
    previous_batch_mode = bool(batchmode()) if callable(batchmode) else False

    if callable(set_batchmode):
        set_batchmode(True)
    try:
        if callable(wait_for_done):
            wait_for_done()
        exported = bool(document.exportImage(str(path), info))
        if callable(wait_for_done):
            wait_for_done()
        # Krita 5.3 may return False even after the file was written. The actual
        # file is the authoritative result for this local bridge operation.
        if (not exported and not path.is_file()) or not path.is_file():
            raise RuntimeError(f"Не удалось экспортировать файл: {path}")
        if path.stat().st_size <= 0:
            raise RuntimeError(f"Krita создала пустой PNG: {path}")
    finally:
        if callable(set_batchmode):
            set_batchmode(previous_batch_mode)


def install_silent_export(extension_class) -> None:
    extension_class._export = staticmethod(silent_png_export)


__all__ = ("install_silent_export", "silent_png_export")
