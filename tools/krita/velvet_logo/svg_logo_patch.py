from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


PATCH_VERSION = "2.1.1"
_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
_NUMBER_SPLIT_RE = re.compile(r"[\s,]+")


def _local_name(value: str) -> tuple[str | None, str]:
    if value.startswith("{") and "}" in value:
        namespace, local = value[1:].split("}", 1)
        return namespace, local
    return None, value


def _strip_namespaces(node: ET.Element) -> None:
    _, local_tag = _local_name(str(node.tag))
    node.tag = local_tag

    normalized: dict[str, str] = {}
    for raw_name, value in node.attrib.items():
        namespace, local_name = _local_name(str(raw_name))
        if namespace == _XLINK_NS and local_name == "href":
            normalized["href"] = value
        elif namespace == _XML_NS:
            normalized[f"xml:{local_name}"] = value
        else:
            normalized[local_name] = value
    node.attrib.clear()
    node.attrib.update(normalized)

    for child in list(node):
        _strip_namespaces(child)


def _view_box(
    root: ET.Element,
    *,
    source_width: float,
    source_height: float,
) -> tuple[float, float, float, float]:
    raw = str(root.attrib.get("viewBox") or "").strip()
    if raw:
        parts = [part for part in _NUMBER_SPLIT_RE.split(raw) if part]
        if len(parts) == 4:
            try:
                min_x, min_y, width, height = (float(part) for part in parts)
            except ValueError:
                pass
            else:
                if (
                    all(math.isfinite(value) for value in (min_x, min_y, width, height))
                    and width > 0
                    and height > 0
                ):
                    return min_x, min_y, width, height
    return 0.0, 0.0, source_width, source_height


def _serialize_children(root: ET.Element) -> tuple[str, str]:
    definitions: list[str] = []
    visible: list[str] = []
    for child in list(root):
        payload = ET.tostring(child, encoding="unicode", short_empty_elements=True)
        if str(child.tag).casefold() in {"defs", "style", "metadata", "title", "desc"}:
            definitions.append(payload)
        else:
            visible.append(payload)
    if not visible:
        raise ValueError("SVG логотип не содержит видимых элементов.")
    return "".join(definitions), "".join(visible)


def _flatten_svg(
    raw: bytes,
    *,
    x: float,
    y: float,
    logo_width: float,
    logo_height: float,
    source_width: float,
    source_height: float,
) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError("SVG логотип не удалось разобрать.") from error

    _, root_name = _local_name(str(root.tag))
    if root_name.casefold() != "svg":
        raise ValueError("Файл не содержит корневой элемент SVG.")

    min_x, min_y, view_width, view_height = _view_box(
        root,
        source_width=source_width,
        source_height=source_height,
    )
    _strip_namespaces(root)
    definitions, visible = _serialize_children(root)

    scale = min(logo_width / view_width, logo_height / view_height)
    rendered_width = view_width * scale
    rendered_height = view_height * scale
    offset_x = x + (logo_width - rendered_width) / 2.0
    offset_y = y + (logo_height - rendered_height) / 2.0
    transform = (
        f"translate({offset_x:.8g} {offset_y:.8g}) "
        f"scale({scale:.8g}) "
        f"translate({-min_x:.8g} {-min_y:.8g})"
    )
    return f"{definitions}<g transform=\"{transform}\">{visible}</g>"


def install_svg_logo_patch(extension_class) -> None:
    """Flatten custom SVG assets before Krita's addShapesFromSvg API.

    Krita can reject nested SVG documents and desktop builds may become unstable when
    PyQt's QtSvg rasterizer is loaded inside the plugin process. The bridge therefore
    keeps the source as vector data, removes XML namespace prefixes and places the
    source children into one transformed group in the outer document.
    """

    if getattr(extension_class, "_velvet_svg_flatten_patch", False):
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

        try:
            body = _flatten_svg(
                source.read_bytes(),
                x=x,
                y=y,
                logo_width=logo_width,
                logo_height=logo_height,
                source_width=source_width,
                source_height=source_height,
            )
        except (OSError, ValueError) as error:
            raise RuntimeError(
                f"SVG логотип не удалось подготовить (Krita plugin {PATCH_VERSION}): {error}"
            ) from error

        return (
            f'<svg xmlns="{_SVG_NS}" xmlns:xlink="{_XLINK_NS}" '
            f'width="{canvas_width}pt" height="{canvas_height}pt" '
            f'viewBox="0 0 {canvas_width} {canvas_height}">{body}</svg>'
        )

    extension_class._build_svg = build_svg
    extension_class._velvet_svg_flatten_patch = True
    extension_class.PLUGIN_VERSION = PATCH_VERSION


__all__ = ("PATCH_VERSION", "install_svg_logo_patch")
