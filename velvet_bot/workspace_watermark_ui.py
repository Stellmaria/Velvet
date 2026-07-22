from __future__ import annotations

from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.domains.workspaces.watermark_assets import WorkspaceWatermarkAsset
from velvet_bot.workspace_ui import workspace_callback


class WorkspaceWatermarkCallback(CallbackData, prefix="wlogo"):
    action: str
    workspace_id: int


class WorkspaceWatermarkForm(StatesGroup):
    waiting_asset = State()


def watermark_asset_callback(action: str, *, workspace_id: int) -> str:
    return WorkspaceWatermarkCallback(action=action, workspace_id=workspace_id).pack()


def format_workspace_watermark(
    *,
    workspace_name: str,
    asset: WorkspaceWatermarkAsset | None,
) -> str:
    if asset is None:
        details = (
            "Сейчас используется <b>стандартный логотип Velvet Anatomy</b>.\n\n"
            "Можно загрузить собственный SVG либо PNG/WebP с прозрачным фоном."
        )
    else:
        kind = "SVG" if asset.asset_kind == "svg" else "PNG"
        details = (
            f"Активный логотип: <b>{kind}</b>\n"
            f"Файл: <code>{escape(asset.file_name)}</code>\n"
            f"Размер: <b>{asset.width:g}×{asset.height:g}</b>\n"
            f"Вес: <b>{asset.file_size / 1024:.1f} КБ</b>\n"
            f"SHA-256: <code>{asset.content_sha256[:16]}…</code>\n\n"
            "Новые watermark-задания будут использовать этот логотип. Уже созданные "
            "задания сохраняют прежний snapshot."
        )
    return f"<b>💧 Логотип · {escape(workspace_name)}</b>\n\n{details}"


def build_workspace_watermark_keyboard(
    *,
    workspace_id: int,
    has_asset: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="📤 Загрузить или заменить логотип",
                callback_data=watermark_asset_callback(
                    "upload",
                    workspace_id=workspace_id,
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="🖼 Создать watermark с логотипом",
                callback_data=watermark_asset_callback(
                    "create",
                    workspace_id=workspace_id,
                ),
            )
        ],
    ]
    if has_asset:
        rows.append(
            [
                InlineKeyboardButton(
                    text="↩️ Вернуть стандартный Velvet",
                    callback_data=watermark_asset_callback(
                        "reset",
                        workspace_id=workspace_id,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Моё пространство",
                callback_data=workspace_callback("home", workspace_id=workspace_id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_reset_confirmation_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, использовать стандартный Velvet",
                    callback_data=watermark_asset_callback(
                        "resetok",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=watermark_asset_callback(
                        "show",
                        workspace_id=workspace_id,
                    ),
                )
            ],
        ]
    )


__all__ = (
    "WorkspaceWatermarkCallback",
    "WorkspaceWatermarkForm",
    "build_reset_confirmation_keyboard",
    "build_workspace_watermark_keyboard",
    "format_workspace_watermark",
    "watermark_asset_callback",
)
