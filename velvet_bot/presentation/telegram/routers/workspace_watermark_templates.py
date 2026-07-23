from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.watermark_templates import (
    WorkspaceWatermarkTemplateRepository,
)
from velvet_bot.workspace_watermark_ui import watermark_asset_callback


router = Router(name=__name__)

_POSITION_LABELS = {
    "top_left": "↖️ Сверху слева",
    "top_center": "⬆️ Сверху",
    "top_right": "↗️ Сверху справа",
    "center_left": "⬅️ Слева",
    "center": "⏺ По центру",
    "center_right": "➡️ Справа",
    "bottom_left": "↙️ Снизу слева",
    "bottom_center": "⬇️ Снизу",
    "bottom_right": "↘️ Снизу справа",
}


class WorkspaceWatermarkTemplateCallback(CallbackData, prefix="wmtpl"):
    action: str
    workspace_id: int
    value: str = ""


def template_callback(action: str, *, workspace_id: int, value: str = "") -> str:
    return WorkspaceWatermarkTemplateCallback(
        action=action,
        workspace_id=int(workspace_id),
        value=value,
    ).pack()


def _global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _require_context(
    database: Database,
    workspace_service: WorkspaceService,
    *,
    workspace_id: int,
    user_id: int,
) -> Workspace:
    workspace = await workspace_service.set_active_workspace(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        global_owner=_global_owner(user_id),
    )
    if workspace.is_system:
        raise WorkspaceAccessError("Системный шаблон Velvet изменяется отдельно.")
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=int(user_id),
        minimum_role="admin",
        global_owner=_global_owner(user_id),
    )
    async with database.acquire() as connection:
        enabled = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT AND module_key = 'watermark'
            """,
            workspace.id,
        )
    if not enabled:
        raise WorkspaceAccessError("Модуль watermark выключен.")
    return workspace


def _template_text(workspace: Workspace, settings) -> str:
    position = _POSITION_LABELS.get(settings.position, settings.position)
    color = "автоконтраст" if settings.color == "auto" else settings.color.upper()
    return (
        f"<b>🧩 Шаблон watermark · {escape(workspace.name)}</b>\n\n"
        f"Положение: <b>{escape(position)}</b>\n"
        f"Цвет: <b>{escape(color)}</b>\n"
        f"Непрозрачность: <b>{settings.opacity}%</b>\n"
        f"Размер: <b>{settings.size:.1f}%</b> ширины\n"
        f"Отступ: <b>{settings.margin:.1f}%</b> ширины\n"
        f"Слой: <b>{'заблокирован' if settings.lock else 'редактируемый'}</b>\n\n"
        "Этот шаблон автоматически применяется ко всем новым заданиям личного "
        "архива. Настройки конкретной копии после создания всё равно можно изменить."
    )


def _template_keyboard(workspace_id: int, settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📍 Положение",
                    callback_data=template_callback("positions", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="🎨 Цвет",
                    callback_data=template_callback("colors", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➖ Прозрачность",
                    callback_data=template_callback("opacity-", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text=f"{settings.opacity}%",
                    callback_data=template_callback("noop", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="➕ Прозрачность",
                    callback_data=template_callback("opacity+", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➖ Размер",
                    callback_data=template_callback("size-", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text=f"{settings.size:.1f}%",
                    callback_data=template_callback("noop", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="➕ Размер",
                    callback_data=template_callback("size+", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➖ Отступ",
                    callback_data=template_callback("margin-", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text=f"{settings.margin:.1f}%",
                    callback_data=template_callback("noop", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="➕ Отступ",
                    callback_data=template_callback("margin+", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=("🔒 Слой" if settings.lock else "🔓 Слой"),
                    callback_data=template_callback("lock", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="↩️ Сбросить",
                    callback_data=template_callback("reset", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Watermark",
                    callback_data=watermark_asset_callback("show", workspace_id=workspace_id),
                )
            ],
        ]
    )


async def _edit(callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


async def _show(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    repository: WorkspaceWatermarkTemplateRepository,
) -> None:
    settings = await repository.get(workspace.id)
    await _edit(
        callback,
        _template_text(workspace, settings),
        _template_keyboard(workspace.id, settings),
    )


def _positions_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    keys = tuple(_POSITION_LABELS)
    rows: list[list[InlineKeyboardButton]] = []
    for start in range(0, len(keys), 3):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_POSITION_LABELS[key].split(" ", 1)[0],
                    callback_data=template_callback(
                        "position", workspace_id=workspace_id, value=key
                    ),
                )
                for key in keys[start : start + 3]
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К шаблону",
                callback_data=template_callback("show", workspace_id=workspace_id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _colors_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌓 Автоконтраст",
                    callback_data=template_callback(
                        "color", workspace_id=workspace_id, value="auto"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚪ Белый",
                    callback_data=template_callback(
                        "color", workspace_id=workspace_id, value="#ffffff"
                    ),
                ),
                InlineKeyboardButton(
                    text="⚫ Чёрный",
                    callback_data=template_callback(
                        "color", workspace_id=workspace_id, value="#000000"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К шаблону",
                    callback_data=template_callback("show", workspace_id=workspace_id),
                )
            ],
        ]
    )


@router.callback_query(WorkspaceWatermarkTemplateCallback.filter())
async def handle_workspace_watermark_template(
    callback: CallbackQuery,
    callback_data: WorkspaceWatermarkTemplateCallback,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    try:
        workspace = await _require_context(
            database,
            workspace_service,
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    repository = WorkspaceWatermarkTemplateRepository(database)
    action = callback_data.action
    if action == "show":
        await _show(callback, workspace=workspace, repository=repository)
        return
    if action == "positions":
        await _edit(
            callback,
            "<b>Положение логотипа</b>\n\nВыберите точку шаблона.",
            _positions_keyboard(workspace.id),
        )
        return
    if action == "colors":
        await _edit(
            callback,
            "<b>Цвет логотипа</b>\n\nАвтоконтраст выбирает чёрный или белый по фону.",
            _colors_keyboard(workspace.id),
        )
        return
    if action == "noop":
        await callback.answer()
        return

    try:
        current = await repository.get(workspace.id)
        if action == "position":
            await repository.revise(
                workspace_id=workspace.id,
                updated_by_user_id=callback.from_user.id,
                position=callback_data.value,
            )
        elif action == "color":
            await repository.revise(
                workspace_id=workspace.id,
                updated_by_user_id=callback.from_user.id,
                color=callback_data.value,
            )
        elif action == "opacity-":
            await repository.revise(
                workspace_id=workspace.id,
                updated_by_user_id=callback.from_user.id,
                opacity_delta=-5,
            )
        elif action == "opacity+":
            await repository.revise(
                workspace_id=workspace.id,
                updated_by_user_id=callback.from_user.id,
                opacity_delta=5,
            )
        elif action == "size-":
            await repository.revise(
                workspace_id=workspace.id,
                updated_by_user_id=callback.from_user.id,
                size_delta=-2.0,
            )
        elif action == "size+":
            await repository.revise(
                workspace_id=workspace.id,
                updated_by_user_id=callback.from_user.id,
                size_delta=2.0,
            )
        elif action == "margin-":
            await repository.revise(
                workspace_id=workspace.id,
                updated_by_user_id=callback.from_user.id,
                margin_delta=-1.0,
            )
        elif action == "margin+":
            await repository.revise(
                workspace_id=workspace.id,
                updated_by_user_id=callback.from_user.id,
                margin_delta=1.0,
            )
        elif action == "lock":
            await repository.revise(
                workspace_id=workspace.id,
                updated_by_user_id=callback.from_user.id,
                lock=not current.lock,
            )
        elif action == "reset":
            await repository.reset(workspace.id)
        else:
            await callback.answer("Неизвестная настройка.", show_alert=True)
            return
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await _show(callback, workspace=workspace, repository=repository)


__all__ = ("router", "template_callback")
