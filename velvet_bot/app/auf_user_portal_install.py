from __future__ import annotations

from velvet_bot.application.media_tasks import task_payload_mapping
from velvet_bot.application.workspace_tasks import list_owned_workspace_tasks
from velvet_bot.domains.media_generation.model_catalog import (
    MODEL_DISPLAY_NAMES,
    media_model_display_name,
)
from velvet_bot.presentation.telegram.state_compatibility import state_value

import importlib
import json
from collections.abc import Mapping
from html import escape

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AITaskRequest
from velvet_bot.domains.auf_wallet import (
    AufInsufficientBalance,
    AufPriceNotConfigured,
    AufPricingRepository,
    AufWalletFrozen,
    AufWalletStatus,
    format_auf_units,
)
from velvet_bot.domains.media_generation import KIE_GENERATION_TASK_TYPE, KieInputMode
from velvet_bot.presentation.telegram.routers import workspace_auf_wallet as wallet_router
from velvet_bot.presentation.telegram.routers import workspace_auf_video as video_core
from velvet_bot.presentation.telegram.routers import workspace_auf_video_simple as video_router
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback

_INSTALLED = False
TASK_PAGE_SIZE = 8
MODEL_NAMES = MODEL_DISPLAY_NAMES
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


def _video_review_keyboard(
    *, workspace_id: int, quoted_units: int, can_submit: bool
) -> InlineKeyboardMarkup:
    first_button = InlineKeyboardButton(
        text=(
            f"Запустить · {format_auf_units(quoted_units)}"
            if can_submit
            else "Пересчитать баланс и цену"
        ),
        callback_data=video_router.video_callback(
            "submit" if can_submit else "review",
            workspace_id=workspace_id,
        ),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [first_button],
            [
                InlineKeyboardButton(
                    text="Изменить параметры",
                    callback_data=video_router.video_callback(
                        "settings", workspace_id=workspace_id
                    ),
                ),
                InlineKeyboardButton(
                    text="Изменить модель",
                    callback_data=video_router.video_callback(
                        "models", workspace_id=workspace_id
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=video_router.video_callback(
                        "cancel", workspace_id=workspace_id
                    ),
                )
            ],
        ]
    )


def _wallet_tasks_callback(*, workspace_id: int, offset: int = 0) -> str:
    return AufCallback(
        action="wallet_tasks",
        workspace_id=int(workspace_id),
        offset=max(0, int(offset)),
    ).pack()


def _wallet_keyboard_with_tasks(
    original,
    *,
    workspace_id: int,
    global_owner: bool,
    frozen: bool,
    invoices,
) -> InlineKeyboardMarkup:
    markup = original(
        workspace_id=workspace_id,
        global_owner=global_owner,
        frozen=frozen,
        invoices=invoices,
    )
    rows = [list(row) for row in markup.inline_keyboard]
    rows.insert(
        max(0, len(rows) - 1),
        [
            InlineKeyboardButton(
                text="🧾 Мои задачи",
                callback_data=_wallet_tasks_callback(workspace_id=workspace_id),
            )
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _user_settings_text(original, **kwargs) -> str:
    kwargs["estimated_usd"] = None
    kwargs["estimated_rub"] = None
    kwargs["cost_change"] = None
    return (
        f"{original(**kwargs)}\n\n"
        "Точная цена в Ауф, баланс и остаток будут показаны перед запуском."
    )


def _video_request_from_state(data: Mapping[str, object]):
    reference = video_core.reference_from_data(
        state_value(data, "auf_video_reference")
    )
    last_reference = video_core.reference_from_data(
        state_value(data, "auf_video_last_reference")
    )
    prompt = str(state_value(data, "auf_video_prompt") or "").strip()
    if reference is None or not prompt:
        raise ValueError("Сессия устарела: нужны первый кадр и промт.")

    model = video_router.validated_model(data)
    wan_mode = video_router.validated_wan_mode(data)
    if model == "wan" and wan_mode == "first_last" and last_reference is None:
        raise ValueError("Для этого режима загрузите последний кадр.")

    resolution = video_router.validated_resolution(data, model=model)
    duration = video_router.validated_duration(data, model=model)
    generate_audio = video_router.validated_audio(data, model=model)
    request = video_router.build_request(
        reference=reference,
        last_reference=last_reference,
        prompt=prompt,
        model=model,
        resolution=resolution,
        duration=duration,
        generate_audio=generate_audio,
        wan_mode=wan_mode,
    )
    return (
        request,
        prompt,
        model,
        resolution,
        duration,
        generate_audio,
        wan_mode,
    )


def _wallet_lines(*, wallet, quoted_units: int, global_owner: bool) -> tuple[list[str], bool]:
    if global_owner:
        return (
            [
                f"Учётная цена: <b>{format_auf_units(quoted_units)}</b>",
                "Списание Стэл: <b>0 Ауф</b>",
            ],
            True,
        )
    if wallet.status == AufWalletStatus.FROZEN:
        return (
            [
                f"Цена: <b>{format_auf_units(quoted_units)}</b>",
                "Кошелёк: <b>заморожен</b>",
            ],
            False,
        )
    if wallet.available_units >= quoted_units:
        return (
            [
                f"Цена: <b>{format_auf_units(quoted_units)}</b>",
                f"Доступно: <b>{format_auf_units(wallet.available_units)}</b>",
                "Останется: "
                f"<b>{format_auf_units(wallet.available_units - quoted_units)}</b>",
            ],
            True,
        )
    return (
        [
            f"Цена: <b>{format_auf_units(quoted_units)}</b>",
            f"Доступно: <b>{format_auf_units(wallet.available_units)}</b>",
            "Не хватает: "
            f"<b>{format_auf_units(quoted_units - wallet.available_units)}</b>",
        ],
        False,
    )


async def _show_video_auf_review(
    callback: CallbackQuery,
    *,
    state,
    workspace_id: int,
    database,
    wallet_service,
) -> None:
    try:
        (
            request,
            prompt,
            model,
            resolution,
            duration,
            generate_audio,
            wan_mode,
        ) = _video_request_from_state(await state.get_data())
        quote = await AufPricingRepository(database).quote(
            {"workspace_id": workspace_id, "request": request.to_task_payload()}
        )
        overview = await wallet_service.overview(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
            history_limit=1,
        )
    except (PermissionError, ValueError, RuntimeError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    await state.update_data(
        auf_video_expected_price_version=quote.version_key,
        auf_video_expected_quoted_units=quote.quoted_units,
    )
    wallet_lines, can_submit = _wallet_lines(
        wallet=overview.wallet,
        quoted_units=quote.quoted_units,
        global_owner=wallet_service.is_global_owner(callback.from_user.id),
    )
    lines = [
        "<b>Проверьте видео перед запуском</b>",
        "",
        f"Модель: <b>{escape(video_router.MODEL_NAMES[model])}</b>",
        f"Разрешение: <b>{escape(resolution)}</b>",
        (
            "Длительность: <b>автоматически, расчёт 6 сек</b>"
            if model == "grok"
            else f"Длительность: <b>{duration} сек</b>"
        ),
    ]
    if model == "seedance":
        lines.append(
            f"Звук: <b>{'включён' if generate_audio else 'выключен'}</b>"
        )
    if model == "wan":
        lines.append(f"Кадры: <b>{video_router.wan_mode_name(wan_mode)}</b>")
    lines.extend(
        [
            "",
            "<b>Стоимость в Ауф</b>",
            *wallet_lines,
            "",
            f"<b>Движение и сцена</b>\n{escape(video_core.truncate_text(prompt, 3500))}",
            "",
            "<i>Цена фиксируется при подтверждении. Если тариф изменится до "
            "резервирования, бот попросит подтвердить новую сумму.</i>",
        ]
    )
    await state.set_state(video_router.AufVideoForm.reviewing)
    await video_core.edit_or_answer(
        callback,
        text="\n".join(lines),
        reply_markup=_video_review_keyboard(
            workspace_id=workspace_id,
            quoted_units=quote.quoted_units,
            can_submit=can_submit,
        ),
    )


async def _submit_video_with_auf(
    callback: CallbackQuery,
    *,
    state,
    workspace_id: int,
    kie_settings,
    ai_usage_service,
    ai_task_queue_service,
    wallet_service,
) -> None:
    data = await state.get_data()
    session_id = str(state_value(data, "auf_video_session_id") or "").strip()
    expected_version = str(
        data.get("auf_video_expected_price_version") or ""
    ).strip()
    try:
        expected_units = int(data.get("auf_video_expected_quoted_units") or 0)
    except (TypeError, ValueError):
        expected_units = 0
    if not session_id or not expected_version or expected_units <= 0:
        await callback.answer(
            "Цена Ауф устарела. Вернитесь к финальному экрану и подтвердите её снова.",
            show_alert=True,
        )
        return

    try:
        (
            request,
            _prompt,
            model,
            resolution,
            duration,
            generate_audio,
            wan_mode,
        ) = _video_request_from_state(data)
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return

    provider_model = kie_settings.models.provider_model(
        video_router.MODEL_ALIASES[model],
        input_mode=KieInputMode.PHOTO_TEXT,
    )
    if provider_model != video_router.MODEL_EXPECTED_IDS[model]:
        await callback.answer(
            f"Неверный model id {video_router.MODEL_NAMES[model]}: {provider_model}",
            show_alert=True,
        )
        return

    estimated_rub = kie_settings.pricing.estimate_rub(
        request, usd_to_rub=kie_settings.usd_to_rub
    )
    block_reason = video_core.budget_block_reason(
        await ai_usage_service.status(), estimated_cost_rub=estimated_rub
    )
    if block_reason is not None:
        await callback.answer(block_reason, show_alert=True)
        return

    chat_id = callback.message.chat.id if isinstance(callback.message, Message) else None
    try:
        result = await ai_task_queue_service.enqueue(
            AITaskRequest(
                scope=AIBudgetScope.VISION,
                task_type=KIE_GENERATION_TASK_TYPE,
                payload={
                    "request": request.to_task_payload(),
                    "chat_id": chat_id,
                    "user_id": callback.from_user.id,
                    "workspace_id": workspace_id,
                    "delivery_kind": "video",
                    "auf_expected_price_version": expected_version,
                    "auf_expected_quoted_units": expected_units,
                },
                priority=35,
                dedupe_key=f"kie:video:{model}:{session_id}",
                max_attempts=3,
                created_by=callback.from_user.id,
                estimated_cost_rub=estimated_rub,
            )
        )
    except (
        AufInsufficientBalance,
        AufWalletFrozen,
        AufPriceNotConfigured,
        ValueError,
        RuntimeError,
    ) as error:
        await callback.answer(str(error), show_alert=True)
        return

    await state.clear()
    details = [
        f"<b>Ауф · {escape(video_router.MODEL_NAMES[model])}</b>",
        "",
        (
            "Задача поставлена в очередь."
            if result.created
            else "Эта задача уже была поставлена в очередь."
        ),
        "",
        f"Разрешение: <b>{escape(resolution)}</b>",
    ]
    if model != "grok":
        details.append(f"Длительность: <b>{duration} сек</b>")
    if model == "seedance":
        details.append(
            f"Звук: <b>{'включён' if generate_audio else 'выключен'}</b>"
        )
    if model == "wan":
        details.append(f"Кадры: <b>{video_router.wan_mode_name(wan_mode)}</b>")
    if wallet_service.is_global_owner(callback.from_user.id):
        details.append(f"Учётная цена: <b>{format_auf_units(expected_units)}</b>")
    else:
        details.append(
            f"{'Зарезервировано' if result.created else 'Цена'}: "
            f"<b>{format_auf_units(expected_units)}</b>"
        )
    details.append(f"Задача: <code>{result.task.id}</code>")
    await video_core.edit_or_answer(
        callback,
        text="\n".join(details),
        reply_markup=video_router.build_auf_root_keyboard(
            workspace_id=workspace_id, enabled=True
        ),
    )


async def load_user_tasks(
    database,
    *,
    workspace_id: int,
    actor_user_id: int,
    offset: int,
):
    return await list_owned_workspace_tasks(
        database,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        offset=offset,
        page_size=TASK_PAGE_SIZE,
    )


def format_userformat_user_task_line(row) -> str:
    request = task_payload_mapping(task_payload_mapping(row["payload"]).get("request"))
    model_alias = str(request.get("model") or "").strip()
    model = media_model_display_name(model_alias)
    resolution = str(request.get("resolution") or "").strip()
    try:
        duration = int(request.get("duration_seconds") or 0)
    except (TypeError, ValueError):
        duration = 0
    status = _TASK_STATUS.get(str(row["status"]), str(row["status"]))
    quoted_units = int(row["quoted_units"] or 0)
    charge_status = str(row["charge_status"] or "")
    charge = (
        f"{format_auf_units(quoted_units)} · "
        f"{_CHARGE_STATUS.get(charge_status, charge_status or 'учтено')}"
        if quoted_units > 0
        else "без операции Ауф"
    )
    params = [
        value
        for value in (resolution, f"{duration} сек" if duration else "")
        if value
    ]
    created_at = row["created_at"].strftime("%d.%m %H:%M")
    return (
        f"• <b>{escape(model)}</b> · {escape(status)}\n"
        f"  {escape(' · '.join(params) or 'стандартные параметры')} · {escape(charge)}\n"
        f"  <code>{str(row['id'])[:8]}</code> · {created_at}"
    )


def build_userbuild_user_task_list_keyboard(
    *, workspace_id: int, offset: int, has_next: bool
) -> InlineKeyboardMarkup:
    navigation: list[InlineKeyboardButton] = []
    if offset > 0:
        navigation.append(
            InlineKeyboardButton(
                text="← Новее",
                callback_data=_wallet_tasks_callback(
                    workspace_id=workspace_id,
                    offset=max(0, offset - TASK_PAGE_SIZE),
                ),
            )
        )
    if has_next:
        navigation.append(
            InlineKeyboardButton(
                text="Старее →",
                callback_data=_wallet_tasks_callback(
                    workspace_id=workspace_id,
                    offset=offset + TASK_PAGE_SIZE,
                ),
            )
        )
    rows: list[list[InlineKeyboardButton]] = []
    if navigation:
        rows.append(navigation)
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Обновить",
                    callback_data=_wallet_tasks_callback(
                        workspace_id=workspace_id, offset=offset
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Кошелёк",
                    callback_data=AufCallback(
                        action="wallet", workspace_id=workspace_id
                    ).pack(),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_user_tasks(
    callback: CallbackQuery,
    *,
    state,
    database,
    workspace_id: int,
    offset: int,
) -> None:
    await state.clear()
    rows = await _load_user_tasks(
        database,
        workspace_id=workspace_id,
        actor_user_id=callback.from_user.id,
        offset=offset,
    )
    page = rows[:TASK_PAGE_SIZE]
    text = (
        "<b>🧾 Мои задачи Ауф</b>\n\n"
        "Показаны только генерации, созданные вами в этом пространстве. "
        "Системные задачи, другие участники и себестоимость провайдера скрыты.\n\n"
        + (
            "\n\n".join(format_user_task_line(row) for row in page)
            if page
            else "• задач пока нет"
        )
    )
    await video_core.edit_or_answer(
        callback,
        text=text,
        reply_markup=build_user_task_list_keyboard(
            workspace_id=workspace_id,
            offset=offset,
            has_next=len(rows) > TASK_PAGE_SIZE,
        ),
    )


def install_user_tasks_renderer(renderer) -> None:
    """Install a task-list renderer through an explicit public hook."""

    global render_user_tasks
    render_user_tasks = renderer


def install_auf_user_portal() -> None:
    """Expose user-safe Auf video pricing and personal task history."""

    global _INSTALLED
    if _INSTALLED:
        return

    controller = importlib.import_module(
        "velvet_bot.presentation.telegram.workspace_home_controller"
    )
    original_action = controller.handle_scoped_auf_action
    original_video_action = controller.handle_scoped_auf_video_action
    original_wallet_keyboard = wallet_router.wallet_keyboard
    original_settings_text = video_router.settings_text

    def wallet_keyboard_with_tasks(
        *, workspace_id: int, global_owner: bool, frozen: bool, invoices
    ) -> InlineKeyboardMarkup:
        return _wallet_keyboard_with_tasks(
            original_wallet_keyboard,
            workspace_id=workspace_id,
            global_owner=global_owner,
            frozen=frozen,
            invoices=invoices,
        )

    def user_settings_text(**kwargs) -> str:
        return _user_settings_text(original_settings_text, **kwargs)

    async def handle_scoped_auf_user_action(
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
        if callback_data.action == "wallet_tasks":
            if not await controller.require_auf_callback(
                callback,
                workspace_id=callback_data.workspace_id,
                service=auf_runtime_service,
            ):
                return
            await render_user_tasks(
                callback,
                state=state,
                database=database,
                workspace_id=int(callback_data.workspace_id),
                offset=max(0, int(callback_data.offset)),
            )
            return
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

    async def handle_scoped_auf_user_video_action(
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
    ) -> None:
        if callback_data.action not in {"review", "submit"}:
            await original_video_action(
                callback,
                callback_data,
                state,
                access_policy,
                kie_settings,
                database,
                ai_usage_service,
                ai_task_queue_service,
                auf_runtime_service,
            )
            return
        if not await controller.require_auf_callback(
            callback,
            workspace_id=callback_data.workspace_id,
            service=auf_runtime_service,
        ):
            return
        if not kie_settings.enabled:
            await state.clear()
            await callback.answer("Kie.ai выключен на сервере.", show_alert=True)
            return
        if callback_data.action == "review":
            await _show_video_auf_review(
                callback,
                state=state,
                workspace_id=int(callback_data.workspace_id),
                database=database,
                wallet_service=auf_wallet_service,
            )
            return
        await _submit_video_with_auf(
            callback,
            state=state,
            workspace_id=int(callback_data.workspace_id),
            kie_settings=kie_settings,
            ai_usage_service=ai_usage_service,
            ai_task_queue_service=ai_task_queue_service,
            wallet_service=auf_wallet_service,
        )

    wallet_router.wallet_keyboard = wallet_keyboard_with_tasks
    video_router.settings_text = user_settings_text
    controller.handle_scoped_auf_action = handle_scoped_auf_user_action
    controller.handle_scoped_auf_video_action = handle_scoped_auf_user_video_action
    _INSTALLED = True


__all__ = (
    "MODEL_NAMES",
    "TASK_PAGE_SIZE",
    "build_user_task_list_keyboard",
    "format_user_task_line",
    "install_auf_user_portal",
    "install_user_tasks_renderer",
    "load_user_tasks",
    "render_user_tasks",
)
