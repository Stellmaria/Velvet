from __future__ import annotations

from decimal import Decimal
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.domains.ai_usage import (
    AIBudgetStatus,
    AITaskQueueService,
    AITaskRequest,
    AIUsageService,
)
from velvet_bot.domains.media_generation import (
    KIE_GENERATION_TASK_TYPE,
    KieGenerationRequest,
    KieModelAlias,
)
from velvet_bot.workspace_ui import WorkspaceCallback, workspace_callback

router = Router(name=__name__)


class MeowCallback(CallbackData, prefix="meow"):
    action: str
    workspace_id: int = 0
    model: str = ""


class MeowForm(StatesGroup):
    waiting_prompt = State()


def build_meow_menu_keyboard(
    *,
    workspace_id: int,
    enabled: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if enabled:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="Seedream 5 Pro",
                        callback_data=MeowCallback(
                            action="model",
                            workspace_id=workspace_id,
                            model=KieModelAlias.SEEDREAM_5_PRO.value,
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Nano Banana Pro",
                        callback_data=MeowCallback(
                            action="model",
                            workspace_id=workspace_id,
                            model=KieModelAlias.NANO_BANANA_PRO.value,
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Grok Imagine Video",
                        callback_data=MeowCallback(
                            action="model",
                            workspace_id=workspace_id,
                            model=KieModelAlias.GROK_IMAGINE_VIDEO.value,
                        ).pack(),
                    )
                ],
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


def build_meow_confirm_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Запустить генерацию",
                    callback_data=MeowCallback(
                        action="confirm",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=MeowCallback(
                        action="cancel",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ],
        ]
    )


def build_meow_cancel_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=MeowCallback(
                        action="cancel",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ]
        ]
    )


def default_meow_request(
    model: KieModelAlias,
    *,
    prompt: str,
) -> KieGenerationRequest:
    if model is KieModelAlias.SEEDREAM_5_PRO:
        return KieGenerationRequest(
            model=model,
            prompt=prompt,
            aspect_ratio="9:16",
            quality="basic",
        )
    if model is KieModelAlias.NANO_BANANA_PRO:
        return KieGenerationRequest(
            model=model,
            prompt=prompt,
            aspect_ratio="9:16",
            resolution="2K",
            output_format="png",
        )
    return KieGenerationRequest(
        model=model,
        prompt=prompt,
        aspect_ratio="9:16",
        resolution="720p",
        duration_seconds=6,
        mode="normal",
    )


def format_meow_preview(
    request: KieGenerationRequest,
    *,
    estimated_usd: Decimal,
    estimated_rub: Decimal,
    budget_status: AIBudgetStatus,
) -> str:
    if request.model.is_video:
        settings = (
            f"Формат: <b>{escape(request.aspect_ratio)}</b> · "
            f"{escape(request.resolution)} · {request.duration_seconds} сек."
        )
    elif request.model is KieModelAlias.SEEDREAM_5_PRO:
        settings = (
            f"Формат: <b>{escape(request.aspect_ratio)}</b> · "
            f"качество {escape(request.quality)}"
        )
    else:
        settings = (
            f"Формат: <b>{escape(request.aspect_ratio)}</b> · "
            f"{escape(request.resolution)} · {escape(request.output_format)}"
        )
    budget_line = (
        "AI-бюджет: <b>приостановлен</b>"
        if budget_status.paused
        else (
            "Остаток сегодня: "
            f"<b>{_format_rub(budget_status.daily_remaining_rub)}</b>"
        )
    )
    return (
        f"<b>Мяу · {escape(request.model.title)}</b>\n\n"
        f"{settings}\n"
        f"Себестоимость: <b>{_format_usd(estimated_usd)}</b> · "
        f"<b>{_format_rub(estimated_rub)}</b>\n"
        f"{budget_line}\n\n"
        f"<b>Промт</b>\n{escape(request.prompt)}\n\n"
        "Платный запрос начнётся только после подтверждения."
    )


async def _edit_or_answer(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await callback.message.answer(text, reply_markup=reply_markup)
    await callback.answer()


def _is_owner(callback: CallbackQuery, access_policy: AccessPolicy) -> bool:
    return access_policy.allows_user(callback.from_user)


def _parse_model(value: str) -> KieModelAlias | None:
    try:
        return KieModelAlias(value)
    except ValueError:
        return None


def _budget_block_reason(
    status: AIBudgetStatus,
    *,
    estimated_cost_rub: Decimal,
) -> str | None:
    if status.paused:
        reason = status.pause_reason or "без указанной причины"
        return f"AI-контур приостановлен: {reason}"
    if not status.enabled:
        return None
    if estimated_cost_rub > status.max_request_rub:
        return "Стоимость превышает лимит одного AI-запроса."
    if estimated_cost_rub > status.daily_remaining_rub:
        return "Недостаточно дневного AI-бюджета."
    if estimated_cost_rub > status.ordinary_month_remaining_rub:
        return "Недостаточно месячного AI-бюджета без резерва Hermes."
    return None


@router.callback_query(WorkspaceCallback.filter(F.action == "meow"))
async def handle_meow_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
) -> None:
    if not _is_owner(callback, access_policy):
        await callback.answer("Мяу доступен только владельцу бота.", show_alert=True)
        return
    await state.clear()
    if kie_settings.enabled:
        text = (
            "<b>Мяу</b>\n\n"
            "Личная генерация через Kie.ai. Выберите модель. "
            "Перед запуском бот покажет себестоимость и попросит подтверждение."
        )
    else:
        text = (
            "<b>Мяу</b>\n\n"
            "Интерфейс установлен, но Kie.ai пока выключен на сервере. "
            "Нужно заполнить KIE_API_KEY, KIE_USD_TO_RUB и model id Seedream 5 Pro."
        )
    await _edit_or_answer(
        callback,
        text=text,
        reply_markup=build_meow_menu_keyboard(
            workspace_id=callback_data.workspace_id,
            enabled=kie_settings.enabled,
        ),
    )


@router.callback_query(MeowCallback.filter(F.action == "model"))
async def handle_meow_model(
    callback: CallbackQuery,
    callback_data: MeowCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
) -> None:
    if not _is_owner(callback, access_policy):
        await callback.answer("Мяу доступен только владельцу бота.", show_alert=True)
        return
    if not kie_settings.enabled:
        await callback.answer("Kie.ai выключен на сервере.", show_alert=True)
        return
    model = _parse_model(callback_data.model)
    if model is None:
        await callback.answer("Неизвестная модель.", show_alert=True)
        return
    try:
        kie_settings.models.provider_model(model)
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.set_state(MeowForm.waiting_prompt)
    await state.update_data(
        meow_model=model.value,
        meow_workspace_id=callback_data.workspace_id,
    )
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"<b>Мяу · {escape(model.title)}</b>\n\n"
            "Отправьте промт одним текстовым сообщением. "
            "Формат по умолчанию: 9:16.",
            reply_markup=build_meow_cancel_keyboard(
                workspace_id=callback_data.workspace_id,
            ),
        )
    await callback.answer()


@router.message(MeowForm.waiting_prompt, F.text)
async def handle_meow_prompt(
    message: Message,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
    ai_usage_service: AIUsageService,
) -> None:
    if not access_policy.allows_user(message.from_user):
        await state.clear()
        return
    if not kie_settings.enabled:
        await state.clear()
        await message.answer("Kie.ai выключен на сервере.")
        return
    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer("Промт не может быть пустым.")
        return
    if len(prompt) > 8000:
        await message.answer("Промт слишком длинный. Максимум 8000 символов.")
        return
    data = await state.get_data()
    model = _parse_model(str(data.get("meow_model") or ""))
    workspace_id = _optional_int(data.get("meow_workspace_id")) or 0
    if model is None:
        await state.clear()
        await message.answer("Сессия Мяу устарела. Откройте кнопку заново.")
        return
    request = default_meow_request(model, prompt=prompt)
    estimated_usd = kie_settings.pricing.estimate_usd(request)
    estimated_rub = kie_settings.pricing.estimate_rub(
        request,
        usd_to_rub=kie_settings.usd_to_rub,
    )
    budget_status = await ai_usage_service.status()
    await state.update_data(meow_prompt=prompt)
    await message.answer(
        format_meow_preview(
            request,
            estimated_usd=estimated_usd,
            estimated_rub=estimated_rub,
            budget_status=budget_status,
        ),
        reply_markup=build_meow_confirm_keyboard(workspace_id=workspace_id),
    )


@router.callback_query(MeowCallback.filter(F.action == "confirm"))
async def handle_meow_confirm(
    callback: CallbackQuery,
    callback_data: MeowCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    if not _is_owner(callback, access_policy):
        await callback.answer("Мяу доступен только владельцу бота.", show_alert=True)
        return
    if not kie_settings.enabled:
        await callback.answer("Kie.ai выключен на сервере.", show_alert=True)
        return
    data = await state.get_data()
    model = _parse_model(str(data.get("meow_model") or ""))
    prompt = str(data.get("meow_prompt") or "").strip()
    if model is None or not prompt:
        await state.clear()
        await callback.answer("Сессия Мяу устарела.", show_alert=True)
        return
    request = default_meow_request(model, prompt=prompt)
    estimated_rub = kie_settings.pricing.estimate_rub(
        request,
        usd_to_rub=kie_settings.usd_to_rub,
    )
    budget_status = await ai_usage_service.status()
    block_reason = _budget_block_reason(
        budget_status,
        estimated_cost_rub=estimated_rub,
    )
    if block_reason is not None:
        await callback.answer(block_reason, show_alert=True)
        return
    result = await ai_task_queue_service.enqueue(
        AITaskRequest(
            scope=AIBudgetScope.VISION,
            task_type=KIE_GENERATION_TASK_TYPE,
            payload={
                "request": request.to_task_payload(),
                "chat_id": callback.message.chat.id if callback.message else None,
                "user_id": callback.from_user.id,
                "workspace_id": callback_data.workspace_id,
            },
            priority=40,
            max_attempts=3,
            created_by=callback.from_user.id,
            estimated_cost_rub=estimated_rub,
        )
    )
    await state.clear()
    await _edit_or_answer(
        callback,
        text=(
            f"<b>Мяу · {escape(model.title)}</b>\n\n"
            "Задача поставлена в очередь. Платный вызов произойдёт только после "
            "атомарной проверки бюджета worker-ом.\n\n"
            f"Задача: <code>{result.task.id}</code>\n"
            f"Себестоимость: <b>{_format_rub(estimated_rub)}</b>"
        ),
        reply_markup=build_meow_menu_keyboard(
            workspace_id=callback_data.workspace_id,
            enabled=True,
        ),
    )


@router.callback_query(MeowCallback.filter(F.action == "cancel"))
async def handle_meow_cancel(
    callback: CallbackQuery,
    callback_data: MeowCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
) -> None:
    if not _is_owner(callback, access_policy):
        await callback.answer()
        return
    await state.clear()
    await _edit_or_answer(
        callback,
        text="<b>Мяу</b>\n\nГенерация отменена. Выберите модель для новой задачи.",
        reply_markup=build_meow_menu_keyboard(
            workspace_id=callback_data.workspace_id,
            enabled=kie_settings.enabled,
        ),
    )


def _format_rub(value: Decimal) -> str:
    normalized = f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")
    return f"{normalized} ₽"


def _format_usd(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    return f"${normalized}"


def _optional_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


__all__ = (
    "MeowCallback",
    "MeowForm",
    "build_meow_confirm_keyboard",
    "build_meow_menu_keyboard",
    "default_meow_request",
    "format_meow_preview",
    "router",
)
