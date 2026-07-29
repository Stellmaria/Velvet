from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Mapping

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

_GROK_MODEL_ID = "grok-imagine/image-to-video"
_SEEDANCE_MODEL_ID = "bytedance/seedance-1.5-pro"
_WAN_MODEL_ID = "wan/2-6-image-to-video"
_MODEL_CODES = ("grok", "seedance", "wan")
_MODEL_ALIASES = {
    "grok": KieModelAlias.GROK_IMAGINE_VIDEO,
    "seedance": KieModelAlias.SEEDANCE_15_PRO_VIDEO,
    "wan": KieModelAlias.WAN_26_IMAGE_TO_VIDEO,
}
_MODEL_NAMES = {
    "grok": "Grok Imagine v1",
    "seedance": "Seedance 1.5 Pro",
    "wan": "Wan 2.6",
}
_MODEL_EXPECTED_IDS = {
    "grok": _GROK_MODEL_ID,
    "seedance": _SEEDANCE_MODEL_ID,
    "wan": _WAN_MODEL_ID,
}
_GROK_RESOLUTIONS = ("480p", "720p")
_SEEDANCE_RESOLUTIONS = ("480p", "720p", "1080p")
_WAN_RESOLUTIONS = ("720p", "1080p")
_WAN_DURATIONS = (5, 10, 15)
_GROK_PRICING_DURATION_SECONDS = 6
_SEEDANCE_DURATION_SECONDS = 5
_MAX_PROMPT_LENGTH = 5000


def _selected(label: str, active: bool) -> str:
    return f"✓ {label}" if active else label


def build_video_model_keyboard(*, workspace_id: int, model: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_selected("Grok · дёшево", model == "grok"),
                    callback_data=legacy._callback(
                        "model", workspace_id=workspace_id, value="grok"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_selected("Seedance · баланс", model == "seedance"),
                    callback_data=legacy._callback(
                        "model", workspace_id=workspace_id, value="seedance"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_selected("Wan · максимум", model == "wan"),
                    callback_data=legacy._callback(
                        "model", workspace_id=workspace_id, value="wan"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить фото",
                    callback_data=legacy._callback(
                        "change_photo", workspace_id=workspace_id
                    ),
                ),
                InlineKeyboardButton(
                    text="Изменить текст",
                    callback_data=legacy._callback(
                        "change_prompt", workspace_id=workspace_id
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=legacy._callback("cancel", workspace_id=workspace_id),
                )
            ],
        ]
    )


def build_video_settings_keyboard(
    *,
    workspace_id: int,
    model: str,
    resolution: str,
    duration: int,
    generate_audio: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for values in _resolution_rows(model):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_selected(item, item == resolution),
                    callback_data=legacy._callback(
                        "resolution",
                        workspace_id=workspace_id,
                        value=item,
                    ),
                )
                for item in values
            ]
        )
    if model == "seedance":
        rows.append(
            [
                InlineKeyboardButton(
                    text=_selected("Без звука", not generate_audio),
                    callback_data=legacy._callback(
                        "audio", workspace_id=workspace_id, value="off"
                    ),
                ),
                InlineKeyboardButton(
                    text=_selected("Со звуком", generate_audio),
                    callback_data=legacy._callback(
                        "audio", workspace_id=workspace_id, value="on"
                    ),
                ),
            ]
        )
    if model == "wan":
        rows.append(
            [
                InlineKeyboardButton(
                    text=_selected(f"{item} сек", item == duration),
                    callback_data=legacy._callback(
                        "duration",
                        workspace_id=workspace_id,
                        value=str(item),
                    ),
                )
                for item in _WAN_DURATIONS
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Проверить и запустить",
                    callback_data=legacy._callback("review", workspace_id=workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить модель",
                    callback_data=legacy._callback("models", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="Изменить текст",
                    callback_data=legacy._callback(
                        "change_prompt", workspace_id=workspace_id
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=legacy._callback("cancel", workspace_id=workspace_id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_video_quality_keyboard(
    *,
    workspace_id: int,
    resolution: str,
) -> InlineKeyboardMarkup:
    """Compatibility wrapper for the former Grok-only UI contract."""

    return build_video_settings_keyboard(
        workspace_id=workspace_id,
        model="grok",
        resolution=resolution,
        duration=_GROK_PRICING_DURATION_SECONDS,
        generate_audio=False,
    )


def build_video_review_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Запустить видео",
                    callback_data=legacy._callback("submit", workspace_id=workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить параметры",
                    callback_data=legacy._callback("settings", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="Изменить модель",
                    callback_data=legacy._callback("models", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=legacy._callback("cancel", workspace_id=workspace_id),
                )
            ],
        ]
    )


def _model_text(*, model: str) -> str:
    return (
        "<b>Мяу · Оживить · модель</b>\n\n"
        "Выберите движок видео. Все варианты используют одно фото и ваш текст.\n\n"
        "• <b>Grok</b> — самый дешёвый вариант.\n"
        "• <b>Seedance</b> — лучший баланс и может создать звук.\n"
        "• <b>Wan</b> — дорогой качественный вариант до 1080p.\n\n"
        f"Текущая модель: <b>{escape(_MODEL_NAMES[model])}</b>\n"
        "Фильтр Kie: <b>выключен</b>."
    )


def _settings_text(
    *,
    model: str,
    resolution: str,
    duration: int,
    generate_audio: bool,
) -> str:
    lines = [
        "<b>Мяу · Оживить · параметры</b>",
        "",
        f"Модель: <b>{escape(_MODEL_NAMES[model])}</b>",
        f"Качество: <b>{escape(resolution)}</b>",
    ]
    if model == "grok":
        lines.append("Длительность и формат: <b>автоматически</b>")
    elif model == "seedance":
        lines.append(f"Длительность: <b>{duration} сек</b>")
        lines.append(
            f"Звук: <b>{'включён' if generate_audio else 'выключен'}</b>"
        )
        lines.append("Камера: <b>динамическая</b>")
    else:
        lines.append(f"Длительность: <b>{duration} сек</b>")
    lines.append("Фильтр Kie: <b>выключен</b>.")
    return "\n".join(lines)


def _review_text(
    *,
    prompt: str,
    model: str,
    resolution: str,
    duration: int,
    generate_audio: bool,
    estimated_usd: Decimal,
    estimated_rub: Decimal,
) -> str:
    settings = [
        "<b>Проверьте видео</b>",
        "",
        f"Модель: <b>{escape(_MODEL_NAMES[model])}</b>",
        "Фото: <b>1</b>",
        f"Качество: <b>{escape(resolution)}</b>",
    ]
    if model == "grok":
        settings.append("Длительность и формат: <b>автоматически</b>")
    else:
        settings.append(f"Длительность: <b>{duration} сек</b>")
    if model == "seedance":
        settings.append(
            f"Звук: <b>{'включён' if generate_audio else 'выключен'}</b>"
        )
    settings.extend(
        [
            "Фильтр Kie: <b>выключен</b>",
            f"Расчётная стоимость: <b>{legacy._format_usd(estimated_usd)}</b> · "
            f"<b>{legacy._format_rub(estimated_rub)}</b>",
            "",
            f"<b>Движение и сцена</b>\n{escape(legacy._truncate(prompt, 3500))}",
            "",
            "После запуска задача попадёт в очередь. Повторное нажатие в этой "
            "сессии не создаст вторую платную генерацию.",
        ]
    )
    return "\n".join(settings)


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
    model = _validated_model(data)
    await state.update_data(meow_video_prompt=prompt, meow_video_model=model)
    await state.set_state(MeowVideoForm.choosing_settings)
    await message.answer(
        _model_text(model=model),
        reply_markup=build_video_model_keyboard(
            workspace_id=workspace_id,
            model=model,
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
    custom_actions = {
        "model",
        "models",
        "resolution",
        "audio",
        "duration",
        "settings",
        "review",
        "submit",
    }
    if action not in custom_actions:
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

    if action == "model":
        if callback_data.value not in _MODEL_CODES:
            await callback.answer("Неизвестная модель видео.", show_alert=True)
            return
        await _apply_model_defaults(state, model=callback_data.value)
        await _show_settings(callback, state=state, workspace_id=workspace_id)
        return
    if action == "models":
        await _show_models(callback, state=state, workspace_id=workspace_id)
        return
    if action == "resolution":
        data = await state.get_data()
        model = _validated_model(data)
        if callback_data.value not in _allowed_resolutions(model):
            await callback.answer("Это качество не поддерживается моделью.", show_alert=True)
            return
        await state.update_data(meow_video_resolution=callback_data.value)
        await _show_settings(callback, state=state, workspace_id=workspace_id)
        return
    if action == "audio":
        data = await state.get_data()
        if _validated_model(data) != "seedance":
            await callback.answer("Звук доступен только Seedance.", show_alert=True)
            return
        await state.update_data(meow_video_generate_audio=callback_data.value == "on")
        await _show_settings(callback, state=state, workspace_id=workspace_id)
        return
    if action == "duration":
        data = await state.get_data()
        if _validated_model(data) != "wan":
            await callback.answer("Длительность выбирается только для Wan.", show_alert=True)
            return
        duration = legacy._optional_int(callback_data.value)
        if duration not in _WAN_DURATIONS:
            await callback.answer("Неизвестная длительность.", show_alert=True)
            return
        await state.update_data(meow_video_duration=duration)
        await _show_settings(callback, state=state, workspace_id=workspace_id)
        return
    if action == "settings":
        await _show_settings(callback, state=state, workspace_id=workspace_id)
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


async def _show_models(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace_id: int,
) -> None:
    data = await state.get_data()
    model = _validated_model(data)
    await state.set_state(MeowVideoForm.choosing_settings)
    await legacy._edit_or_answer(
        callback,
        text=_model_text(model=model),
        reply_markup=build_video_model_keyboard(
            workspace_id=workspace_id,
            model=model,
        ),
    )


async def _show_settings(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace_id: int,
) -> None:
    data = await state.get_data()
    model = _validated_model(data)
    resolution = _validated_resolution(data, model=model)
    duration = _validated_duration(data, model=model)
    generate_audio = _validated_audio(data, model=model)
    await state.set_state(MeowVideoForm.choosing_settings)
    await legacy._edit_or_answer(
        callback,
        text=_settings_text(
            model=model,
            resolution=resolution,
            duration=duration,
            generate_audio=generate_audio,
        ),
        reply_markup=build_video_settings_keyboard(
            workspace_id=workspace_id,
            model=model,
            resolution=resolution,
            duration=duration,
            generate_audio=generate_audio,
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
    model = _validated_model(data)
    resolution = _validated_resolution(data, model=model)
    duration = _validated_duration(data, model=model)
    generate_audio = _validated_audio(data, model=model)
    request = _build_request(
        reference=reference,
        prompt=prompt,
        model=model,
        resolution=resolution,
        duration=duration,
        generate_audio=generate_audio,
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
            model=model,
            resolution=resolution,
            duration=duration,
            generate_audio=generate_audio,
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
    model = _validated_model(data)
    alias = _MODEL_ALIASES[model]
    provider_model = kie_settings.models.provider_model(
        alias,
        input_mode=KieInputMode.PHOTO_TEXT,
    )
    if provider_model != _MODEL_EXPECTED_IDS[model]:
        await callback.answer(
            f"Неверный model id {_MODEL_NAMES[model]}: {provider_model}",
            show_alert=True,
        )
        return
    resolution = _validated_resolution(data, model=model)
    duration = _validated_duration(data, model=model)
    generate_audio = _validated_audio(data, model=model)
    request = _build_request(
        reference=reference,
        prompt=prompt,
        model=model,
        resolution=resolution,
        duration=duration,
        generate_audio=generate_audio,
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
            dedupe_key=f"kie:video:{model}:{session_id}",
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
    details = [
        f"<b>Мяу · {escape(_MODEL_NAMES[model])}</b>",
        "",
        created_line,
        "Фильтр Kie выключен. Готовый MP4 будет скачан ботом перед отправкой.",
        "",
        f"Качество: <b>{escape(resolution)}</b>",
    ]
    if model != "grok":
        details.append(f"Длительность: <b>{duration} сек</b>")
    if model == "seedance":
        details.append(f"Звук: <b>{'включён' if generate_audio else 'выключен'}</b>")
    details.extend(
        [
            f"Расчётная стоимость: <b>{legacy._format_usd(estimated_usd)}</b> · "
            f"<b>{legacy._format_rub(estimated_rub)}</b>",
            f"Задача: <code>{result.task.id}</code>",
        ]
    )
    await legacy._edit_or_answer(
        callback,
        text="\n".join(details),
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
    model: str = "grok",
    duration: int | None = None,
    generate_audio: bool = False,
) -> KieGenerationRequest:
    if model == "seedance":
        return KieGenerationRequest(
            model=KieModelAlias.SEEDANCE_15_PRO_VIDEO,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt=prompt,
            references=(reference,),
            content_mode=KieContentMode.MATURE,
            aspect_ratio="1:1",
            resolution=resolution,
            duration_seconds=duration or _SEEDANCE_DURATION_SECONDS,
            output_format="mp4",
            extra_input={
                "fixed_lens": False,
                "generate_audio": generate_audio,
                "nsfw_checker": False,
            },
        )
    if model == "wan":
        return KieGenerationRequest(
            model=KieModelAlias.WAN_26_IMAGE_TO_VIDEO,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt=prompt,
            references=(reference,),
            content_mode=KieContentMode.MATURE,
            resolution=resolution,
            duration_seconds=duration or 5,
            output_format="mp4",
            extra_input={"nsfw_checker": False},
        )
    return KieGenerationRequest(
        model=KieModelAlias.GROK_IMAGINE_VIDEO,
        input_mode=KieInputMode.PHOTO_TEXT,
        prompt=prompt,
        references=(reference,),
        content_mode=KieContentMode.MATURE,
        resolution=resolution,
        duration_seconds=_GROK_PRICING_DURATION_SECONDS,
        output_format="mp4",
        extra_input={"nsfw_checker": False},
    )


async def _apply_model_defaults(state: FSMContext, *, model: str) -> None:
    if model == "seedance":
        await state.update_data(
            meow_video_model=model,
            meow_video_resolution="720p",
            meow_video_duration=_SEEDANCE_DURATION_SECONDS,
            meow_video_generate_audio=False,
        )
    elif model == "wan":
        await state.update_data(
            meow_video_model=model,
            meow_video_resolution="720p",
            meow_video_duration=5,
            meow_video_generate_audio=False,
        )
    else:
        await state.update_data(
            meow_video_model="grok",
            meow_video_resolution="480p",
            meow_video_duration=_GROK_PRICING_DURATION_SECONDS,
            meow_video_generate_audio=False,
        )


def _validated_model(data: Mapping[str, object] | object) -> str:
    if isinstance(data, Mapping):
        model = str(data.get("meow_video_model") or "grok")
    else:
        model = "grok"
    return model if model in _MODEL_CODES else "grok"


def _validated_resolution(
    data: Mapping[str, object] | object,
    *,
    model: str | None = None,
) -> str:
    resolved_model = model or _validated_model(data)
    if isinstance(data, Mapping):
        resolution = str(data.get("meow_video_resolution") or "")
    else:
        resolution = ""
    allowed = _allowed_resolutions(resolved_model)
    default = "480p" if resolved_model == "grok" else "720p"
    return resolution if resolution in allowed else default


def _validated_duration(
    data: Mapping[str, object] | object,
    *,
    model: str,
) -> int:
    if model == "grok":
        return _GROK_PRICING_DURATION_SECONDS
    if model == "seedance":
        return _SEEDANCE_DURATION_SECONDS
    value = legacy._optional_int(data.get("meow_video_duration")) if isinstance(data, Mapping) else None
    return value if value in _WAN_DURATIONS else 5


def _validated_audio(
    data: Mapping[str, object] | object,
    *,
    model: str,
) -> bool:
    if model != "seedance" or not isinstance(data, Mapping):
        return False
    return data.get("meow_video_generate_audio") is True


def _allowed_resolutions(model: str) -> tuple[str, ...]:
    if model == "seedance":
        return _SEEDANCE_RESOLUTIONS
    if model == "wan":
        return _WAN_RESOLUTIONS
    return _GROK_RESOLUTIONS


def _resolution_rows(model: str) -> tuple[tuple[str, ...], ...]:
    allowed = _allowed_resolutions(model)
    return (allowed,)


__all__ = (
    "MeowVideoCallback",
    "MeowVideoForm",
    "build_video_model_keyboard",
    "build_video_quality_keyboard",
    "build_video_review_keyboard",
    "build_video_settings_keyboard",
    "handle_meow_video_action",
    "handle_meow_video_entry",
    "handle_meow_video_prompt",
    "handle_meow_video_reference_message",
)
