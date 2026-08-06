from __future__ import annotations

import importlib
import os
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Mapping, Sequence

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AITaskRequest
from velvet_bot.domains.codex_image import (
    CODEX_IMAGE_EFFORTS,
    CODEX_IMAGE_MODELS,
    CODEX_IMAGE_RATIOS,
    CODEX_IMAGE_RESOLUTIONS,
    CODEX_IMAGE_TASK_TYPE,
    CodexImageRequest,
    GPT_IMAGE_2_ALIAS,
    GPT_IMAGE_2_NAME,
    MAX_CODEX_IMAGE_PROMPT,
    MAX_CODEX_IMAGE_REFERENCES,
    render_codex_image_progress,
)
from velvet_bot.domains.media_generation import KieReferenceImage
from velvet_bot.presentation.telegram.auf_editing import edit_or_answer_auf_callback
from velvet_bot.presentation.telegram.routers import workspace_auf_photo as photo_router
from velvet_bot.presentation.telegram.routers.workspace_auf import build_auf_root_keyboard
from velvet_bot.reference_media import validate_reference_document

_INSTALLED = False
_MAX_PROMPT_MESSAGES = 2
_INTERNAL_EXPORT_PROFILE = "2K"


def _enabled() -> bool:
    return os.getenv("CODEX_IMAGE_ENABLED", "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
        "да",
    }


def _button(
    text: str,
    action: str,
    *,
    workspace_id: int,
    value: str = "",
    item_id: int = 0,
) -> InlineKeyboardButton:
    return photo_router._button(
        text,
        action,
        workspace_id=workspace_id,
        value=value,
        item_id=item_id,
    )


def _markup(*rows: Sequence[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(row) for row in rows])


def _state_value(data: Mapping[str, object], key: str) -> object:
    return data.get(key, data.get(key.replace("auf_", "meow_", 1)))


def _is_gpt(data: Mapping[str, object]) -> bool:
    return str(_state_value(data, "auf_model") or "") == GPT_IMAGE_2_ALIAS


def _references(data: Mapping[str, object]) -> tuple[KieReferenceImage, ...]:
    raw = _state_value(data, "auf_references")
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(
        KieReferenceImage.from_payload(item)
        for item in raw
        if isinstance(item, Mapping)
    )


def _prompt_parts(data: Mapping[str, object]) -> tuple[str, ...]:
    raw = _state_value(data, "auf_prompt_parts")
    if isinstance(raw, (list, tuple)):
        return tuple(
            str(item).strip() for item in raw if str(item).strip()
        )[:_MAX_PROMPT_MESSAGES]
    prompt = str(_state_value(data, "auf_prompt") or "").strip()
    return (prompt,) if prompt else ()


def _prompt(data: Mapping[str, object]) -> str:
    return "\n\n".join(_prompt_parts(data)).strip()


async def _save_prompt_parts(state: FSMContext, parts: Sequence[str]) -> None:
    cleaned = tuple(
        str(item).strip() for item in parts if str(item).strip()
    )[:_MAX_PROMPT_MESSAGES]
    await state.update_data(
        auf_prompt_parts=list(cleaned),
        auf_prompt="\n\n".join(cleaned),
    )


def _combined_model_keyboard(
    workspace_id: int,
    kie_settings: Any,
) -> InlineKeyboardMarkup:
    model_modes = importlib.import_module("velvet_bot.app.auf_photo_model_modes")
    base = model_modes._model_keyboard(
        workspace_id,
        grs_enabled=bool(kie_settings.grs_api_key),
    )
    rows = [list(row) for row in base.inline_keyboard]
    rows.insert(
        0,
        [
            _button(
                GPT_IMAGE_2_NAME,
                "photo_model",
                workspace_id=workspace_id,
                value=GPT_IMAGE_2_ALIAS,
            )
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_models(
    callback: CallbackQuery,
    state: FSMContext,
    kie_settings: Any,
) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    await state.set_state(photo_router.AufPhotoForm.choosing_model)
    await edit_or_answer_auf_callback(
        callback,
        text=(
            "<b>Выберите модель изображения</b>\n\n"
            "GPT Image 2 работает через Codex и подписку ChatGPT Plus. "
            "Создаётся ровно одно изображение без автоматической перегенерации."
        ),
        reply_markup=_combined_model_keyboard(workspace_id, kie_settings),
    )


async def _show_modes(callback: CallbackQuery, state: FSMContext) -> None:
    workspace_id = int(
        _state_value(await state.get_data(), "auf_workspace_id") or 0
    )
    await state.set_state(photo_router.AufPhotoForm.choosing_mode)
    await edit_or_answer_auf_callback(
        callback,
        text=(
            f"<b>{GPT_IMAGE_2_NAME}</b>\n\n"
            "Только текст: 0 референсов.\n"
            "Фото + текст: от 1 до 5 общих референсов.\n"
            "Каэль сам анализирует персонажа, одежду, сцену и остальные детали.\n"
            "Промт: до 8000 символов двумя сообщениями.\n"
            "Результат: один JPEG без выбора условного качества. "
            "Фактический размер показывается после генерации."
        ),
        reply_markup=_markup(
            [
                _button(
                    "Только текст",
                    "gpt2_mode",
                    workspace_id=workspace_id,
                    value="text",
                )
            ],
            [
                _button(
                    "Фото + текст",
                    "gpt2_mode",
                    workspace_id=workspace_id,
                    value="photo_text",
                )
            ],
            [_button("К моделям", "photo_choose_model", workspace_id=workspace_id)],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ),
    )


def _input_keyboard(
    workspace_id: int,
    *,
    mode: str,
    refs: int,
    prompt_parts: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if mode == "photo_text":
        rows.append(
            [
                _button(
                    "Референсы из базы",
                    "photo_ref_sources",
                    workspace_id=workspace_id,
                )
            ]
        )
        if refs:
            rows.append(
                [
                    _button(
                        "Убрать последнее фото",
                        "photo_remove_last",
                        workspace_id=workspace_id,
                    ),
                    _button(
                        "Очистить фото",
                        "photo_clear_refs",
                        workspace_id=workspace_id,
                    ),
                ]
            )
    if prompt_parts:
        rows.append(
            [
                _button(
                    "Очистить текст",
                    "gpt2_clear_prompt",
                    workspace_id=workspace_id,
                )
            ]
        )
    rows.extend(
        [
            [_button("К проверке", "gpt2_review", workspace_id=workspace_id)],
            [
                _button(
                    "Изменить режим",
                    "gpt2_change_mode",
                    workspace_id=workspace_id,
                )
            ],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_input(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    mode = str(_state_value(data, "auf_input_mode") or "")
    parts = _prompt_parts(data)
    prompt = _prompt(data)
    refs = _references(data)
    await state.set_state(photo_router.AufPhotoForm.collecting_input)
    lines = [
        f"<b>{GPT_IMAGE_2_NAME} · "
        f"{'Только текст' if mode == 'text' else 'Фото + текст'}</b>",
        "",
        f"Промт: <b>{len(prompt)}/{MAX_CODEX_IMAGE_PROMPT}</b> символов.",
        f"Частей текста: <b>{len(parts)}/{_MAX_PROMPT_MESSAGES}</b>.",
    ]
    if mode == "photo_text":
        lines.extend(
            [
                f"Референсы: <b>{len(refs)}/{MAX_CODEX_IMAGE_REFERENCES}</b>.",
                "Один файл: <b>до 10 МБ</b> · JPG, PNG или WEBP.",
                "Каэль сам определит назначение каждого изображения.",
            ]
        )
    lines.extend(
        ["", "Отправьте промт, а в режиме «Фото + текст» также изображения."]
    )
    markup = _input_keyboard(
        workspace_id,
        mode=mode,
        refs=len(refs),
        prompt_parts=len(parts),
    )
    if isinstance(event, CallbackQuery):
        await edit_or_answer_auf_callback(
            event,
            text="\n".join(lines),
            reply_markup=markup,
        )
    else:
        await event.answer("\n".join(lines), reply_markup=markup)


async def _show_review(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    mode = str(_state_value(data, "auf_input_mode") or "")
    prompt = _prompt(data)
    refs = _references(data)
    if not prompt:
        await callback.answer("Добавьте промт.", show_alert=True)
        return
    if mode == "photo_text" and not refs:
        await callback.answer("Добавьте хотя бы один референс.", show_alert=True)
        return
    await state.set_state(photo_router.AufPhotoForm.reviewing_input)
    await edit_or_answer_auf_callback(
        callback,
        text=(
            "<b>Проверьте исходные данные</b>\n\n"
            f"Модель: <b>{GPT_IMAGE_2_NAME}</b>\n"
            f"Режим: <b>{'Только текст' if mode == 'text' else 'Фото + текст'}</b>\n"
            f"Референсы: <b>{len(refs)}</b>\n"
            f"Промт: <b>{len(prompt)}/{MAX_CODEX_IMAGE_PROMPT}</b> символов\n\n"
            f"<b>Текст</b>\n{escape(photo_router._truncate(prompt, 3000))}"
        ),
        reply_markup=_markup(
            [
                _button(
                    "Да, всё верно",
                    "gpt2_input_confirm",
                    workspace_id=workspace_id,
                )
            ],
            [
                _button(
                    "Вернуться к вводу",
                    "gpt2_input_back",
                    workspace_id=workspace_id,
                )
            ],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ),
    )


async def _show_resolutions(callback: CallbackQuery, state: FSMContext) -> None:
    """Redirect stale size-selection keyboards to aspect ratio selection."""
    await _show_ratios(callback, state)


async def _show_ratios(callback: CallbackQuery, state: FSMContext) -> None:
    workspace_id = int(
        _state_value(await state.get_data(), "auf_workspace_id") or 0
    )
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(CODEX_IMAGE_RATIOS), 3):
        rows.append(
            [
                _button(
                    ratio,
                    "gpt2_ratio",
                    workspace_id=workspace_id,
                    value=ratio,
                )
                for ratio in CODEX_IMAGE_RATIOS[index : index + 3]
            ]
        )
    rows.extend(
        [
            [
                _button(
                    "К проверке",
                    "gpt2_review",
                    workspace_id=workspace_id,
                )
            ],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    await state.set_state(photo_router.AufPhotoForm.choosing_aspect_ratio)
    await edit_or_answer_auf_callback(
        callback,
        text="<b>GPT Image 2 · соотношение сторон</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _show_analysis_models(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    workspace_id = int(
        _state_value(await state.get_data(), "auf_workspace_id") or 0
    )
    rows = [
        [
            _button(
                label,
                "gpt2_analysis",
                workspace_id=workspace_id,
                value=value,
            )
        ]
        for value, label in CODEX_IMAGE_MODELS
    ]
    rows.extend(
        [
            [
                _button(
                    "К пропорции",
                    "gpt2_choose_ratio",
                    workspace_id=workspace_id,
                )
            ],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    await edit_or_answer_auf_callback(
        callback,
        text=(
            "<b>GPT Image 2 · модель анализа</b>\n\n"
            "Sol глубже анализирует сложные референсы, Terra является основным "
            "вариантом, Luna экономит лимит."
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _show_efforts(callback: CallbackQuery, state: FSMContext) -> None:
    workspace_id = int(
        _state_value(await state.get_data(), "auf_workspace_id") or 0
    )
    rows = [
        [
            _button(
                label,
                "gpt2_effort",
                workspace_id=workspace_id,
                value=value,
            )
        ]
        for value, label in CODEX_IMAGE_EFFORTS
    ]
    rows.extend(
        [
            [
                _button(
                    "К модели анализа",
                    "gpt2_choose_analysis",
                    workspace_id=workspace_id,
                )
            ],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    await edit_or_answer_auf_callback(
        callback,
        text=(
            "<b>GPT Image 2 · усилие анализа</b>\n\n"
            "Настройка влияет на разбор промта и референсов Каэлем. "
            "Скорость отдельно не выбирается."
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def _request(data: Mapping[str, object]) -> CodexImageRequest:
    return CodexImageRequest(
        prompt=_prompt(data),
        references=_references(data),
        input_mode=str(_state_value(data, "auf_input_mode") or "text"),
        aspect_ratio=str(_state_value(data, "auf_aspect_ratio") or "9:16"),
        resolution=_INTERNAL_EXPORT_PROFILE,
        analysis_model=str(
            _state_value(data, "auf_analysis_model") or "gpt-5.6-terra"
        ),
        reasoning_effort=str(
            _state_value(data, "auf_reasoning_effort") or "high"
        ),
    )


async def _show_final(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    request = _request(data)
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    model_name = dict(CODEX_IMAGE_MODELS)[request.analysis_model]
    effort_name = dict(CODEX_IMAGE_EFFORTS)[request.reasoning_effort]
    await state.set_state(photo_router.AufPhotoForm.confirming_generation)
    await edit_or_answer_auf_callback(
        callback,
        text=(
            "<b>Проверьте перед созданием</b>\n\n"
            f"Модель: <b>{GPT_IMAGE_2_NAME}</b>\n"
            f"Анализ: <b>{escape(model_name)} · {escape(effort_name)}</b>\n"
            f"Референсы: <b>{len(request.references)}</b>\n"
            "Экспорт: <b>JPEG без искусственного апскейла</b>\n"
            f"Соотношение: <b>{request.aspect_ratio}</b>\n"
            "Результатов: <b>1</b>\n"
            "Автоперегенерация: <b>нет</b>\n\n"
            f"<b>Текст</b>\n{escape(photo_router._truncate(request.prompt, 2500))}"
        ),
        reply_markup=_markup(
            [_button("Да, создать", "gpt2_generate", workspace_id=workspace_id)],
            [
                _button(
                    "Пропорция",
                    "gpt2_choose_ratio",
                    workspace_id=workspace_id,
                )
            ],
            [
                _button(
                    "Модель анализа",
                    "gpt2_choose_analysis",
                    workspace_id=workspace_id,
                ),
                _button(
                    "Усилие",
                    "gpt2_choose_effort",
                    workspace_id=workspace_id,
                ),
            ],
            [
                _button(
                    "Исходные данные",
                    "gpt2_input_back",
                    workspace_id=workspace_id,
                )
            ],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ),
    )


async def _enqueue(
    callback: CallbackQuery,
    state: FSMContext,
    queue: Any,
) -> None:
    data = await state.get_data()
    request = _request(data)
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    chat_id = callback.message.chat.id if isinstance(callback.message, Message) else None
    progress_message_id = (
        callback.message.message_id
        if isinstance(callback.message, Message)
        else None
    )
    queued_at = datetime.now(timezone.utc)
    result = await queue.enqueue(
        AITaskRequest(
            scope=AIBudgetScope.VISION,
            task_type=CODEX_IMAGE_TASK_TYPE,
            payload={
                "request": request.to_payload(),
                "chat_id": chat_id,
                "user_id": callback.from_user.id,
                "workspace_id": workspace_id,
                "progress_message_id": progress_message_id,
                "queued_at": queued_at.isoformat(),
            },
            priority=35,
            max_attempts=1,
            created_by=callback.from_user.id,
        )
    )
    await state.clear()
    await edit_or_answer_auf_callback(
        callback,
        text=render_codex_image_progress(
            request,
            task_id=result.task.id,
            progress=0,
            stage="ожидание запуска",
            queued_at=queued_at,
        ),
        reply_markup=build_auf_root_keyboard(
            workspace_id=workspace_id,
            enabled=True,
        ),
    )


async def _append_prompt(
    message: Message,
    state: FSMContext,
    text: str,
) -> bool:
    data = await state.get_data()
    parts = _prompt_parts(data)
    value = text.strip()
    if not value:
        await message.answer("Промт не может быть пустым.")
        return False
    if len(parts) >= _MAX_PROMPT_MESSAGES:
        await message.answer(
            "Промт уже состоит из двух сообщений. Очистите текст, чтобы заменить его."
        )
        return False
    candidate = (*parts, value)
    if len("\n\n".join(candidate)) > MAX_CODEX_IMAGE_PROMPT:
        await message.answer("Промт превышает 8000 символов и не был добавлен.")
        return False
    await _save_prompt_parts(state, candidate)
    return True


async def _handle_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    mode = str(_state_value(data, "auf_input_mode") or "")
    if message.text:
        if await _append_prompt(message, state, message.text):
            await _show_input(message, state)
        return
    if mode != "photo_text":
        await message.answer(
            "В режиме «Только текст» отправьте промт, а не изображение."
        )
        return
    refs = _references(data)
    if len(refs) >= MAX_CODEX_IMAGE_REFERENCES:
        await message.answer("GPT Image 2 принимает не больше пяти референсов.")
        return
    reference: KieReferenceImage | None = None
    try:
        if message.photo:
            photo = message.photo[-1]
            reference = KieReferenceImage(
                telegram_file_id=photo.file_id,
                telegram_file_unique_id=photo.file_unique_id,
                source="upload",
                file_name=f"telegram-{photo.file_unique_id}.jpg",
                file_size=photo.file_size,
            )
        elif message.document:
            validation_error = validate_reference_document(message.document)
            if validation_error is not None:
                await message.answer(validation_error)
                return
            suffix = Path(
                message.document.file_name or "reference.jpg"
            ).suffix.casefold()
            mime_type = (message.document.mime_type or "").strip().casefold()
            if not mime_type:
                mime_type = {
                    ".png": "image/png",
                    ".webp": "image/webp",
                }.get(suffix, "image/jpeg")
            reference = KieReferenceImage(
                telegram_file_id=message.document.file_id,
                telegram_file_unique_id=message.document.file_unique_id,
                source="upload",
                mime_type=mime_type,
                file_name=Path(
                    message.document.file_name or "reference.jpg"
                ).name,
                file_size=message.document.file_size,
            )
    except ValueError as error:
        await message.answer(str(error))
        return
    if reference is None:
        await message.answer(
            "Отправьте текст, Telegram-фото или JPG, PNG, WEBP до 10 МБ."
        )
        return
    duplicate = any(
        item.telegram_file_id == reference.telegram_file_id
        or (
            reference.telegram_file_unique_id
            and item.telegram_file_unique_id == reference.telegram_file_unique_id
        )
        for item in refs
    )
    if duplicate:
        await message.answer("Это изображение уже выбрано.")
        return
    await photo_router._save_references(state, (*refs, reference))
    caption = (message.caption or "").strip()
    if caption:
        await _append_prompt(message, state, caption)
    await _show_input(message, state)


async def _add_character_references(
    state: FSMContext,
    database: Any,
    *,
    source_workspace_id: int,
    character_id: int,
) -> tuple[int, int, int]:
    current = list(_references(await state.get_data()))
    is_system, rows = await photo_router._load_character_reference_rows(
        database,
        source_workspace_id=source_workspace_id,
        character_id=character_id,
    )
    source = "system" if is_system else "personal"
    added = 0
    skipped = 0
    for row in rows:
        if len(current) >= MAX_CODEX_IMAGE_REFERENCES:
            skipped += 1
            continue
        reference_id = int(row["id"])
        if any(
            item.reference_id == reference_id
            and item.workspace_id == source_workspace_id
            for item in current
        ):
            continue
        current.append(
            KieReferenceImage(
                telegram_file_id=str(row["telegram_file_id"]),
                telegram_file_unique_id=(
                    str(row["telegram_file_unique_id"])
                    if row["telegram_file_unique_id"]
                    else None
                ),
                source=source,
                file_name=f"reference-{reference_id}.jpg",
                character_id=character_id,
                reference_id=reference_id,
                workspace_id=source_workspace_id,
            )
        )
        added += 1
    await photo_router._save_references(state, tuple(current))
    return added, len(current), skipped


def install_auf_gpt_image_2() -> None:
    """Add the one-shot GPT Image 2 Codex subscription flow to Auf."""
    global _INSTALLED
    if _INSTALLED:
        return
    controller = importlib.import_module(
        "velvet_bot.presentation.telegram.workspace_home_controller"
    )
    original_action = controller.handle_scoped_auf_action
    original_input = photo_router.handle_auf_photo_input
    original_command = photo_router.handle_auf_photo_command

    async def action_wrapper(
        callback: CallbackQuery,
        callback_data: Any,
        state: FSMContext,
        access_policy: Any,
        kie_settings: Any,
        database: Any,
        ai_usage_service: Any,
        ai_task_queue_service: Any,
        auf_runtime_service: Any,
        auf_wallet_service: Any,
        auf_purchase_service: Any,
    ) -> None:
        action = callback_data.action
        data = await state.get_data()
        gpt_session = _is_gpt(data)
        if action == "create" and _enabled():
            allowed = await controller._require_auf_callback(
                callback,
                workspace_id=callback_data.workspace_id,
                service=auf_runtime_service,
            )
            if not allowed:
                return
            await state.clear()
            await state.update_data(
                auf_workspace_id=callback_data.workspace_id,
                auf_model="",
                auf_input_mode="",
                auf_prompt="",
                auf_prompt_parts=[],
                auf_references=[],
                auf_resolution="",
                auf_aspect_ratio="",
                auf_analysis_model="gpt-5.6-terra",
                auf_reasoning_effort="high",
            )
            await _show_models(callback, state, kie_settings)
            return
        if action == "photo_model" and callback_data.value == GPT_IMAGE_2_ALIAS:
            if not _enabled():
                await callback.answer(
                    "GPT Image 2 отключён на сервере.",
                    show_alert=True,
                )
                return
            await state.update_data(
                auf_model=GPT_IMAGE_2_ALIAS,
                auf_input_mode="",
                auf_resolution="",
                auf_aspect_ratio="",
                auf_analysis_model="gpt-5.6-terra",
                auf_reasoning_effort="high",
            )
            await _show_modes(callback, state)
            return
        if action == "photo_choose_model" and gpt_session:
            await _show_models(callback, state, kie_settings)
            return
        if not gpt_session and not action.startswith("gpt2_"):
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
        allowed = await controller._require_auf_callback(
            callback,
            workspace_id=callback_data.workspace_id,
            service=auf_runtime_service,
        )
        if not allowed:
            return
        workspace_id = callback_data.workspace_id
        if action == "cancel":
            await state.clear()
            await edit_or_answer_auf_callback(
                callback,
                text="<b>Ауф</b>\n\nГенерация отменена.",
                reply_markup=build_auf_root_keyboard(
                    workspace_id=workspace_id,
                    enabled=True,
                ),
            )
        elif action == "gpt2_change_mode":
            await _show_modes(callback, state)
        elif action == "gpt2_mode":
            mode = callback_data.value
            if mode not in {"text", "photo_text"}:
                await callback.answer("Неизвестный режим.", show_alert=True)
                return
            updates: dict[str, object] = {"auf_input_mode": mode}
            if mode == "text":
                updates["auf_references"] = []
            await state.update_data(**updates)
            await _show_input(callback, state)
        elif action in {"gpt2_input_back", "photo_input_back"}:
            await _show_input(callback, state)
        elif action == "gpt2_clear_prompt":
            await _save_prompt_parts(state, ())
            await _show_input(callback, state)
        elif action == "photo_remove_last":
            refs = _references(await state.get_data())
            await photo_router._save_references(state, refs[:-1])
            await _show_input(callback, state)
        elif action == "photo_clear_refs":
            await photo_router._save_references(state, ())
            await _show_input(callback, state)
        elif action == "photo_ref_sources":
            sources = await photo_router._load_sources(
                database,
                user_id=callback.from_user.id,
                active_workspace_id=workspace_id,
            )
            await edit_or_answer_auf_callback(
                callback,
                text="<b>Откуда взять референсы?</b>",
                reply_markup=photo_router._source_keyboard(workspace_id, sources),
            )
        elif action == "photo_ref_workspace":
            source_workspace_id = callback_data.item_id
            can_access = await photo_router._can_access_source(
                database,
                user_id=callback.from_user.id,
                active_workspace_id=workspace_id,
                source_workspace_id=source_workspace_id,
            )
            if not can_access:
                await callback.answer("Источник недоступен.", show_alert=True)
                return
            characters = await photo_router._load_characters(
                database,
                source_workspace_id,
            )
            await edit_or_answer_auf_callback(
                callback,
                text="<b>Выберите персонажа</b>",
                reply_markup=photo_router._character_keyboard(
                    workspace_id,
                    source_workspace_id,
                    characters,
                ),
            )
        elif action == "photo_ref_character":
            source_workspace_id = photo_router._optional_int(callback_data.value)
            if source_workspace_id is None:
                await callback.answer("Источник недоступен.", show_alert=True)
                return
            added, total, skipped = await _add_character_references(
                state,
                database,
                source_workspace_id=source_workspace_id,
                character_id=callback_data.item_id,
            )
            text = f"Добавлено: {added}. Всего: {total}."
            if skipped:
                text += f" Не добавлено из-за лимита: {skipped}."
            await callback.answer(text)
            await _show_input(callback, state)
        elif action == "gpt2_review":
            await _show_review(callback, state)
        elif action == "gpt2_input_confirm":
            await _show_ratios(callback, state)
        elif action == "gpt2_choose_resolution":
            await _show_resolutions(callback, state)
        elif action == "gpt2_resolution":
            if callback_data.value not in CODEX_IMAGE_RESOLUTIONS:
                await callback.answer("Недоступный размер.", show_alert=True)
                return
            await state.update_data(auf_resolution=callback_data.value)
            await _show_ratios(callback, state)
        elif action == "gpt2_choose_ratio":
            await _show_ratios(callback, state)
        elif action == "gpt2_ratio":
            if callback_data.value not in CODEX_IMAGE_RATIOS:
                await callback.answer("Недоступная пропорция.", show_alert=True)
                return
            await state.update_data(auf_aspect_ratio=callback_data.value)
            await _show_analysis_models(callback, state)
        elif action == "gpt2_choose_analysis":
            await _show_analysis_models(callback, state)
        elif action == "gpt2_analysis":
            if callback_data.value not in dict(CODEX_IMAGE_MODELS):
                await callback.answer(
                    "Недоступная модель анализа.",
                    show_alert=True,
                )
                return
            await state.update_data(auf_analysis_model=callback_data.value)
            await _show_efforts(callback, state)
        elif action == "gpt2_choose_effort":
            await _show_efforts(callback, state)
        elif action == "gpt2_effort":
            if callback_data.value not in dict(CODEX_IMAGE_EFFORTS):
                await callback.answer(
                    "Недоступное усилие анализа.",
                    show_alert=True,
                )
                return
            await state.update_data(auf_reasoning_effort=callback_data.value)
            await _show_final(callback, state)
        elif action == "gpt2_generate":
            await _enqueue(callback, state, ai_task_queue_service)
        else:
            await callback.answer(
                "Неизвестное действие GPT Image 2.",
                show_alert=True,
            )

    async def input_wrapper(
        message: Message,
        state: FSMContext,
        access_policy: Any,
        kie_settings: Any,
    ) -> None:
        if _is_gpt(await state.get_data()):
            await _handle_input(message, state)
            return
        await original_input(message, state, access_policy, kie_settings)

    async def command_wrapper(
        message: Message,
        state: FSMContext,
        access_policy: Any,
        kie_settings: Any,
        database: Any,
    ) -> None:
        if _is_gpt(await state.get_data()):
            await message.answer(
                "Для GPT Image 2 выберите «Референсы из базы» кнопкой "
                "в текущем экране."
            )
            return
        await original_command(
            message,
            state,
            access_policy,
            kie_settings,
            database,
        )

    controller.handle_scoped_auf_action = action_wrapper
    photo_router.handle_auf_photo_input = input_wrapper
    photo_router.handle_auf_photo_command = command_wrapper
    _INSTALLED = True


__all__ = ("install_auf_gpt_image_2",)
