from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
    AIBudgetStatus,
    AITaskQueueService,
    AITaskRequest,
    AIUsageService,
)
from velvet_bot.domains.media_generation import (
    KIE_GENERATION_TASK_TYPE,
    KieContentMode,
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieReferenceImage,
)
from velvet_bot.reference_catalog import get_reference_page
from velvet_bot.reference_media import validate_reference_document
from velvet_bot.presentation.telegram.routers.workspace_auf import (
    AufCallback,
    build_auf_root_keyboard,
)

_GROK_V1_MODEL_ID = "grok-imagine/image-to-video"
_VIDEO_RESOLUTIONS = ("480p", "720p")
_VIDEO_DURATIONS = (6, 10)
_VIDEO_ASPECT_RATIOS = ("9:16", "16:9", "1:1", "2:3", "3:2")
_VIDEO_MODES = ("normal", "fun")
_MAX_PROMPT_LENGTH = 8000


class AufVideoCallback(CallbackData, prefix="aufv"):
    action: str
    workspace_id: int = 0
    value: str = ""
    item_id: int = 0
    offset: int = 0

class LegacyAufVideoCallback(CallbackData, prefix="meowv"):
    """Parse video callbacks emitted before the Auf protocol migration."""

    action: str
    workspace_id: int = 0
    value: str = ""
    item_id: int = 0
    offset: int = 0


class AufVideoForm(StatesGroup):
    choosing_reference = State()
    waiting_reference = State()
    waiting_prompt = State()
    choosing_settings = State()
    reviewing = State()

class LegacyAufVideoForm(StatesGroup):
    """Recognize video forms created before the Auf state migration."""

    choosing_reference = State()
    waiting_reference = State()
    waiting_prompt = State()
    choosing_settings = State()
    reviewing = State()


def _callback(
    action: str,
    *,
    workspace_id: int,
    value: str = "",
    item_id: int = 0,
    offset: int = 0,
) -> str:
    return AufVideoCallback(
        action=action,
        workspace_id=int(workspace_id),
        value=value,
        item_id=int(item_id),
        offset=max(0, int(offset)),
    ).pack()


def build_video_source_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Выбрать из базы",
                    callback_data=_callback("database", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="Отправить фото",
                    callback_data=_callback("upload", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=_callback("cancel", workspace_id=workspace_id),
                )
            ],
        ]
    )


def build_video_settings_keyboard(
    *,
    workspace_id: int,
    resolution: str,
    duration: int,
    aspect_ratio: str,
    mode: str,
) -> InlineKeyboardMarkup:
    def selected(label: str, active: bool) -> str:
        return f"✓ {label}" if active else label

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=selected(item, item == resolution),
                callback_data=_callback(
                    "resolution",
                    workspace_id=workspace_id,
                    value=item,
                ),
            )
            for item in _VIDEO_RESOLUTIONS
        ],
        [
            InlineKeyboardButton(
                text=selected(f"{item} сек", item == duration),
                callback_data=_callback(
                    "duration",
                    workspace_id=workspace_id,
                    value=str(item),
                ),
            )
            for item in _VIDEO_DURATIONS
        ],
        [
            InlineKeyboardButton(
                text=selected(item, item == aspect_ratio),
                callback_data=_callback(
                    "aspect",
                    workspace_id=workspace_id,
                    value=item,
                ),
            )
            for item in _VIDEO_ASPECT_RATIOS[:3]
        ],
        [
            InlineKeyboardButton(
                text=selected(item, item == aspect_ratio),
                callback_data=_callback(
                    "aspect",
                    workspace_id=workspace_id,
                    value=item,
                ),
            )
            for item in _VIDEO_ASPECT_RATIOS[3:]
        ],
        [
            InlineKeyboardButton(
                text=selected("Обычный", mode == "normal"),
                callback_data=_callback(
                    "mode",
                    workspace_id=workspace_id,
                    value="normal",
                ),
            ),
            InlineKeyboardButton(
                text=selected("Весёлый", mode == "fun"),
                callback_data=_callback(
                    "mode",
                    workspace_id=workspace_id,
                    value="fun",
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                text="Проверить и запустить",
                callback_data=_callback("review", workspace_id=workspace_id),
            )
        ],
        [
            InlineKeyboardButton(
                text="Изменить фото",
                callback_data=_callback("change_photo", workspace_id=workspace_id),
            ),
            InlineKeyboardButton(
                text="Изменить текст",
                callback_data=_callback("change_prompt", workspace_id=workspace_id),
            ),
        ],
        [
            InlineKeyboardButton(
                text="Отмена",
                callback_data=_callback("cancel", workspace_id=workspace_id),
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_video_review_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Запустить видео",
                    callback_data=_callback("submit", workspace_id=workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить параметры",
                    callback_data=_callback("settings", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=_callback("cancel", workspace_id=workspace_id),
                ),
            ],
        ]
    )


def _settings_text(
    *,
    resolution: str,
    duration: int,
    aspect_ratio: str,
    mode: str,
) -> str:
    mode_name = "Обычный" if mode == "normal" else "Весёлый"
    return (
        "<b>Мяу · Оживить · параметры</b>\n\n"
        "Модель: <b>Grok Imagine v1</b>\n"
        f"Качество: <b>{escape(resolution)}</b>\n"
        f"Длительность: <b>{duration} сек</b>\n"
        f"Формат: <b>{escape(aspect_ratio)}</b>\n"
        f"Режим: <b>{escape(mode_name)}</b>\n\n"
        "Для внешнего фото режим Spicy недоступен у провайдера, поэтому бот "
        "предлагает только документированные Normal и Fun."
    )


def _review_text(
    *,
    prompt: str,
    resolution: str,
    duration: int,
    aspect_ratio: str,
    mode: str,
    estimated_usd: Decimal,
    estimated_rub: Decimal,
) -> str:
    mode_name = "Обычный" if mode == "normal" else "Весёлый"
    return (
        "<b>Проверьте видео</b>\n\n"
        "Модель: <b>Grok Imagine v1 · фото → видео</b>\n"
        "Фото: <b>1</b>\n"
        f"Качество: <b>{escape(resolution)}</b>\n"
        f"Длительность: <b>{duration} сек</b>\n"
        f"Формат: <b>{escape(aspect_ratio)}</b>\n"
        f"Режим: <b>{escape(mode_name)}</b>\n"
        "Контент: <b>Mature</b>\n"
        f"Себестоимость: <b>{_format_usd(estimated_usd)}</b> · "
        f"<b>{_format_rub(estimated_rub)}</b>\n\n"
        f"<b>Движение и сцена</b>\n{escape(_truncate(prompt, 3500))}\n\n"
        "После запуска задача попадёт в очередь. Повторное нажатие в этой сессии "
        "не создаст вторую платную генерацию."
    )


async def handle_auf_video_entry(
    callback: CallbackQuery,
    callback_data: AufCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
) -> None:
    if not access_policy.allows_user(callback.from_user):
        await callback.answer("Оживление доступно только владельцу бота.", show_alert=True)
        return
    if not kie_settings.enabled:
        await callback.answer("Kie.ai выключен на сервере.", show_alert=True)
        return
    provider_model = kie_settings.models.provider_model(
        KieModelAlias.GROK_IMAGINE_VIDEO,
        input_mode=KieInputMode.PHOTO_TEXT,
    )
    if provider_model != _GROK_V1_MODEL_ID:
        await callback.answer(
            "Для Оживить задайте KIE_GROK_IMAGINE_VIDEO_MODEL="
            "grok-imagine/image-to-video и перезапустите бота.",
            show_alert=True,
        )
        return
    workspace_id = callback_data.workspace_id
    await state.clear()
    await state.update_data(
        auf_video_session_id=uuid4().hex,
        auf_video_workspace_id=workspace_id,
        auf_video_reference=None,
        auf_video_prompt="",
        auf_video_resolution="480p",
        auf_video_duration=6,
        auf_video_aspect_ratio="9:16",
        auf_video_mode="normal",
    )
    await state.set_state(AufVideoForm.choosing_reference)
    await _edit_or_answer(
        callback,
        text=(
            "<b>Мяу · Оживить</b>\n\n"
            "Grok Imagine v1 превратит одно фото в видео по вашему текстовому "
            "описанию движения. Можно выбрать сохранённый референс или отправить "
            "JPG, PNG либо WEBP до 10 МБ.\n\n"
            "Используется ровно одно фото: так требует старый image-to-video API."
        ),
        reply_markup=build_video_source_keyboard(workspace_id=workspace_id),
    )


async def handle_auf_video_action(
    callback: CallbackQuery,
    callback_data: AufVideoCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
    database: Database,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    if not access_policy.allows_user(callback.from_user):
        await callback.answer("Оживление доступно только владельцу бота.", show_alert=True)
        return
    workspace_id = callback_data.workspace_id
    action = callback_data.action
    if action == "cancel":
        await state.clear()
        await _edit_or_answer(
            callback,
            text="<b>Мяу</b>\n\nСоздание видео отменено.",
            reply_markup=build_auf_root_keyboard(
                workspace_id=workspace_id,
                enabled=kie_settings.enabled,
            ),
        )
        return
    if not kie_settings.enabled:
        await state.clear()
        await callback.answer("Kie.ai выключен на сервере.", show_alert=True)
        return
    if action in {"change_photo", "sources"}:
        await state.set_state(AufVideoForm.choosing_reference)
        await _edit_or_answer(
            callback,
            text=(
                "<b>Выберите одно фото для оживления</b>\n\n"
                "Новый выбор заменит прежний референс."
            ),
            reply_markup=build_video_source_keyboard(workspace_id=workspace_id),
        )
        return
    if action == "upload":
        await state.set_state(AufVideoForm.waiting_reference)
        await _edit_or_answer(
            callback,
            text=(
                "<b>Отправьте одно фото</b>\n\n"
                "Принимаются Telegram-фото и документы JPG, PNG или WEBP до 10 МБ."
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ К источникам",
                            callback_data=_callback("sources", workspace_id=workspace_id),
                        ),
                        InlineKeyboardButton(
                            text="Отмена",
                            callback_data=_callback("cancel", workspace_id=workspace_id),
                        ),
                    ]
                ]
            ),
        )
        return
    if action == "database":
        rows = await _load_reference_characters(database, workspace_id=workspace_id)
        if not rows:
            await callback.answer(
                "В этом пространстве пока нет сохранённых референсов.",
                show_alert=True,
            )
            return
        await state.set_state(AufVideoForm.choosing_reference)
        await _edit_or_answer(
            callback,
            text="<b>Выберите персонажа</b>\n\nЗатем выберите одно фото для видео.",
            reply_markup=_character_keyboard(workspace_id=workspace_id, rows=rows),
        )
        return
    if action in {"character", "reference"}:
        await _show_reference_page(
            callback,
            database=database,
            workspace_id=workspace_id,
            character_id=callback_data.item_id,
            offset=callback_data.offset,
        )
        return
    if action == "select_reference":
        page = await get_reference_page(
            database,
            callback_data.item_id,
            callback_data.offset,
            workspace_id=workspace_id,
        )
        if page is None or page.reference is None:
            await callback.answer("Референс больше не найден.", show_alert=True)
            return
        reference = KieReferenceImage(
            telegram_file_id=page.reference.telegram_file_id,
            telegram_file_unique_id=page.reference.telegram_file_unique_id,
            source="library",
            mime_type="image/jpeg",
            file_name=f"reference-{page.reference.id}.jpg",
            character_id=page.character.id,
            reference_id=page.reference.id,
        )
        await state.update_data(auf_video_reference=reference.to_payload())
        await _ask_video_prompt(callback, state=state, workspace_id=workspace_id)
        return
    if action == "change_prompt":
        await _ask_video_prompt(callback, state=state, workspace_id=workspace_id)
        return
    if action in {"resolution", "duration", "aspect", "mode"}:
        await _update_setting(state, action=action, value=callback_data.value)
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
    if action == "submit":
        await _submit_video(
            callback,
            state=state,
            workspace_id=workspace_id,
            kie_settings=kie_settings,
            ai_usage_service=ai_usage_service,
            ai_task_queue_service=ai_task_queue_service,
        )
        return
    await callback.answer("Неизвестное действие Оживить.", show_alert=True)


async def handle_auf_video_reference_message(
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
    reference = _reference_from_message(message)
    if isinstance(reference, str):
        await message.answer(reference)
        return
    if reference is None:
        await message.answer("Отправьте фото или документ JPG, PNG либо WEBP.")
        return
    data = await state.get_data()
    workspace_id = _optional_int(data.get("auf_video_workspace_id")) or 0
    await state.update_data(auf_video_reference=reference.to_payload())
    await state.set_state(AufVideoForm.waiting_prompt)
    await message.answer(
        "<b>Фото сохранено</b>\n\n"
        "Теперь отправьте текстом, что должно двигаться, как должна работать камера "
        "и что должно происходить в сцене.",
        reply_markup=_prompt_keyboard(workspace_id=workspace_id),
    )


async def handle_auf_video_prompt(
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
    if _reference_from_data(data.get("auf_video_reference")) is None:
        await state.clear()
        await message.answer("Сессия устарела: фото не найдено. Откройте Оживить заново.")
        return
    workspace_id = _optional_int(data.get("auf_video_workspace_id")) or 0
    await state.update_data(auf_video_prompt=prompt)
    await state.set_state(AufVideoForm.choosing_settings)
    await message.answer(
        _settings_text(
            resolution=str(data.get("auf_video_resolution") or "480p"),
            duration=_optional_int(data.get("auf_video_duration")) or 6,
            aspect_ratio=str(data.get("auf_video_aspect_ratio") or "9:16"),
            mode=str(data.get("auf_video_mode") or "normal"),
        ),
        reply_markup=build_video_settings_keyboard(
            workspace_id=workspace_id,
            resolution=str(data.get("auf_video_resolution") or "480p"),
            duration=_optional_int(data.get("auf_video_duration")) or 6,
            aspect_ratio=str(data.get("auf_video_aspect_ratio") or "9:16"),
            mode=str(data.get("auf_video_mode") or "normal"),
        ),
    )


async def _ask_video_prompt(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace_id: int,
) -> None:
    await state.set_state(AufVideoForm.waiting_prompt)
    await _edit_or_answer(
        callback,
        text=(
            "<b>Опишите движение</b>\n\n"
            "Напишите одним сообщением, что происходит в кадре: движения персонажа, "
            "камеры, волос, ткани, света и окружения. Избегайте противоречивых команд."
        ),
        reply_markup=_prompt_keyboard(workspace_id=workspace_id),
    )


def _prompt_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ Изменить фото",
                    callback_data=_callback("change_photo", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=_callback("cancel", workspace_id=workspace_id),
                ),
            ]
        ]
    )


async def _show_settings(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace_id: int,
) -> None:
    data = await state.get_data()
    resolution, duration, aspect_ratio, mode = _validated_settings(data)
    await state.set_state(AufVideoForm.choosing_settings)
    await _edit_or_answer(
        callback,
        text=_settings_text(
            resolution=resolution,
            duration=duration,
            aspect_ratio=aspect_ratio,
            mode=mode,
        ),
        reply_markup=build_video_settings_keyboard(
            workspace_id=workspace_id,
            resolution=resolution,
            duration=duration,
            aspect_ratio=aspect_ratio,
            mode=mode,
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
    reference = _reference_from_data(data.get("auf_video_reference"))
    prompt = str(data.get("auf_video_prompt") or "").strip()
    if reference is None or not prompt:
        await callback.answer("Сессия устарела: нужны фото и текст.", show_alert=True)
        return
    resolution, duration, aspect_ratio, mode = _validated_settings(data)
    request = _build_request(
        reference=reference,
        prompt=prompt,
        resolution=resolution,
        duration=duration,
        aspect_ratio=aspect_ratio,
        mode=mode,
    )
    estimated_usd = kie_settings.pricing.estimate_usd(request)
    estimated_rub = kie_settings.pricing.estimate_rub(
        request,
        usd_to_rub=kie_settings.usd_to_rub,
    )
    await state.set_state(AufVideoForm.reviewing)
    await _edit_or_answer(
        callback,
        text=_review_text(
            prompt=prompt,
            resolution=resolution,
            duration=duration,
            aspect_ratio=aspect_ratio,
            mode=mode,
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
    reference = _reference_from_data(data.get("auf_video_reference"))
    prompt = str(data.get("auf_video_prompt") or "").strip()
    session_id = str(data.get("auf_video_session_id") or "").strip()
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
    resolution, duration, aspect_ratio, mode = _validated_settings(data)
    request = _build_request(
        reference=reference,
        prompt=prompt,
        resolution=resolution,
        duration=duration,
        aspect_ratio=aspect_ratio,
        mode=mode,
    )
    estimated_usd = kie_settings.pricing.estimate_usd(request)
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
    await _edit_or_answer(
        callback,
        text=(
            "<b>Мяу · Grok Imagine v1</b>\n\n"
            f"{created_line}\n"
            "Worker скачает Telegram-фото, временно загрузит его в Kie, создаст "
            "видео и сам скачает готовый MP4 перед отправкой в Telegram.\n\n"
            f"Качество: <b>{escape(resolution)}</b>\n"
            f"Длительность: <b>{duration} сек</b>\n"
            f"Формат: <b>{escape(aspect_ratio)}</b>\n"
            f"Себестоимость: <b>{_format_usd(estimated_usd)}</b> · "
            f"<b>{_format_rub(estimated_rub)}</b>\n"
            f"Задача: <code>{result.task.id}</code>"
        ),
        reply_markup=build_auf_root_keyboard(
            workspace_id=workspace_id,
            enabled=True,
        ),
    )


def _build_request(
    *,
    reference: KieReferenceImage,
    prompt: str,
    resolution: str,
    duration: int,
    aspect_ratio: str,
    mode: str,
) -> KieGenerationRequest:
    return KieGenerationRequest(
        model=KieModelAlias.GROK_IMAGINE_VIDEO,
        input_mode=KieInputMode.PHOTO_TEXT,
        prompt=prompt,
        references=(reference,),
        content_mode=KieContentMode.MATURE,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        duration_seconds=duration,
        output_format="mp4",
        mode=mode,
        extra_input={"nsfw_checker": False},
    )


async def _update_setting(state: FSMContext, *, action: str, value: str) -> None:
    if action == "resolution" and value in _VIDEO_RESOLUTIONS:
        await state.update_data(auf_video_resolution=value)
    elif action == "duration":
        duration = _optional_int(value)
        if duration in _VIDEO_DURATIONS:
            await state.update_data(auf_video_duration=duration)
    elif action == "aspect" and value in _VIDEO_ASPECT_RATIOS:
        await state.update_data(auf_video_aspect_ratio=value)
    elif action == "mode" and value in _VIDEO_MODES:
        await state.update_data(auf_video_mode=value)


def _validated_settings(data: Mapping[str, object]) -> tuple[str, int, str, str]:
    resolution = str(data.get("auf_video_resolution") or "480p")
    if resolution not in _VIDEO_RESOLUTIONS:
        resolution = "480p"
    duration = _optional_int(data.get("auf_video_duration")) or 6
    if duration not in _VIDEO_DURATIONS:
        duration = 6
    aspect_ratio = str(data.get("auf_video_aspect_ratio") or "9:16")
    if aspect_ratio not in _VIDEO_ASPECT_RATIOS:
        aspect_ratio = "9:16"
    mode = str(data.get("auf_video_mode") or "normal")
    if mode not in _VIDEO_MODES:
        mode = "normal"
    return resolution, duration, aspect_ratio, mode


def _reference_from_message(message: Message) -> KieReferenceImage | str | None:
    if message.photo:
        photo = message.photo[-1]
        return KieReferenceImage(
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            source="upload",
            mime_type="image/jpeg",
            file_name=f"telegram-{photo.file_unique_id}.jpg",
            file_size=photo.file_size,
        )
    if message.document:
        validation_error = validate_reference_document(message.document)
        if validation_error is not None:
            return validation_error
        suffix = Path(message.document.file_name or "reference.jpg").suffix.casefold()
        mime_type = (message.document.mime_type or "").strip().casefold()
        if not mime_type:
            mime_type = {
                ".png": "image/png",
                ".webp": "image/webp",
            }.get(suffix, "image/jpeg")
        return KieReferenceImage(
            telegram_file_id=message.document.file_id,
            telegram_file_unique_id=message.document.file_unique_id,
            source="upload",
            mime_type=mime_type,
            file_name=Path(message.document.file_name or "reference.jpg").name,
            file_size=message.document.file_size,
        )
    return None


def _reference_from_data(value: object) -> KieReferenceImage | None:
    if not isinstance(value, Mapping):
        return None
    try:
        return KieReferenceImage.from_payload(value)
    except ValueError:
        return None


async def _load_reference_characters(
    database: Database,
    *,
    workspace_id: int,
):
    async with database.acquire() as connection:
        return await connection.fetch(
            """
            SELECT
                character.id,
                character.name,
                COUNT(reference.id) AS reference_count
            FROM characters AS character
            JOIN character_references AS reference
              ON reference.workspace_id = character.workspace_id
             AND reference.character_id = character.id
            WHERE character.workspace_id = $1::BIGINT
            GROUP BY character.id
            ORDER BY character.normalized_name, character.id
            LIMIT 60
            """,
            int(workspace_id),
        )


def _character_keyboard(*, workspace_id: int, rows) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{row['name']} · {int(row['reference_count'] or 0)}"[:60],
                callback_data=_callback(
                    "character",
                    workspace_id=workspace_id,
                    item_id=int(row["id"]),
                ),
            )
        ]
        for row in rows
    ]
    buttons.append(
        [
            InlineKeyboardButton(
                text="↩️ К источникам",
                callback_data=_callback("sources", workspace_id=workspace_id),
            ),
            InlineKeyboardButton(
                text="Отмена",
                callback_data=_callback("cancel", workspace_id=workspace_id),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _reference_keyboard(*, workspace_id: int, page) -> InlineKeyboardMarkup:
    if page.total > 1:
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_callback(
                        "reference",
                        workspace_id=workspace_id,
                        item_id=page.character.id,
                        offset=(page.offset - 1) % page.total,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.offset + 1}/{page.total}",
                    callback_data=_callback(
                        "reference",
                        workspace_id=workspace_id,
                        item_id=page.character.id,
                        offset=page.offset,
                    ),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_callback(
                        "reference",
                        workspace_id=workspace_id,
                        item_id=page.character.id,
                        offset=(page.offset + 1) % page.total,
                    ),
                ),
            ]
        ]
    else:
        rows = []
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Выбрать это фото",
                    callback_data=_callback(
                        "select_reference",
                        workspace_id=workspace_id,
                        item_id=page.character.id,
                        offset=page.offset,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К персонажам",
                    callback_data=_callback("database", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=_callback("cancel", workspace_id=workspace_id),
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_reference_page(
    callback: CallbackQuery,
    *,
    database: Database,
    workspace_id: int,
    character_id: int,
    offset: int,
) -> None:
    page = await get_reference_page(
        database,
        character_id,
        offset,
        workspace_id=workspace_id,
    )
    if page is None or page.reference is None:
        await callback.answer("Референс больше не найден.", show_alert=True)
        return
    caption = (
        f"<b>{escape(page.character.name)}</b>\n"
        f"Референс: <b>{page.offset + 1}/{page.total}</b>\n"
        "Для видео будет использовано только это фото."
    )
    keyboard = _reference_keyboard(workspace_id=workspace_id, page=page)
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение больше недоступно.", show_alert=True)
        return
    try:
        if callback.message.photo:
            await callback.message.edit_media(
                InputMediaPhoto(
                    media=page.reference.telegram_file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
        else:
            await callback.message.answer_photo(
                photo=page.reference.telegram_file_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                protect_content=True,
            )
    except TelegramBadRequest:
        await callback.message.answer_photo(
            photo=page.reference.telegram_file_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            protect_content=True,
        )
    await callback.answer()


async def _edit_or_answer(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if isinstance(callback.message, Message):
        if callback.message.photo or callback.message.video or callback.message.document:
            await callback.message.answer(text, reply_markup=reply_markup)
        else:
            try:
                await callback.message.edit_text(text, reply_markup=reply_markup)
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).casefold():
                    await callback.message.answer(text, reply_markup=reply_markup)
    await callback.answer()


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


def _format_rub(value: Decimal) -> str:
    normalized = f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")
    return f"{normalized} ₽"


def _format_usd(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    return f"${normalized}"


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _optional_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


__all__ = (
    "AufVideoCallback",
    "AufVideoForm",
    "build_video_review_keyboard",
    "build_video_settings_keyboard",
    "build_video_source_keyboard",
    "handle_auf_video_action",
    "handle_auf_video_entry",
    "handle_auf_video_prompt",
    "handle_auf_video_reference_message",
)
