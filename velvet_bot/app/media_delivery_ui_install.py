from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Any, Mapping
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.application.media_tasks import task_payload_mapping
from velvet_bot.domains.auf_wallet import format_auf_units
from velvet_bot.domains.media_generation.model_catalog import media_model_display_name
from velvet_bot.infrastructure.media_delivery_runtime import redeliver_owned_task
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback
from velvet_bot.presentation.telegram.routers.workspace_auf_video import edit_or_answer

_INSTALLED = False
_VIDEO_MODELS = frozenset(
    {
        "grok_imagine_video",
        "grok_imagine_video_15",
        "seedance_15_pro_video",
        "wan_26_image_to_video",
    }
)
_TASK_STATUS = {
    "queued": "⏳ в очереди",
    "running": "⚙️ выполняется",
    "success": "✅ готово",
    "error": "❌ ошибка",
    "cancelled": "🚫 отменено",
}
_CHARGE_STATUS = {
    "reserved": "зарезервировано",
    "captured": "списано",
    "refunded": "возвращено после ошибки",
    "released": "возвращено после отмены",
}
_INPUT_MODE_NAMES = {
    "text": "Только текст",
    "photo": "Только фото",
    "photo_text": "Фото + текст",
}


@dataclass(frozen=True, slots=True)
class MediaTaskDeliveryView:
    task_id: UUID
    status: str
    model_name: str
    media_kind: str
    input_mode: str
    resolution: str
    created_at: datetime
    quoted_units: int
    charge_status: str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "MediaTaskDeliveryView":
        payload = task_payload_mapping(row.get("payload"))
        request = task_payload_mapping(payload.get("request"))
        model_alias = str(request.get("model") or "").strip()
        input_mode = str(request.get("input_mode") or "").strip()
        return cls(
            task_id=UUID(str(row["id"])),
            status=str(row.get("status") or ""),
            model_name=media_model_display_name(model_alias),
            media_kind=("Видео" if model_alias in _VIDEO_MODELS else "Изображение"),
            input_mode=_INPUT_MODE_NAMES.get(
                input_mode,
                input_mode.replace("_", " ").title(),
            ),
            resolution=str(request.get("resolution") or "").strip(),
            created_at=row["created_at"],
            quoted_units=_integer(row.get("quoted_units")),
            charge_status=str(row.get("charge_status") or ""),
        )


def delivery_callback(*, workspace_id: int, task_id: UUID) -> str:
    return AufCallback(
        action="deliver",
        workspace_id=int(workspace_id),
        value=str(task_id),
    ).pack()


def task_card_text(view: MediaTaskDeliveryView, *, offset: int) -> str:
    lines = [
        "<b>🧾 Мои задачи Ауф</b>",
        "<i>Последняя задача</i>" if offset == 0 else f"<i>Задача {offset + 1} в истории</i>",
        "",
        f"<b>{escape(view.model_name)}</b>",
        f"Статус: {_TASK_STATUS.get(view.status, escape(view.status))}",
        f"Тип: <b>{view.media_kind}</b>",
    ]
    if view.input_mode:
        lines.append(f"Режим: <b>{escape(view.input_mode)}</b>")
    if view.resolution:
        lines.append(f"Качество: <b>{escape(view.resolution)}</b>")
    lines.extend(
        [
            f"Создана: <b>{view.created_at.strftime('%d.%m %H:%M')}</b>",
            f"ID: <code>{str(view.task_id)[:8]}</code>",
            "",
        ]
    )
    if view.quoted_units > 0:
        charge = _CHARGE_STATUS.get(
            view.charge_status,
            view.charge_status or "учтено",
        )
        lines.extend(
            [
                f"Стоимость: <b>{format_auf_units(view.quoted_units)}</b>",
                f"Расчёт: <b>{escape(charge)}</b>",
            ]
        )
    else:
        lines.extend(("Тип учёта: <b>личная задача</b>", "Списаний Ауф: <b>нет</b>"))
    lines.append("")
    if view.status == "success":
        lines.extend(
            (
                "Нажмите <b>«Получить результат»</b>, чтобы повторно отправить "
                "уже готовый файл.",
                "<i>Новая генерация и новое списание не запускаются.</i>",
            )
        )
    elif view.status in {"queued", "running"}:
        lines.append("Задача ещё выполняется. Обновите карточку позже.")
    else:
        lines.append("Для этой задачи готового результата нет.")
    return "\n".join(lines)


def task_card_keyboard(
    *,
    view: MediaTaskDeliveryView | None,
    workspace_id: int,
    offset: int,
    has_older: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if view is not None and view.status == "success":
        rows.append(
            [
                InlineKeyboardButton(
                    text="📥 Получить результат",
                    callback_data=delivery_callback(
                        workspace_id=workspace_id,
                        task_id=view.task_id,
                    ),
                )
            ]
        )
    navigation: list[InlineKeyboardButton] = []
    if offset > 0:
        navigation.append(
            InlineKeyboardButton(
                text="← Новее",
                callback_data=_history_callback(
                    workspace_id=workspace_id,
                    offset=offset - 1,
                ),
            )
        )
    if has_older:
        navigation.append(
            InlineKeyboardButton(
                text="Старее →",
                callback_data=_history_callback(
                    workspace_id=workspace_id,
                    offset=offset + 1,
                ),
            )
        )
    if navigation:
        rows.append(navigation)
    rows.extend(
        (
            [
                InlineKeyboardButton(
                    text="🔄 Обновить карточку",
                    callback_data=_history_callback(
                        workspace_id=workspace_id,
                        offset=offset,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Кошелёк",
                    callback_data=AufCallback(
                        action="wallet",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ],
        )
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_user_task_card(
    callback: Any,
    *,
    state: Any,
    database: Any,
    workspace_id: int,
    offset: int,
) -> None:
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    await state.clear()
    normalized_offset = max(0, int(offset))
    rows = await portal.load_user_tasks(
        database,
        workspace_id=workspace_id,
        actor_user_id=callback.from_user.id,
        offset=normalized_offset,
    )
    row = rows[0] if rows else None
    view = MediaTaskDeliveryView.from_row(row) if row is not None else None
    await edit_or_answer(
        callback,
        text=(
            task_card_text(view, offset=normalized_offset)
            if view is not None
            else "<b>🧾 Мои задачи Ауф</b>\n\nЗадач пока нет."
        ),
        reply_markup=task_card_keyboard(
            view=view,
            workspace_id=workspace_id,
            offset=normalized_offset,
            has_older=len(rows) > 1,
        ),
    )


def install_media_delivery_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    controller = importlib.import_module(
        "velvet_bot.presentation.telegram.workspace_home_controller"
    )
    original_action = controller.handle_scoped_auf_action

    async def handle_delivery_action(
        callback,
        callback_data,
        state,
        access_policy,
        kie_settings,
        database,
        ai_usage_service,
        ai_task_queue_service,
        auf_runtime_service,
        auf_wallet_service,
        auf_purchase_service,
    ) -> None:
        if callback_data.action != "deliver":
            await original_action(
                callback,
                callback_data,
                state,
                access_policy,
                kie_settings,
                database,
                ai_usage_service,
                ai_task_queue_service,
                auf_runtime_service,
                auf_wallet_service,
                auf_purchase_service,
            )
            return
        if not await controller.require_auf_callback(
            callback,
            workspace_id=callback_data.workspace_id,
            service=auf_runtime_service,
        ):
            return
        await redeliver_owned_task(
            callback,
            database=database,
            workspace_id=int(callback_data.workspace_id),
            task_id_text=str(callback_data.value or ""),
        )

    portal.install_user_tasks_renderer(render_user_task_card)
    controller.install_scoped_auf_handlers(action_handler=handle_delivery_action)
    _INSTALLED = True


def _history_callback(*, workspace_id: int, offset: int) -> str:
    return AufCallback(
        action="wallet_tasks",
        workspace_id=int(workspace_id),
        offset=max(0, int(offset)),
    ).pack()


def _integer(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


__all__ = (
    "MediaTaskDeliveryView",
    "delivery_callback",
    "install_media_delivery_ui",
    "render_user_task_card",
    "task_card_keyboard",
    "task_card_text",
)
