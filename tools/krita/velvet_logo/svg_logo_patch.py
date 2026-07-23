from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtSvg import QSvgRenderer


PATCH_VERSION = "2.1.0"
_MAX_RASTER_SIDE = 4096.0


def _render_svg_to_png(raw: bytes, *, width: float, height: float) -> bytes:
    renderer = QSvgRenderer(QByteArray(raw))
    if not renderer.isValid():
        raise RuntimeError(
            f"SVG логотип не удалось прочитать (Krita plugin {PATCH_VERSION})."
        )

    scale = min(1.0, _MAX_RASTER_SIDE / max(width, height))
    pixel_width = max(1, int(round(width * scale)))
    pixel_height = max(1, int(round(height * scale)))
    image = QImage(
        pixel_width,
        pixel_height,
        QImage.Format_ARGB32_Premultiplied,
    )
    image.fill(0)

    painter = QPainter(image)
    try:
        renderer.render(painter)
    finally:
        painter.end()

    buffer = QBuffer()
    if not buffer.open(QIODevice.WriteOnly):
        raise RuntimeError(
            f"Не удалось подготовить PNG логотипа (Krita plugin {PATCH_VERSION})."
        )
    try:
        if not image.save(buffer, "PNG"):
            raise RuntimeError(
                f"Не удалось сохранить PNG логотипа (Krita plugin {PATCH_VERSION})."
            )
        payload = bytes(buffer.data())
    finally:
        buffer.close()
    if not payload:
        raise RuntimeError(
            f"Получен пустой PNG логотипа (Krita plugin {PATCH_VERSION})."
        )
    return payload


def install_svg_logo_patch(extension_class) -> None:
    """Make custom SVG assets deterministic for Krita's addShapesFromSvg API.

    Krita is inconsistent when one SVG document is nested inside another. The bot
    still validates and stores the original SVG, but the desktop plugin renders it
    to a transparent PNG first and embeds that PNG into the normal wrapper used by
    the already working custom-PNG path.
    """

    if getattr(extension_class, "_velvet_svg_raster_patch", False):
        return

    original_build_svg = extension_class._build_svg

    def build_svg(
        self,
        document,
        settings: dict[str, Any],
        logo: dict[str, Any] | None = None,
    ) -> str:
        logo = logo or {"kind": "builtin"}
        kind = str(logo.get("kind") or "builtin").casefold()
        if kind != "svg":
            return original_build_svg(self, document, settings, logo)

        source = self._safe_path(logo.get("path"), required=True)
        assert source is not None
        assets_root = (self._bridge_root / "assets").resolve()
        try:
            Path(source).resolve().relative_to(assets_root)
        except ValueError as error:
            raise ValueError("Пользовательский логотип находится вне assets.") from error

        source_width = float(logo.get("width") or 0)
        source_height = float(logo.get("height") or 0)
        if source_width <= 0 or source_height <= 0:
            raise ValueError("Некорректные размеры пользовательского логотипа.")

        png = _render_svg_to_png(
            source.read_bytes(),
            width=source_width,
            height=source_height,
        )
        encoded = base64.b64encode(png).decode("ascii")

        width = float(document.width())
        height = float(document.height())
        points = 72.0 / float(document.resolution() or 72.0)
        canvas_width, canvas_height = width * points, height * points
        logo_width = width * settings["size"] / 100.0 * points
        logo_height = logo_width * source_height / source_width
        margin = width * settings["margin"] / 100.0 * points
        vertical, horizontal = self._parts(settings["position"])
        x = self._axis(horizontal, canvas_width, logo_width, margin)
        y = self._axis(vertical, canvas_height, logo_height, margin)
        body = (
            f'<image x="{x}" y="{y}" width="{logo_width}" height="{logo_height}" '
            f'preserveAspectRatio="xMidYMid meet" '
            f'href="data:image/png;base64,{encoded}" />'
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{canvas_width}pt" '
            f'height="{canvas_height}pt" viewBox="0 0 {canvas_width} {canvas_height}">'
            f"{body}</svg>"
        )

    extension_class._build_svg = build_svg
    extension_class._velvet_svg_raster_patch = True
    extension_class.PLUGIN_VERSION = PATCH_VERSION


__all__ = ("PATCH_VERSION", "install_svg_logo_patch")
