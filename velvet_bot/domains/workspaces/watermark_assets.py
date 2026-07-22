from __future__ import annotations

import hashlib
import io
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from velvet_bot.database import Database
from velvet_bot.infrastructure.krita_bridge import KritaBridgePaths

_MAX_SVG_BYTES = 5 * 1024 * 1024
_MAX_RASTER_BYTES = 10 * 1024 * 1024
_MAX_SIDE = 8192
_MAX_PIXELS = 40_000_000
_BLOCKED_SVG_TAGS = frozenset(
    {"script", "foreignobject", "iframe", "object", "embed", "audio", "video"}
)
_LENGTH_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(?:px|pt|mm|cm|in)?\s*$", re.I)


@dataclass(frozen=True, slots=True)
class WorkspaceWatermarkAsset:
    workspace_id: int
    asset_kind: str
    telegram_file_id: str
    telegram_file_unique_id: str | None
    file_name: str
    mime_type: str
    file_size: int
    local_path: str
    content_sha256: str
    width: float
    height: float
    has_alpha: bool
    uploaded_by: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PreparedWatermarkAsset:
    asset_kind: str
    mime_type: str
    suffix: str
    payload: bytes
    width: float
    height: float
    has_alpha: bool
    content_sha256: str


class WorkspaceWatermarkAssetRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get(self, workspace_id: int) -> WorkspaceWatermarkAsset | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM workspace_watermark_assets
                WHERE workspace_id = $1::BIGINT
                """,
                int(workspace_id),
            )
        return self._map(row) if row is not None else None

    async def upsert(
        self,
        *,
        workspace_id: int,
        prepared: PreparedWatermarkAsset,
        telegram_file_id: str,
        telegram_file_unique_id: str | None,
        file_name: str,
        local_path: str,
        uploaded_by: int,
    ) -> tuple[WorkspaceWatermarkAsset, str | None]:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                previous_path = await connection.fetchval(
                    """
                    SELECT local_path
                    FROM workspace_watermark_assets
                    WHERE workspace_id = $1::BIGINT
                    FOR UPDATE
                    """,
                    int(workspace_id),
                )
                row = await connection.fetchrow(
                    """
                    INSERT INTO workspace_watermark_assets (
                        workspace_id, asset_kind, telegram_file_id,
                        telegram_file_unique_id, file_name, mime_type,
                        file_size, local_path, content_sha256,
                        width, height, has_alpha, uploaded_by
                    )
                    VALUES (
                        $1::BIGINT, $2::VARCHAR, $3::TEXT,
                        $4::TEXT, $5::TEXT, $6::VARCHAR,
                        $7::BIGINT, $8::TEXT, $9::CHAR(64),
                        $10::DOUBLE PRECISION, $11::DOUBLE PRECISION,
                        $12::BOOLEAN, $13::BIGINT
                    )
                    ON CONFLICT (workspace_id) DO UPDATE
                    SET asset_kind = EXCLUDED.asset_kind,
                        telegram_file_id = EXCLUDED.telegram_file_id,
                        telegram_file_unique_id = EXCLUDED.telegram_file_unique_id,
                        file_name = EXCLUDED.file_name,
                        mime_type = EXCLUDED.mime_type,
                        file_size = EXCLUDED.file_size,
                        local_path = EXCLUDED.local_path,
                        content_sha256 = EXCLUDED.content_sha256,
                        width = EXCLUDED.width,
                        height = EXCLUDED.height,
                        has_alpha = EXCLUDED.has_alpha,
                        uploaded_by = EXCLUDED.uploaded_by,
                        updated_at = NOW()
                    RETURNING *
                    """,
                    int(workspace_id),
                    prepared.asset_kind,
                    telegram_file_id,
                    telegram_file_unique_id,
                    file_name,
                    prepared.mime_type,
                    len(prepared.payload),
                    local_path,
                    prepared.content_sha256,
                    prepared.width,
                    prepared.height,
                    prepared.has_alpha,
                    int(uploaded_by),
                )
        if row is None:
            raise RuntimeError("Не удалось сохранить логотип пространства.")
        return self._map(row), (str(previous_path) if previous_path else None)

    async def delete(self, workspace_id: int) -> WorkspaceWatermarkAsset | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                DELETE FROM workspace_watermark_assets
                WHERE workspace_id = $1::BIGINT
                RETURNING *
                """,
                int(workspace_id),
            )
        return self._map(row) if row is not None else None

    @staticmethod
    def _map(row) -> WorkspaceWatermarkAsset:
        return WorkspaceWatermarkAsset(
            workspace_id=int(row["workspace_id"]),
            asset_kind=str(row["asset_kind"]),
            telegram_file_id=str(row["telegram_file_id"]),
            telegram_file_unique_id=(
                str(row["telegram_file_unique_id"])
                if row["telegram_file_unique_id"] is not None
                else None
            ),
            file_name=str(row["file_name"]),
            mime_type=str(row["mime_type"]),
            file_size=int(row["file_size"]),
            local_path=str(row["local_path"]),
            content_sha256=str(row["content_sha256"]),
            width=float(row["width"]),
            height=float(row["height"]),
            has_alpha=bool(row["has_alpha"]),
            uploaded_by=int(row["uploaded_by"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class WorkspaceWatermarkAssetService:
    def __init__(
        self,
        *,
        repository: WorkspaceWatermarkAssetRepository,
        bridge_paths: KritaBridgePaths,
    ) -> None:
        self._repository = repository
        self._paths = bridge_paths

    async def get(self, workspace_id: int) -> WorkspaceWatermarkAsset | None:
        return await self._repository.get(workspace_id)

    async def store(
        self,
        *,
        workspace_id: int,
        raw: bytes,
        file_name: str,
        mime_type: str | None,
        telegram_file_id: str,
        telegram_file_unique_id: str | None,
        uploaded_by: int,
    ) -> WorkspaceWatermarkAsset:
        prepared = prepare_watermark_asset(raw, file_name=file_name, mime_type=mime_type)
        directory = self._asset_directory(workspace_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = self._safe_asset_path(
            directory / f"logo-{prepared.content_sha256[:20]}{prepared.suffix}"
        )
        temporary = self._safe_asset_path(path.with_suffix(path.suffix + ".tmp"))
        temporary.write_bytes(prepared.payload)
        os.replace(temporary, path)
        try:
            asset, previous_path = await self._repository.upsert(
                workspace_id=workspace_id,
                prepared=prepared,
                telegram_file_id=telegram_file_id,
                telegram_file_unique_id=telegram_file_unique_id,
                file_name=_safe_file_name(file_name, prepared.suffix),
                local_path=str(path),
                uploaded_by=uploaded_by,
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        if previous_path and Path(previous_path).resolve(strict=False) != path:
            self._delete_owned_path(previous_path)
        return asset

    async def reset(self, workspace_id: int) -> bool:
        asset = await self._repository.delete(workspace_id)
        if asset is None:
            return False
        self._delete_owned_path(asset.local_path)
        return True

    def _asset_directory(self, workspace_id: int) -> Path:
        return self._safe_asset_path(self._paths.assets / f"workspace-{int(workspace_id)}")

    def _safe_asset_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser().resolve(strict=False)
        root = self._paths.assets.resolve(strict=False)
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ValueError("Путь логотипа выходит за каталог assets.") from error
        return path

    def _delete_owned_path(self, value: str | Path) -> None:
        try:
            path = self._safe_asset_path(value)
        except ValueError:
            return
        path.unlink(missing_ok=True)


def prepare_watermark_asset(
    raw: bytes,
    *,
    file_name: str,
    mime_type: str | None,
) -> PreparedWatermarkAsset:
    if not raw:
        raise ValueError("Файл логотипа пуст.")
    suffix = Path(file_name or "").suffix.casefold()
    normalized_mime = (mime_type or "").strip().casefold()
    if suffix == ".svg" or normalized_mime == "image/svg+xml":
        return _prepare_svg(raw)
    if suffix not in {".png", ".webp"} and normalized_mime not in {
        "image/png",
        "image/webp",
    }:
        raise ValueError("Поддерживаются SVG, PNG и WebP с прозрачным фоном.")
    return _prepare_raster(raw)


def _prepare_svg(raw: bytes) -> PreparedWatermarkAsset:
    if len(raw) > _MAX_SVG_BYTES:
        raise ValueError("SVG-логотип больше 5 МБ.")
    lowered = raw[:4096].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("DOCTYPE и ENTITY запрещены в SVG-логотипе.")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError("SVG повреждён или содержит некорректный XML.") from error
    if _local_name(root.tag) != "svg":
        raise ValueError("Корневой элемент файла должен быть <svg>.")
    for element in root.iter():
        tag = _local_name(element.tag)
        if tag in _BLOCKED_SVG_TAGS:
            raise ValueError(f"Элемент <{tag}> запрещён в SVG-логотипе.")
        for raw_name, raw_value in element.attrib.items():
            name = _local_name(raw_name)
            value = str(raw_value).strip()
            lowered_value = value.casefold()
            if name.startswith("on"):
                raise ValueError("Обработчики событий запрещены в SVG-логотипе.")
            if name in {"href", "src"} and value and not value.startswith("#"):
                raise ValueError("Внешние ссылки и встроенные файлы запрещены в SVG.")
            if "javascript:" in lowered_value or "file:" in lowered_value:
                raise ValueError("Небезопасная ссылка запрещена в SVG-логотипе.")
            if "@import" in lowered_value:
                raise ValueError("Импорт внешних стилей запрещён в SVG-логотипе.")
            for match in re.findall(r"url\(([^)]+)\)", lowered_value):
                target = match.strip(" \t\r\n\"'")
                if not target.startswith("#"):
                    raise ValueError("Внешние CSS-ресурсы запрещены в SVG-логотипе.")
    width, height = _svg_dimensions(root)
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    digest = hashlib.sha256(payload).hexdigest()
    return PreparedWatermarkAsset(
        asset_kind="svg",
        mime_type="image/svg+xml",
        suffix=".svg",
        payload=payload,
        width=width,
        height=height,
        has_alpha=True,
        content_sha256=digest,
    )


def _prepare_raster(raw: bytes) -> PreparedWatermarkAsset:
    if len(raw) > _MAX_RASTER_BYTES:
        raise ValueError("Растровый логотип больше 10 МБ.")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            width, height = image.size
            if width <= 0 or height <= 0 or width > _MAX_SIDE or height > _MAX_SIDE:
                raise ValueError("Размер логотипа должен быть от 1 до 8192 пикселей.")
            if width * height > _MAX_PIXELS:
                raise ValueError("Растровый логотип содержит слишком много пикселей.")
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            minimum, maximum = alpha.getextrema()
            if minimum == 255 and maximum == 255:
                raise ValueError("У PNG/WebP нет прозрачного фона. Отправьте файл с alpha-каналом.")
            output = io.BytesIO()
            rgba.save(output, format="PNG", optimize=True)
    except ValueError:
        raise
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError("Файл не является корректным PNG или WebP.") from error
    payload = output.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    return PreparedWatermarkAsset(
        asset_kind="png",
        mime_type="image/png",
        suffix=".png",
        payload=payload,
        width=float(width),
        height=float(height),
        has_alpha=True,
        content_sha256=digest,
    )


def _svg_dimensions(root: ET.Element) -> tuple[float, float]:
    view_box = root.attrib.get("viewBox") or root.attrib.get("viewbox")
    if view_box:
        parts = re.split(r"[\s,]+", view_box.strip())
        if len(parts) == 4:
            try:
                width = float(parts[2])
                height = float(parts[3])
            except ValueError:
                width = height = 0.0
            if width > 0 and height > 0:
                return width, height
    width = _parse_length(root.attrib.get("width"))
    height = _parse_length(root.attrib.get("height"))
    if width and height:
        return width, height
    raise ValueError("SVG должен содержать корректный viewBox или width/height.")


def _parse_length(value: str | None) -> float | None:
    if not value:
        return None
    match = _LENGTH_RE.fullmatch(value)
    if match is None:
        return None
    number = float(match.group(1))
    return number if number > 0 else None


def _local_name(value: str) -> str:
    return value.rsplit("}", maxsplit=1)[-1].casefold()


def _safe_file_name(value: str, suffix: str) -> str:
    name = Path(value or f"logo{suffix}").name.strip()
    return (name or f"logo{suffix}")[:255]


__all__ = (
    "PreparedWatermarkAsset",
    "WorkspaceWatermarkAsset",
    "WorkspaceWatermarkAssetRepository",
    "WorkspaceWatermarkAssetService",
    "prepare_watermark_asset",
)
