from __future__ import annotations

from html import escape
from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.domains.auf_runtime import (
    AUF_WORKSPACE_ACTION,
    AufProvider,
    AufRuntimeAccessError,
    AufRuntimeService,
)
from velvet_bot.presentation.telegram.routers.workspace_meow import MeowCallback
from velvet_bot.workspace_ui import workspace_callback


class AufRuntimeCallback(CallbackData, prefix="mrt"):
    """Runtime callback payload; the prefix is stable for sent keyboards."""

    action: str
    workspace_id: int = 0
    value: str = ""


class AufRuntimeForm(StatesGroup):
    waiting_limit = State()


# Compatibility aliases for imports from stacked branches.
AufRuntimeCallback = AufRuntimeCallback
AufRuntimeForm = AufRuntimeForm


def _callback(action: str, *, workspace_id: int, value: str = "") -> str:
    return AufRuntimeCallback(
        action=action,
        workspace_id=workspace_id,
        value=value,
    ).pack()


def build_task_cancel_keyboard(
    *,
    workspace_id: int,
    task_id: UUID | str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⛔ Отменить задачу",
                    callback_data=_callback(
                        "cancel_task",
                        workspace_id=workspace_id,
                        value=str(task_id),
                    ),
                )
            ]
        ]
    )


def _runtime_keyboard(
    *,
    workspace_id: int,
    global_owner: bool,
    configured: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if global_owner:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="Изменить Kie",
                        callback_data=_callback(
                            "limit_input",
                            workspace_id=workspace_id,
                            value=AufProvider.KIE.value,
                        ),
                    ),
                    InlineKeyboardButton(
                        text="Изменить GRS",
                        callback_data=_callback(
                            "limit_input",
                            workspace_id=workspace_id,
                            value=AufProvider.GRS.value,
                        ),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Применить 100 / 100",
                        callback_data=_callback(
                            "max_limits",
                            workspace_id=workspace_id,
                        ),
                    )
                ],
            ]
        )
        if not configured:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="✅ Подтвердить",
                        callback_data=_callback(
                            "confirm",
                            workspace_id=workspace_id,
                        ),
                    )
                ]
            )
    else:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text=str(value),
                        callback_data=_callback(
                            "workspace_limit",
                            workspace_id=workspace_id,
                            value=str(value),
                        ),
                    )
                    for value in (1, 5, 10)
                ],
                [
                    InlineKeyboardButton(
                        text=str(value),
                        callback_data=_callback(
                            "workspace_limit",
                            workspace_id=workspace_id,
                            value=str(value),
                        ),
                    )
                    for value in (15, 20)
                ],
                [
                    InlineKeyboardButton(
                        text="Ввести своё число",
                        callback_data=_callback(
                            "limit_input",
                            workspace_id=workspace_id,
                            value="workspace",
                        ),
                    )
                ],
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Ауф",
                callback_data=workspace_callback(
                    AUF_WORKSPACE_ACTION,
                    workspace_id=workspace_id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _runtime_text(
    *,
    workspace_id: int,
    user_id: int,
    service: AufRuntimeService,
) -> tuple[str, bool, bool]:
    await service.require_workspace_access(
        workspace_id=workspace_id,
        actor_user_id=user_id,
    )
    workspace = await service.workspace_settings(
        workspace_id=workspace_id,
        actor_user_id=user_id,
    )
    global_owner = service.is_global_owner(user_id)
    if not global_owner:
        return (
            "<b>⚙️ Ауф · параллельность пространства</b>\n\n"
            f"Одновременно может работать: <b>{workspace.concurrency_limit}</b> задач.\n"
            "Допустимый диапазон: <b>1–20</b>. Остальные запросы сохраняются "
            "в очереди.\n\nГлобальные пределы Kie и GRS управляются Стэл.",
            False,
            True,
        )

    runtime = await service.runtime_settings(actor_user_id=user_id)
    snapshots = await service.provider_snapshots(actor_user_id=user_id)
    status = "\n".join(
        f"• {item.provider.display_name}: <b>{item.running}</b> работает, "
        f"<b>{item.queued}</b> ожидает"
        for item in snapshots
    )
    text = (
        "<b>⚙️ Ауф · параллельность</b>\n\n"
        f"Kie.ai: <b>{runtime.kie_concurrency_limit}/100</b>\n"
        f"GRS AI: <b>{runtime.grs_concurrency_limit}/100</b>\n"
        f"Лимит нового пространства: <b>{runtime.workspace_default_limit}</b>\n"
        f"Максимум пространства: <b>{runtime.workspace_max_limit}</b>\n"
        f"Первичная настройка: <b>{'подтверждена' if runtime.configured else 'ожидает подтверждения'}</b>\n\n"
        f"{status}\n\n"
        "Стэл получает следующий освободившийся слот раньше. Уже работающие "
        "задачи владельцев пространств не прерываются."
    )
    return text, True, runtime.configured


async def _render_runtime(
    callback: CallbackQuery,
    *,
    workspace_id: int,
    service: AufRuntimeService,
) -> None:
    try:
        text, global_owner, configured = await _runtime_text(
            workspace_id=workspace_id,
            user_id=callback.from_user.id,
            service=service,
        )
    except (AufRuntimeAccessError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text,
            reply_markup=_runtime_keyboard(
                workspace_id=workspace_id,
                global_owner=global_owner,
                configured=configured,
            ),
        )
    await callback.answer()


async def handle_auf_runtime_action(
    callback: CallbackQuery,
    callback_data: MeowCallback,
    state: FSMContext,
    meow_runtime_service: AufRuntimeService,
) -> None:
    workspace_id = callback_data.workspace_id
    if callback_data.action == "runtime":
        await state.clear()
        await _render_runtime(
            callback,
            workspace_id=workspace_id,
            service=meow_runtime_service,
        )
        return
    if callback_data.action != "visibility_toggle":
        await callback.answer("Неизвестное действие настроек Ауф.", show_alert=True)
        return
    current = await meow_runtime_service.module_is_visible(
        workspace_id=workspace_id,
        actor_user_id=callback.from_user.id,
    )
    try:
        visible = await meow_runtime_service.set_module_visible(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
            is_visible=not current,
        )
    except AufRuntimeAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer(
        "Ауф показан в вашем меню."
        if visible
        else "Ауф скрыт только в вашем меню.",
        show_alert=True,
    )


async def _cancel_task(
    callback: CallbackQuery,
    *,
    value: str,
    service: AufRuntimeService,
) -> None:
    try:
        task_id = UUID(value)
    except ValueError:
        await callback.answer("Некорректный идентификатор задачи.", show_alert=True)
        return
    try:
        result = await service.request_cancellation(
            task_id=task_id,
            actor_user_id=callback.from_user.id,
        )
    except (PermissionError, AufRuntimeAccessError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    if result is None:
        text = "Задача не найдена."
    elif result.status == "cancelled":
        text = "Задача отменена до отправки провайдеру."
    elif result.status == "running":
        text = (
            "Остановка запрошена. Если провайдер уже создаёт результат, бот всё "
            "равно пришлёт готовый файл. Новая платная попытка после ошибки не запускается."
        )
    else:
        text = f"Задача уже имеет статус: {result.status}."
    await callback.answer(text, show_alert=True)


async def handle_auf_runtime_callback(
    callback: CallbackQuery,
    callback_data: AufRuntimeCallback,
    state: FSMContext,
    meow_runtime_service: AufRuntimeService,
) -> None:
    action = callback_data.action
    workspace_id = callback_data.workspace_id
    user_id = callback.from_user.id
    if action == "cancel_task":
        await _cancel_task(
            callback,
            value=callback_data.value,
            service=meow_runtime_service,
        )
        return
    if action == "max_limits":
        try:
            for provider in AufProvider:
                await meow_runtime_service.set_provider_limit(
                    actor_user_id=user_id,
                    provider=provider,
                    limit=100,
                )
        except AufRuntimeAccessError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await _render_runtime(
            callback,
            workspace_id=workspace_id,
            service=meow_runtime_service,
        )
        return
    if action == "confirm":
        try:
            await meow_runtime_service.confirm_runtime_settings(
                actor_user_id=user_id
            )
        except AufRuntimeAccessError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await _render_runtime(
            callback,
            workspace_id=workspace_id,
            service=meow_runtime_service,
        )
        return
    if action == "workspace_limit":
        try:
            await meow_runtime_service.set_workspace_limit(
                workspace_id=workspace_id,
                actor_user_id=user_id,
                limit=int(callback_data.value),
            )
        except (ValueError, AufRuntimeAccessError) as error:
            await callback.answer(str(error), show_alert=True)
            return
        await _render_runtime(
            callback,
            workspace_id=workspace_id,
            service=meow_runtime_service,
        )
        return
    if action != "limit_input":
        await callback.answer("Неизвестная команда runtime Ауф.", show_alert=True)
        return

    await state.set_state(AufRuntimeForm.waiting_limit)
    await state.update_data(
        auf_runtime_workspace_id=workspace_id,
        auf_runtime_limit_target=callback_data.value,
    )
    if isinstance(callback.message, Message):
        maximum = 20 if callback_data.value == "workspace" else 100
        await callback.message.edit_text(
            "<b>Введите лимит</b>\n\n"
            f"Отправьте целое число от 1 до {maximum}.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ Назад",
                            callback_data=MeowCallback(
                                action="runtime",
                                workspace_id=workspace_id,
                            ).pack(),
                        )
                    ]
                ]
            ),
        )
    await callback.answer()


async def handle_auf_runtime_limit_input(
    message: Message,
    state: FSMContext,
    meow_runtime_service: AufRuntimeService,
) -> None:
    data = await state.get_data()
    workspace_id = int(
        data.get("auf_runtime_workspace_id")
        or data.get("meow_runtime_workspace_id")
        or 0
    )
    target = str(
        data.get("auf_runtime_limit_target")
        or data.get("meow_runtime_limit_target")
        or ""
    )
    try:
        limit = int((message.text or "").strip())
        if target == "workspace":
            settings = await meow_runtime_service.set_workspace_limit(
                workspace_id=workspace_id,
                actor_user_id=message.from_user.id,
                limit=limit,
            )
            result = (
                "Лимит пространства установлен: "
                f"<b>{settings.concurrency_limit}</b>."
            )
        else:
            provider = AufProvider(target)
            settings = await meow_runtime_service.set_provider_limit(
                actor_user_id=message.from_user.id,
                provider=provider,
                limit=limit,
            )
            result = (
                f"Лимит {escape(provider.display_name)} установлен: "
                f"<b>{settings.limit_for(provider)}</b>."
            )
    except (ValueError, AufRuntimeAccessError) as error:
        await message.answer(str(error))
        return
    await state.clear()
    await message.answer(
        result,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="↩️ К настройкам Ауф",
                        callback_data=MeowCallback(
                            action="runtime",
                            workspace_id=workspace_id,
                        ).pack(),
                    )
                ]
            ]
        ),
    )


# Existing router registration imports the historical handler names.
handle_auf_runtime_action = handle_auf_runtime_action
handle_auf_runtime_callback = handle_auf_runtime_callback
handle_auf_runtime_limit_input = handle_auf_runtime_limit_input


__all__ = (
    "AufRuntimeCallback",
    "AufRuntimeForm",
    "AufRuntimeCallback",
    "AufRuntimeForm",
    "build_task_cancel_keyboard",
    "handle_auf_runtime_action",
    "handle_auf_runtime_callback",
    "handle_auf_runtime_limit_input",
    "handle_auf_runtime_action",
    "handle_auf_runtime_callback",
    "handle_auf_runtime_limit_input",
)
