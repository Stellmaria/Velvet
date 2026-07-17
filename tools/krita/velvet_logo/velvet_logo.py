from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from krita import Extension, InfoObject, Krita
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from .logo_data import LOGO_SVG


POSITIONS = (
    ("Сверху слева", "top_left"),
    ("Сверху по центру", "top_center"),
    ("Сверху справа", "top_right"),
    ("По центру слева", "center_left"),
    ("По центру", "center"),
    ("По центру справа", "center_right"),
    ("Снизу слева", "bottom_left"),
    ("Снизу по центру", "bottom_center"),
    ("Снизу справа", "bottom_right"),
)
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class LogoDialog(QDialog):
    def __init__(self, settings: dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Velvet Anatomy: логотип")
        self.color = QComboBox()
        for label, value in (
            ("Чёрный", "#000000"),
            ("Белый", "#ffffff"),
            ("Автоконтраст", "auto"),
            ("Свой HEX", "custom"),
        ):
            self.color.addItem(label, value)
        stored_color = str(settings.get("color", "#000000"))
        color_mode = stored_color if stored_color in {"#000000", "#ffffff", "auto"} else "custom"
        self._select(self.color, color_mode)
        self.custom_color = QLineEdit(
            stored_color if color_mode == "custom" else str(settings.get("custom_color", ""))
        )
        self.custom_color.setPlaceholderText("#D8C8B8")
        self.color.currentIndexChanged.connect(
            lambda: self.custom_color.setEnabled(self.color.currentData() == "custom")
        )

        self.position = QComboBox()
        for label, value in POSITIONS:
            self.position.addItem(label, value)
        self._select(self.position, settings.get("position", "bottom_right"))

        self.size = QDoubleSpinBox()
        self.size.setRange(3.0, 70.0)
        self.size.setDecimals(1)
        self.size.setValue(float(settings.get("size", 16.7)))
        self.size.setSuffix(" % ширины фото")

        self.margin = QDoubleSpinBox()
        self.margin.setRange(0.0, 30.0)
        self.margin.setDecimals(1)
        self.margin.setValue(float(settings.get("margin", 4.4)))
        self.margin.setSuffix(" % ширины фото")

        self.opacity = QSpinBox()
        self.opacity.setRange(1, 100)
        self.opacity.setValue(int(settings.get("opacity", 70)))
        self.opacity.setSuffix(" %")

        self.lock_layer = QCheckBox("Заблокировать слой после добавления")
        self.lock_layer.setChecked(bool(settings.get("lock", True)))

        form = QFormLayout()
        form.addRow("Цвет:", self.color)
        form.addRow("Свой цвет:", self.custom_color)
        form.addRow("Расположение:", self.position)
        form.addRow("Размер:", self.size)
        form.addRow("Отступ от края:", self.margin)
        form.addRow("Непрозрачность:", self.opacity)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.lock_layer)
        layout.addWidget(buttons)
        self.custom_color.setEnabled(color_mode == "custom")

    @staticmethod
    def _select(combo: QComboBox, value: Any) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def values(self) -> dict[str, Any]:
        color = str(self.color.currentData())
        custom = self.custom_color.text().strip().lower()
        if color == "custom":
            if not HEX_COLOR.fullmatch(custom):
                raise ValueError("Введите HEX-цвет вида #D8C8B8.")
            color = custom
        return {
            "color": color,
            "custom_color": custom,
            "position": str(self.position.currentData()),
            "size": self.size.value(),
            "margin": self.margin.value(),
            "opacity": self.opacity.value(),
            "lock": self.lock_layer.isChecked(),
        }


class VelvetLogoExtension(Extension):
    LAYER_PREFIX = "Velvet Anatomy Logo"
    SETTINGS_GROUP = "VelvetAnatomyLogo"
    LOGO_ASPECT = 795.0 / 1055.0

    def __init__(self, parent):
        super().__init__(parent)
        self._bridge_root: Path | None = None
        self._timer: QTimer | None = None
        self._busy = False

    def setup(self) -> None:
        app = Krita.instance()
        configured = (
            app.readSetting(self.SETTINGS_GROUP, "bridge_dir", "").strip()
            or os.getenv("VELVET_KRITA_BRIDGE_DIR", "").strip()
            or os.getenv("KRITA_BRIDGE_DIR", "").strip()
            or str(Path.home() / "VelvetKritaBridge")
        )
        self._set_bridge_root(configured)
        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    def createActions(self, window) -> None:
        actions = (
            ("velvet_logo_add", "Velvet Anatomy: добавить логотип…", self.show_dialog),
            ("velvet_logo_repeat", "Velvet Anatomy: повторить последний логотип", self.repeat_last),
            ("velvet_logo_remove", "Velvet Anatomy: удалить логотип", self.remove_logo),
            ("velvet_logo_bridge_configure", "Velvet Anatomy: настроить bridge-каталог…", self.configure_bridge),
        )
        for action_id, title, handler in actions:
            action = window.createAction(action_id, title, "tools/scripts")
            action.triggered.connect(handler)

    def configure_bridge(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            None,
            "Каталог Velvet Krita bridge",
            str(self._bridge_root or Path.home()),
        )
        if selected:
            self._set_bridge_root(selected)
            QMessageBox.information(None, "Velvet Anatomy", f"Bridge-каталог:\n{self._bridge_root}")

    def show_dialog(self) -> None:
        document = Krita.instance().activeDocument()
        if document is None:
            QMessageBox.warning(None, "Velvet Anatomy", "Сначала откройте фотографию.")
            return
        dialog = LogoDialog(self._load_settings())
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            settings = self._normalize(dialog.values())
            self._save_settings(settings)
            self._apply(document, settings)
        except Exception as error:
            QMessageBox.critical(None, "Velvet Anatomy", str(error))

    def repeat_last(self) -> None:
        document = Krita.instance().activeDocument()
        if document is not None:
            self._apply(document, self._load_settings())

    def remove_logo(self) -> None:
        document = Krita.instance().activeDocument()
        if document is None:
            QMessageBox.warning(None, "Velvet Anatomy", "Сначала откройте фотографию.")
            return
        removed = self._remove_layers(document)
        document.refreshProjection()
        QMessageBox.information(
            None,
            "Velvet Anatomy",
            "Логотип удалён." if removed else "Логотип не найден.",
        )

    def _set_bridge_root(self, value: str) -> None:
        root = Path(value).expanduser().resolve()
        for name in ("requests", "responses", "outputs", "sources", "previews"):
            (root / name).mkdir(parents=True, exist_ok=True)
        self._bridge_root = root
        Krita.instance().writeSetting(self.SETTINGS_GROUP, "bridge_dir", str(root))

    def _poll(self) -> None:
        if self._busy or self._bridge_root is None:
            return
        requests = sorted((self._bridge_root / "requests").glob("*.json"))[:3]
        if not requests:
            return
        self._busy = True
        try:
            for request_path in requests:
                processing = request_path.with_suffix(".processing")
                try:
                    os.replace(request_path, processing)
                except OSError:
                    continue
                try:
                    self._process_request(processing)
                finally:
                    processing.unlink(missing_ok=True)
        finally:
            self._busy = False

    def _process_request(self, request_path: Path) -> None:
        response: dict[str, Any] = {"status": "error"}
        response_path: Path | None = None
        document = None
        opened_by_bridge = False
        try:
            request = json.loads(request_path.read_text(encoding="utf-8"))
            for key in ("request_id", "job_id", "revision"):
                response[key] = request.get(key)
            response_path = self._safe_path(request.get("response_path"), required=True)
            source_path = self._safe_path(request.get("source_path"), required=True)
            output_path = self._safe_path(request.get("output_path"), required=True)
            declared_root = request.get("bridge_root")
            if declared_root and Path(declared_root).expanduser().resolve() != self._bridge_root:
                raise ValueError("Bridge request использует другой каталог.")

            document = Krita.instance().openDocument(str(source_path))
            if document is None:
                raise RuntimeError(f"Krita не открыла файл: {source_path}")
            opened_by_bridge = True
            window = Krita.instance().activeWindow()
            if window is not None:
                window.addView(document)

            if request.get("remove_only"):
                self._remove_layers(document)
                document.refreshProjection()
            else:
                settings = self._normalize(request.get("settings") or {})
                self._apply(document, settings)
                response["applied_settings"] = settings
            self._export(document, output_path)
            response.update(status="ok", output_path=str(output_path))
        except Exception as error:
            response["error"] = str(error)
        finally:
            if response_path is not None:
                self._write_response(response_path, response)
            if opened_by_bridge and document is not None:
                document.setModified(False)
                document.close()

    def _safe_path(self, value: Any, *, required: bool) -> Path | None:
        if not value:
            if required:
                raise ValueError("Bridge request не содержит обязательный путь.")
            return None
        if self._bridge_root is None:
            raise RuntimeError("Bridge не инициализирован.")
        path = Path(str(value)).expanduser().resolve()
        try:
            path.relative_to(self._bridge_root)
        except ValueError as error:
            raise ValueError("Путь выходит за каталог bridge.") from error
        return path

    def _write_response(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    def _apply(self, document, raw_settings: dict[str, Any]) -> None:
        settings = self._normalize(raw_settings)
        color = settings["color"]
        if color == "auto":
            color = self._auto_color(document, settings)
        settings = dict(settings, color=color)
        self._remove_layers(document)
        root = document.rootNode()
        layer = document.createVectorLayer(f"{self.LAYER_PREFIX} ({color})")
        root.addChildNode(layer, None)
        shapes = layer.addShapesFromSvg(self._build_svg(document, settings))
        if not shapes:
            root.removeChildNode(layer)
            raise RuntimeError("Krita не смогла импортировать SVG логотипа.")
        layer.setOpacity(round(255 * settings["opacity"] / 100.0))
        layer.setLocked(settings["lock"])
        document.setActiveNode(layer)
        document.setModified(True)
        document.refreshProjection()

    def _build_svg(self, document, settings: dict[str, Any]) -> str:
        width = float(document.width())
        height = float(document.height())
        points = 72.0 / float(document.resolution() or 72.0)
        canvas_width, canvas_height = width * points, height * points
        logo_width = width * settings["size"] / 100.0 * points
        logo_height = logo_width * self.LOGO_ASPECT
        margin = width * settings["margin"] / 100.0 * points
        vertical, horizontal = self._parts(settings["position"])
        x = self._axis(horizontal, canvas_width, logo_width, margin)
        y = self._axis(vertical, canvas_height, logo_height, margin)
        scale = logo_width / 1055.0
        start = LOGO_SVG.index("<path")
        path = LOGO_SVG[start:LOGO_SVG.index("/>", start) + 2].replace(
            "#000000", settings["color"]
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}pt" '
            f'height="{canvas_height}pt" viewBox="0 0 {canvas_width} {canvas_height}">'
            f'<g transform="translate({x} {y}) scale({scale}) translate(-99 -250)">'
            f"{path}</g></svg>"
        )

    def _auto_color(self, document, settings: dict[str, Any]) -> str:
        width, height = int(document.width()), int(document.height())
        sample_width = max(8, int(width * min(settings["size"] + settings["margin"], 40) / 100))
        sample_height = max(8, int(sample_width * self.LOGO_ASPECT))
        margin = int(width * settings["margin"] / 100)
        vertical, horizontal = self._parts(settings["position"])
        x = int(self._axis(horizontal, width, sample_width, margin))
        y = int(self._axis(vertical, height, sample_height, margin))
        x = max(0, min(x, width - sample_width))
        y = max(0, min(y, height - sample_height))
        pixel_reader = getattr(document, "projectionPixelData", None)
        if not callable(pixel_reader):
            pixel_reader = getattr(document, "pixelData", None)
        if not callable(pixel_reader):
            raise RuntimeError(
                "Эта версия Krita не предоставляет API чтения пикселей документа."
            )
        raw = bytes(pixel_reader(x, y, sample_width, sample_height))
        if len(raw) < 4:
            return "#ffffff"
        step = max(4, (len(raw) // 1200 // 4) * 4)
        values = [sum(raw[i:i + 3]) / 3 for i in range(0, len(raw) - 3, step) if raw[i + 3]]
        average = sum(values) / len(values) if values else 0
        return "#000000" if average >= 145 else "#ffffff"

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        settings = self._load_settings()
        settings.update(raw)
        position = str(settings.get("position", "bottom_right")).casefold()
        if position not in {value for _, value in POSITIONS}:
            raise ValueError("Неизвестное положение логотипа.")
        color = str(settings.get("color", "#000000")).strip().casefold()
        if color == "custom":
            color = str(settings.get("custom_color", "")).strip().casefold()
        if color != "auto" and not HEX_COLOR.fullmatch(color):
            raise ValueError("Некорректный HEX-цвет логотипа.")
        return {
            "position": position,
            "color": color,
            "custom_color": str(settings.get("custom_color", "")),
            "size": max(3.0, min(float(settings.get("size", 16.7)), 70.0)),
            "margin": max(0.0, min(float(settings.get("margin", 4.4)), 30.0)),
            "opacity": max(1, min(int(settings.get("opacity", 70)), 100)),
            "lock": self._boolean(settings.get("lock", True)),
        }

    def _load_settings(self) -> dict[str, Any]:
        app = Krita.instance()
        read = lambda key, default: app.readSetting(self.SETTINGS_GROUP, key, str(default))
        return {
            "position": read("position", "bottom_right"),
            "color": read("color", "#000000"),
            "custom_color": read("custom_color", ""),
            "size": read("size", "16.7"),
            "margin": read("margin", "4.4"),
            "opacity": read("opacity", "70"),
            "lock": read("lock", "true"),
        }

    def _save_settings(self, settings: dict[str, Any]) -> None:
        app = Krita.instance()
        for key, value in settings.items():
            app.writeSetting(self.SETTINGS_GROUP, key, str(value).lower() if isinstance(value, bool) else str(value))

    def _remove_layers(self, document) -> bool:
        root = document.rootNode()
        removed = False
        for node in list(root.childNodes()):
            if node.name().startswith(self.LAYER_PREFIX):
                root.removeChildNode(node)
                removed = True
        if removed:
            document.setModified(True)
        return removed

    @staticmethod
    def _export(document, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        info = InfoObject()
        info.setProperty("alpha", True)
        if not document.exportImage(str(path), info):
            raise RuntimeError(f"Не удалось экспортировать файл: {path}")

    @staticmethod
    def _parts(position: str) -> tuple[str, str]:
        return ("center", "center") if position == "center" else tuple(position.split("_", 1))

    @staticmethod
    def _axis(alignment: str, canvas: float, object_size: float, margin: float) -> float:
        if alignment in {"left", "top"}:
            return margin
        if alignment == "center":
            return (canvas - object_size) / 2
        return canvas - object_size - margin

    @staticmethod
    def _boolean(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {"1", "true", "yes", "on", "да"}
