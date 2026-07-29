from __future__ import annotations

from decimal import Decimal
from html import escape

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AITaskQueueService, AITaskRequest, AIUsageService
from velvet_bot.domains.media_generation import (
    KIE_GENERATION_TASK_TYPE,
    KieContentMode,
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieReferenceImage,
)
from velvet_bot.presentation.telegram.routers import workspace_meow_video as legacy
from velvet_bot.presentation.telegram.routers.workspace_meow import build_meow_root_keyboard

MeowVideoCallback = legacy.MeowVideoCallback
MeowVideoForm = legacy.MeowVideoForm
handle_meow_video_entry = legacy.handle_meow_video_entry
handle_meow_video_reference_message = legacy.handle_meow_video_reference_message

_GROK_V1_MODEL_ID = "grok-imagine/image-to-video"
_VIDEO_RESOLUTIONS = ("480p", "720p")
_PROVIDER_PRICING_DURATION_SECONDS = 6
_MAX_PROMPT_LENGTH = 5000


def build_video_quality_keyboard(
    *,
    workspace_id: int,
    resolution: str,
) -> InlineKeyboardMarkup:
    def selected(label: str, active: bool) -> str:
        return f"✓ {label}" if active else label

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=selected(item, item == resolution),
                    callback_data=legacy._callback(
                        "resolution",
                        workspace_id=workspace_id,
                        value=item,
                    ),
                )
                for item in _VIDEO_RESOLUTIONS
            ],
            [
                InlineKeyboardButton(
                    text="Изменить фото",
                    callback_data=legacy._callback(
                        "change_photo",
                        workspace_id=workspace_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="Изменить текст",
                    callback_data=legacy._callback(
                        "change_prompt",
                        workspace_id=workspace_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=legacy._callback(
                        "cancel",
                        workspace_id=workspace_id,
                    ),
                )
            ],
        ]
    )


def build_video_review_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Запустить видео",
                    callback_data=legacy._callback(
                        "submit",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить качество",
                    callback_data=legacy._callback(
                        "settings",
                        workspace_id=workspace_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=legacy._callback(
                        "cancel",
                        workspace_id=workspace_id,
                    ),
                ),
            ],
        ]
    )


def _quality_text(*, resolution: str) -> str:
    return (
        "<b>Мяу · Оживить</b>\n\n"
        "Выберите качество видео. Остальные параметры Grok определит сам по "
        "исходному фото и описанию движения.\n\n"
        f"Текущее качество: <b>{escape(resolution)}</b>\n"
        "Фильтр Kie: <b>выключен</b>."
    )


def _review_text(
    *,
    prompt: str,
    resolution: str,
    estimated_usd: Decimal,
    estimated_rub: Decimal,
) -> str:
    return (
        "<b>Проверьте видео</b>\n\n"
        "Модель: <b>Grok Imagine v1 · фото → видео</b>\n"
        "Фото: <b>1</b>\n"
        f"Качество: <b>{escape(resolution)}</b>\n"
        "Формат, длительность и стиль движения: <b>автоматически</b>\n"
        "Фильтр Kie: <b>выключен</b>\n"
        f"Расчётная стоимость: <b>{legacy._format_usd(estimated_usd)}</b> · "
        f"<b>{legacy._format_rub(estimated_rub)}</b>\n\n"
        f"<b>Движение и сцена</b>\n{escape(legacy._truncate(prompt, 3500))}\n\n"
        "После запуска задача попадёт в очередь. Повторное нажатие в этой сессии "
        "не создаст вторую платную генерацию."
    )


async def handle_meow_video_prompt(
    message: Message,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
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
        await message.answer("Описание движения не может быть пустым.")
        return
    if len(prompt) > _MAX_PROMPT_LENGTH:
        await message.answer(
            f"Описание слишком длинное. Максимум {_MAX_PROMPT_LENGTH} символов."
        )
        return

    data = await state.get_data()
    if legacy._reference_from_data(data.get("meow_video_reference")) is None:
        await state.clear()
        await message.answer("Сессия устарела: фото не найдено. Откройте Оживить заново.")
        return

    workspace_id = legacy._optional_int(data.get("meow_video_workspace_id")) or 0
    resolution = _validated_resolution(data)
    await state.update_data(meow_video_prompt=prompt)
    await state.set_state(MeowVideoForm.choosing_settings)
    await message.answer(
        _quality_text(resolution=resolution),
        reply_markup=build_video_quality_keyboard(
            workspace_id=workspace_id,
            resolution=resolution,
        ),
    )


async def handle_meow_video_action(
    callback: CallbackQuery,
    callback_data: MeowVideoCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
    database: Database,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    action = callback_data.action
    workspace_id = callback_data.workspace_id

    if action not in {"resolution", "settings", "review", "submit"}:
        await legacy.handle_meow_video_action(
            callback,
            callback_data,
            state,
            access_policy,
            kie_settings,
            database,
            ai_usage_service,
            ai_task_queue_service,
        )
        return

    if not access_policy.allows_user(callback.from_user):
        await callback.answer("Оживление доступно только владельцу бота.", show_alert=True)
        return
    if not kie_settings.enabled:
        await state.clear()
        await callback.answer("Kie.ai выключен на сервере.", show_alert=True)
        return

    if action == "resolution":
        if callback_data.value not in _VIDEO_RESOLUTIONS:
            await callback.answer("Неизвестное качество видео.", show_alert=True)
            return
        await state.update_data(meow_video_resolution=callback_data.value)
        await _show_review(
            callback,
            state=state,
            workspace_id=workspace_id,
            kie_settings=kie_settings,
        )
        return

    if action == "settings":
        await _show_quality(callback, state=state, workspace_id=workspace_id)
        return

    if action == "review":
        await _show_review(
            callback,
            state=state,
            workspace_id=workspace_id,
            kie_settings=kie_settings,
        )
        return

    await _submit_video(
        callback,
        state=state,
        workspace_id=workspace_id,
        kie_settings=kie_settings,
        ai_usage_service=ai_usage_service,
        ai_task_queue_service=ai_task_queue_service,
    )


async def _show_quality(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace_id: int,
) -> None:
    data = await state.get_data()
    resolution = _validated_resolution(data)
    await state.set_state(MeowVideoForm.choosing_settings)
    await legacy._edit_or_answer(
        callback,
        text=_quality_text(resolution=resolution),
        reply_markup=build_video_quality_keyboard(
            workspace_id=workspace_id,
            resolution=resolution,
        ),
    )


async def _show_review(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace_id: int,
    kie_settings: KieSettings,
) -> None:
    data = await state.get_data()
    reference = legacy._reference_from_data(data.get("meow_video_reference"))
    prompt = str(data.get("meow_video_prompt") or "").strip()
    if reference is None or not prompt:
        await callback.answer("Сессия устарела: нужны фото и текст.", show_alert=True)
        return

    resolution = _validated_resolution(data)
    request = _build_request(
        reference=reference,
        prompt=prompt,
        resolution=resolution,
    )
    estimated_usd = kie_settings.pricing.estimate_usd(request)
    estimated_rub = kie_settings.pricing.estimate_rub(
        request,
        usd_to_rub=kie_settings.usd_to_rub,
    )
    await state.set_state(MeowVideoForm.reviewing)
    await legacy._edit_or_answer(
        callback,
        text=_review_text(
            prompt=prompt,
            resolution=resolution,
            estimated_usd=estimated_usd,
            estimated_rub=estimated_rub,
        ),
        reply_markup=build_video_review_keyboard(workspace_id=workspace_id),
    )


async def _submit_video(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace_id: int,
    kie_settings: KieSettings,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    data = await state.get_data()
    reference = legacy._reference_from_data(data.get("meow_video_reference"))
    prompt = str(data.get("meow_video_prompt") or "").strip()
    session_id = str(data.get("meow_video_session_id") or "").strip()
    if reference is None or not prompt or not session_id:
        await state.clear()
        await callback.answer("Сессия Оживить устарела.", show_alert=True)
        return

    provider_model = kie_settings.models.provider_model(
        KieModelAlias.GROK_IMAGINE_VIDEO,
        input_mode=KieInputMode.PHOTO_TEXT,
    )
    if provider_model != _GROK_V1_MODEL_ID:
        await callback.answer(
            "Неверный model id Grok: требуется grok-imagine/image-to-video.",
            show_alert=True,
        )
        return

    resolution = _validated_resolution(data)
    request = _build_request(
        reference=reference,
        prompt=prompt,
        resolution=resolution,
    )
    estimated_usd = kie_settings.pricing.estimate_usd(request)
    estimated_rub = kie_settings.pricing.estimate_rub(
        request,
        usd_to_rub=kie_settings.usd_to_rub,
    )
    budget_status = await ai_usage_service.status()
    block_reason = legacy._budget_block_reason(
        budget_status,
        estimated_cost_rub=estimated_rub,
    )
    if block_reason is not None:
        await callback.answer(block_reason, show_alert=True)
        return

    chat_id = callback.message.chat.id if isinstance(callback.message, Message) else None
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
            },
            priority=35,
            dedupe_key=f"kie:grok-v1:{session_id}",
            max_attempts=3,
            created_by=callback.from_user.id,
            estimated_cost_rub=estimated_rub,
        )
    )
    await state.clear()
    created_line = (
        "Задача поставлена в очередь."
        if result.created
        else "Эта задача уже была поставлена в очередь."
    )
    await legacy._edit_or_answer(
        callback,
        text=(
            "<b>Мяу · Grok Imagine v1</b>\n\n"
            f"{created_line}\n"
            "Grok сам выберет длительность, формат кадра и режим движения по фото. "
            "Фильтр Kie выключен. Готовый MP4 будет скачан ботом перед отправкой.\n\n"
            f"Качество: <b>{escape(resolution)}</b>\n"
            f"Расчётная стоимость: <b>{legacy._format_usd(estimated_usd)}</b> · "
            f"<b>{legacy._format_rub(estimated_rub)}</b>\n"
            f"Задача: <code>{result.task.id}</code>"
        ),
        reply_markup=build_meow_root_keyboard(
            workspace_id=workspace_id,
            enabled=True,
        ),
    )


def _build_request(
    *,
    reference: KieReferenceImage,
    prompt: str,
    resolution: str,
) -> KieGenerationRequest:
    return KieGenerationRequest(
        model=KieModelAlias.GROK_IMAGINE_VIDEO,
        input_mode=KieInputMode.PHOTO_TEXT,
        prompt=prompt,
        references=(reference,),
        content_mode=KieContentMode.MATURE,
        resolution=resolution,
        duration_seconds=_PROVIDER_PRICING_DURATION_SECONDS,
        output_format="mp4",
        extra_input={"nsfw_checker": False},
    )


def _validated_resolution(data: dict[str, object] | object) -> str:
    if isinstance(data, dict):
        resolution = str(data.get("meow_video_resolution") or "480p")
    else:
        resolution = "480p"
    return resolution if resolution in _VIDEO_RESOLUTIONS else "480p"


__all__ = (
    "MeowVideoCallback",
    "MeowVideoForm",
    "build_video_quality_keyboard",
    "build_video_review_keyboard",
    "handle_meow_video_action",
    "handle_meow_video_entry",
    "handle_meow_video_prompt",
    "handle_meow_video_reference_message",
)
