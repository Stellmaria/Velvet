from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Mapping

from aiogram import F
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
    MAX_KIE_REFERENCES,
    KieContentMode,
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieReferenceImage,
)
from velvet_bot.presentation.telegram.auf_editing import edit_or_answer_auf_callback
from velvet_bot.reference_catalog import get_reference_page
from velvet_bot.reference_media import validate_reference_document
from velvet_bot.workspace_ui import WorkspaceCallback, workspace_callback


class AufCallback(CallbackData, prefix="auf"):
    action: str
    workspace_id: int = 0
    value: str = ""
    item_id: int = 0
    offset: int = 0


class AufForm(StatesGroup):
    collecting_references = State()
    waiting_prompt = State()
    reviewing_request = State()
    choosing_model = State()
    choosing_quality = State()


def _callback(
    action: str,
    *,
    workspace_id: int,
    value: str = "",
    item_id: int = 0,
    offset: int = 0,
) -> str:
    return AufCallback(
        action=action,
        workspace_id=int(workspace_id),
        value=value,
        item_id=int(item_id),
        offset=max(0, int(offset)),
    ).pack()


def build_auf_root_keyboard(
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
                        text="Фото",
                        callback_data=_callback(
                            "create",
                            workspace_id=workspace_id,
                        ),
                    ),
                    InlineKeyboardButton(
                        text="Видео",
                        callback_data=_callback(
                            "animate",
                            workspace_id=workspace_id,
                        ),
                    ),
                ]
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


def build_auf_mode_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Текст",
                    callback_data=_callback(
                        "mode",
                        workspace_id=workspace_id,
                        value=KieInputMode.TEXT.value,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Фото",
                    callback_data=_callback(
                        "mode",
                        workspace_id=workspace_id,
                        value=KieInputMode.PHOTO.value,
                    ),
                ),
                InlineKeyboardButton(
                    text="Фото + текст",
                    callback_data=_callback(
                        "mode",
                        workspace_id=workspace_id,
                        value=KieInputMode.PHOTO_TEXT.value,
                    ),
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


def build_reference_source_keyboard(
    *,
    workspace_id: int,
    selected_count: int,
) -> InlineKeyboardMarkup:
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
                    text=f"Готово · {selected_count}/{MAX_KIE_REFERENCES}",
                    callback_data=_callback("references_done", workspace_id=workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=_callback("cancel", workspace_id=workspace_id),
                )
            ],
        ]
    )


def build_request_review_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, подтвердить",
                    callback_data=_callback(
                        "request_confirm",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить",
                    callback_data=_callback("edit", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=_callback("cancel", workspace_id=workspace_id),
                ),
            ],
        ]
    )


def build_edit_keyboard(
    *,
    workspace_id: int,
    input_mode: KieInputMode,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if input_mode in {KieInputMode.TEXT, KieInputMode.PHOTO_TEXT}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Изменить текст",
                    callback_data=_callback("edit_text", workspace_id=workspace_id),
                )
            ]
        )
    if input_mode in {KieInputMode.PHOTO, KieInputMode.PHOTO_TEXT}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Изменить фото",
                    callback_data=_callback("edit_photos", workspace_id=workspace_id),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Вернуться к проверке",
                    callback_data=_callback("review", workspace_id=workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=_callback("cancel", workspace_id=workspace_id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_model_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Nano Banana Pro",
                    callback_data=_callback(
                        "model",
                        workspace_id=workspace_id,
                        value=KieModelAlias.NANO_BANANA_PRO.value,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Seedream 5 Pro",
                    callback_data=_callback(
                        "model",
                        workspace_id=workspace_id,
                        value=KieModelAlias.SEEDREAM_5_PRO.value,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К проверке",
                    callback_data=_callback("review", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=_callback("cancel", workspace_id=workspace_id),
                ),
            ],
        ]
    )


def build_quality_keyboard(
    *,
    workspace_id: int,
    model: KieModelAlias,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=resolution,
                callback_data=_callback(
                    "quality",
                    workspace_id=workspace_id,
                    value=resolution,
                ),
            )
        ]
        for resolution in model.supported_photo_resolutions
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К моделям",
                callback_data=_callback("request_confirm", workspace_id=workspace_id),
            ),
            InlineKeyboardButton(
                text="Отмена",
                callback_data=_callback("cancel", workspace_id=workspace_id),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _reference_collection_text(
    *,
    input_mode: KieInputMode,
    selected_count: int,
    prompt_present: bool,
) -> str:
    prompt_line = (
        "\nТекст уже сохранён." if prompt_present else "\nТекст пока не задан."
    )
    if input_mode is KieInputMode.PHOTO:
        prompt_line = ""
    return (
        "<b>Ауф · референсы</b>\n\n"
        f"Выбрано: <b>{selected_count}/{MAX_KIE_REFERENCES}</b>.\n"
        "Можно смешивать сохранённые референсы из базы и новые Telegram-фото."
        f"{prompt_line}\n\n"
        "Когда закончите, нажмите «Готово»."
    )


def format_request_review(
    *,
    input_mode: KieInputMode,
    prompt: str,
    references: tuple[KieReferenceImage, ...],
) -> str:
    prompt_block = (
        escape(_truncate(prompt, 2400))
        if prompt.strip()
        else "<i>только референсы, без пользовательского текста</i>"
    )
    library_count = sum(item.source == "library" for item in references)
    upload_count = len(references) - library_count
    return (
        "<b>Проверьте запрос</b>\n\n"
        f"Режим: <b>{escape(input_mode.display_name)}</b>\n"
        f"Фото: <b>{len(references)}</b> "
        f"(из базы {library_count}, отправлено {upload_count})\n"
        "Контент: <b>Mature</b>\n\n"
        f"<b>Текст</b>\n{prompt_block}\n\n"
        "Модель и доступное качество выбираются после подтверждения."
    )


def _model_selection_text() -> str:
    return (
        "<b>Выберите модель</b>\n\n"
        "Доступны две фото-модели: Nano Banana Pro и Seedream 5 Pro.\n"
        "Mature-режим включён. Для Seedream бот передаст документированный "
        "<code>nsfw_checker=false</code>. У Nano Banana Pro отдельного API-флага "
        "отключения фильтра нет, поэтому действует политика самого провайдера."
    )


def _quality_selection_text(model: KieModelAlias) -> str:
    qualities = ", ".join(model.supported_photo_resolutions)
    return (
        f"<b>{escape(model.display_name)}</b>\n\n"
        f"Доступное качество: <b>{escape(qualities)}</b>.\n"
        "После выбора качества задача сразу попадёт в очередь генерации."
    )


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


# Local compatibility alias for the existing router implementation. External
# consumers must import the public Auf editing contract instead.
_edit_or_answer = edit_or_answer_auf_callback


def _is_owner(callback: CallbackQuery, access_policy: AccessPolicy) -> bool:
    return access_policy.allows_user(callback.from_user)


def _parse_mode(value: object) -> KieInputMode | None:
    try:
        return KieInputMode(str(value or ""))
    except ValueError:
        return None


def _parse_model(value: object) -> KieModelAlias | None:
    try:
        return KieModelAlias(str(value or ""))
    except ValueError:
        return None


def _references_from_data(value: object) -> tuple[KieReferenceImage, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        KieReferenceImage.from_payload(item)
        for item in value
        if isinstance(item, Mapping)
    )


def _state_value(data: Mapping[str, object], key: str) -> object:
    if key in data:
        return data[key]
    return data.get(key.replace("auf_", "meow_", 1))

async def _session_data(
    state: FSMContext,
) -> tuple[int, KieInputMode | None, str, tuple[KieReferenceImage, ...]]:
    data = await state.get_data()
    return (
        _optional_int(_state_value(data, "auf_workspace_id")) or 0,
        _parse_mode(_state_value(data, "auf_input_mode")),
        str(_state_value(data, "auf_prompt") or "").strip(),
        _references_from_data(_state_value(data, "auf_references")),
    )


async def _save_references(
    state: FSMContext,
    references: tuple[KieReferenceImage, ...],
) -> None:
    await state.update_data(
        auf_references=[item.to_payload() for item in references]
    )


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


def _character_keyboard(
    *,
    workspace_id: int,
    rows,
    selected_count: int,
) -> InlineKeyboardMarkup:
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
    buttons.extend(
        [
            [
                InlineKeyboardButton(
                    text=f"Готово · {selected_count}/{MAX_KIE_REFERENCES}",
                    callback_data=_callback(
                        "references_done",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К источникам",
                    callback_data=_callback("references", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=_callback("cancel", workspace_id=workspace_id),
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _reference_keyboard(
    *,
    workspace_id: int,
    page,
    selected: bool,
    selected_count: int,
) -> InlineKeyboardMarkup:
    reference_id = page.reference.id if page.reference is not None else 0
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
        rows = [
            [
                InlineKeyboardButton(
                    text="1/1",
                    callback_data=_callback(
                        "reference",
                        workspace_id=workspace_id,
                        item_id=page.character.id,
                        offset=0,
                    ),
                )
            ]
        ]
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Убрать" if selected else "Добавить",
                    callback_data=_callback(
                        "reference_toggle",
                        workspace_id=workspace_id,
                        item_id=page.character.id,
                        offset=page.offset,
                        value=str(reference_id),
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К персонажам",
                    callback_data=_callback("database", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text=f"Готово · {selected_count}/{MAX_KIE_REFERENCES}",
                    callback_data=_callback(
                        "references_done",
                        workspace_id=workspace_id,
                    ),
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
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_reference_page(
    callback: CallbackQuery,
    *,
    database: Database,
    state: FSMContext,
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
    _, _, _, references = await _session_data(state)
    selected = any(item.reference_id == page.reference.id for item in references)
    caption = (
        f"<b>{escape(page.character.name)}</b>\n"
        f"Референс: <b>{page.offset + 1}/{page.total}</b>\n"
        f"Выбрано для Ауф: <b>{len(references)}/{MAX_KIE_REFERENCES}</b>"
    )
    keyboard = _reference_keyboard(
        workspace_id=workspace_id,
        page=page,
        selected=selected,
        selected_count=len(references),
    )
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


async def _show_review(
    event: Message | CallbackQuery,
    *,
    state: FSMContext,
) -> None:
    workspace_id, input_mode, prompt, references = await _session_data(state)
    if input_mode is None:
        await state.clear()
        if isinstance(event, CallbackQuery):
            await event.answer("Сессия Ауф устарела.", show_alert=True)
        else:
            await event.answer("Сессия Ауф устарела. Откройте кнопку заново.")
        return
    if input_mode is KieInputMode.TEXT and not prompt:
        message = "Для режима Текст нужен промт."
    elif input_mode is KieInputMode.PHOTO and not references:
        message = "Для режима Фото нужен хотя бы один референс."
    elif input_mode is KieInputMode.PHOTO_TEXT and (not prompt or not references):
        message = "Для режима Фото + текст нужны фото и текст."
    else:
        message = ""
    if message:
        if isinstance(event, CallbackQuery):
            await event.answer(message, show_alert=True)
        else:
            await event.answer(message)
        return
    await state.set_state(AufForm.reviewing_request)
    text = format_request_review(
        input_mode=input_mode,
        prompt=prompt,
        references=references,
    )
    keyboard = build_request_review_keyboard(workspace_id=workspace_id)
    if isinstance(event, CallbackQuery):
        await _edit_or_answer(event, text=text, reply_markup=keyboard)
    else:
        await event.answer(text, reply_markup=keyboard)


async def handle_auf_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
) -> None:
    if not _is_owner(callback, access_policy):
        await callback.answer("Ауф доступен только владельцу бота.", show_alert=True)
        return
    await state.clear()
    if kie_settings.enabled:
        text = (
            "<b>Ауф</b>\n\n"
            "Создание фото через Kie.ai. Можно использовать текст, до пяти фото "
            "из базы или новые Telegram-фото.\n\n"
            "Оживление появится отдельным видеосрезом после завершения фото-ветки."
        )
    else:
        text = (
            "<b>Ауф</b>\n\n"
            "Интерфейс установлен, но Kie.ai пока выключен на сервере. "
            "Нужно заполнить KIE_API_KEY, KIE_USD_TO_RUB и model id Seedream 5 Pro."
        )
    await _edit_or_answer(
        callback,
        text=text,
        reply_markup=build_auf_root_keyboard(
            workspace_id=callback_data.workspace_id,
            enabled=kie_settings.enabled,
        ),
    )


async def handle_auf_action(
    callback: CallbackQuery,
    callback_data: AufCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
    database: Database,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    if not _is_owner(callback, access_policy):
        await callback.answer("Ауф доступен только владельцу бота.", show_alert=True)
        return
    action = callback_data.action
    workspace_id = callback_data.workspace_id
    if action == "cancel":
        await state.clear()
        await _edit_or_answer(
            callback,
            text="<b>Ауф</b>\n\nГенерация отменена.",
            reply_markup=build_auf_root_keyboard(
                workspace_id=workspace_id,
                enabled=kie_settings.enabled,
            ),
        )
        return
    if not kie_settings.enabled:
        await callback.answer("Kie.ai выключен на сервере.", show_alert=True)
        return
    if action == "create":
        await state.clear()
        await state.update_data(auf_workspace_id=workspace_id)
        await _edit_or_answer(
            callback,
            text=(
                "<b>Ауф · Создать</b>\n\n"
                "Выберите, что отправить модели: только текст, только фото или фото с текстом."
            ),
            reply_markup=build_auf_mode_keyboard(workspace_id=workspace_id),
        )
        return
    if action == "animate":
        await callback.answer(
            "Оживление будет добавлено после завершения фото-ветки.",
            show_alert=True,
        )
        return
    if action == "mode":
        input_mode = _parse_mode(callback_data.value)
        if input_mode is None:
            await callback.answer("Неизвестный режим.", show_alert=True)
            return
        await state.clear()
        await state.update_data(
            auf_workspace_id=workspace_id,
            auf_input_mode=input_mode.value,
            auf_prompt="",
            auf_references=[],
        )
        if input_mode is KieInputMode.TEXT:
            await state.set_state(AufForm.waiting_prompt)
            await _edit_or_answer(
                callback,
                text=(
                    "<b>Ауф · Текст</b>\n\n"
                    "Отправьте промт одним текстовым сообщением."
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Отмена",
                                callback_data=_callback(
                                    "cancel",
                                    workspace_id=workspace_id,
                                ),
                            )
                        ]
                    ]
                ),
            )
            return
        await state.set_state(AufForm.collecting_references)
        await _edit_or_answer(
            callback,
            text=_reference_collection_text(
                input_mode=input_mode,
                selected_count=0,
                prompt_present=False,
            ),
            reply_markup=build_reference_source_keyboard(
                workspace_id=workspace_id,
                selected_count=0,
            ),
        )
        return
    if action == "references":
        _, input_mode, prompt, references = await _session_data(state)
        if input_mode is None:
            await callback.answer("Сессия Ауф устарела.", show_alert=True)
            return
        await state.set_state(AufForm.collecting_references)
        await _edit_or_answer(
            callback,
            text=_reference_collection_text(
                input_mode=input_mode,
                selected_count=len(references),
                prompt_present=bool(prompt),
            ),
            reply_markup=build_reference_source_keyboard(
                workspace_id=workspace_id,
                selected_count=len(references),
            ),
        )
        return
    if action == "upload":
        _, input_mode, prompt, references = await _session_data(state)
        if input_mode is None:
            await callback.answer("Сессия Ауф устарела.", show_alert=True)
            return
        await state.set_state(AufForm.collecting_references)
        await _edit_or_answer(
            callback,
            text=(
                "<b>Отправьте фото</b>\n\n"
                f"Сейчас выбрано <b>{len(references)}/{MAX_KIE_REFERENCES}</b>. "
                "Принимаются фото и изображения JPG, PNG или WEBP до 10 МБ. "
                "Можно отправлять по одному или альбомом."
                + (
                    " Подпись первого фото будет сохранена как текст запроса."
                    if input_mode is KieInputMode.PHOTO_TEXT and not prompt
                    else ""
                )
            ),
            reply_markup=build_reference_source_keyboard(
                workspace_id=workspace_id,
                selected_count=len(references),
            ),
        )
        return
    if action == "database":
        _, input_mode, _, references = await _session_data(state)
        if input_mode is None:
            await callback.answer("Сессия Ауф устарела.", show_alert=True)
            return
        rows = await _load_reference_characters(
            database,
            workspace_id=workspace_id,
        )
        if not rows:
            await callback.answer(
                "В этом пространстве пока нет сохранённых референсов.",
                show_alert=True,
            )
            return
        await _edit_or_answer(
            callback,
            text=(
                "<b>Референсы из базы</b>\n\n"
                f"Выбрано: <b>{len(references)}/{MAX_KIE_REFERENCES}</b>. "
                "Откройте персонажа и добавьте нужные изображения."
            ),
            reply_markup=_character_keyboard(
                workspace_id=workspace_id,
                rows=rows,
                selected_count=len(references),
            ),
        )
        return
    if action in {"character", "reference"}:
        await _show_reference_page(
            callback,
            database=database,
            state=state,
            workspace_id=workspace_id,
            character_id=callback_data.item_id,
            offset=callback_data.offset,
        )
        return
    if action == "reference_toggle":
        page = await get_reference_page(
            database,
            callback_data.item_id,
            callback_data.offset,
            workspace_id=workspace_id,
        )
        if page is None or page.reference is None:
            await callback.answer("Референс больше не найден.", show_alert=True)
            return
        _, input_mode, _, references = await _session_data(state)
        if input_mode is None:
            await callback.answer("Сессия Ауф устарела.", show_alert=True)
            return
        current = list(references)
        existing_index = next(
            (
                index
                for index, item in enumerate(current)
                if item.reference_id == page.reference.id
            ),
            None,
        )
        if existing_index is not None:
            current.pop(existing_index)
        else:
            if len(current) >= MAX_KIE_REFERENCES:
                await callback.answer(
                    "Можно выбрать не больше пяти фото.",
                    show_alert=True,
                )
                return
            current.append(
                KieReferenceImage(
                    telegram_file_id=page.reference.telegram_file_id,
                    telegram_file_unique_id=page.reference.telegram_file_unique_id,
                    source="library",
                    mime_type="image/jpeg",
                    file_name=f"reference-{page.reference.id}.jpg",
                    character_id=page.character.id,
                    reference_id=page.reference.id,
                )
            )
        await _save_references(state, tuple(current))
        await _show_reference_page(
            callback,
            database=database,
            state=state,
            workspace_id=workspace_id,
            character_id=page.character.id,
            offset=page.offset,
        )
        return
    if action == "references_done":
        _, input_mode, prompt, references = await _session_data(state)
        if input_mode is None:
            await callback.answer("Сессия Ауф устарела.", show_alert=True)
            return
        if not references:
            await callback.answer("Добавьте хотя бы одно фото.", show_alert=True)
            return
        if input_mode is KieInputMode.PHOTO:
            await _show_review(callback, state=state)
            return
        if input_mode is KieInputMode.PHOTO_TEXT and not prompt:
            await state.set_state(AufForm.waiting_prompt)
            await _edit_or_answer(
                callback,
                text=(
                    "<b>Ауф · Фото + текст</b>\n\n"
                    f"Фото выбрано: <b>{len(references)}</b>. Теперь отправьте текстовый промт."
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="↩️ К фото",
                                callback_data=_callback(
                                    "references",
                                    workspace_id=workspace_id,
                                ),
                            ),
                            InlineKeyboardButton(
                                text="Отмена",
                                callback_data=_callback(
                                    "cancel",
                                    workspace_id=workspace_id,
                                ),
                            ),
                        ]
                    ]
                ),
            )
            return
        await _show_review(callback, state=state)
        return
    if action == "review":
        await _show_review(callback, state=state)
        return
    if action == "edit":
        _, input_mode, _, _ = await _session_data(state)
        if input_mode is None:
            await callback.answer("Сессия Ауф устарела.", show_alert=True)
            return
        await _edit_or_answer(
            callback,
            text="<b>Что изменить?</b>",
            reply_markup=build_edit_keyboard(
                workspace_id=workspace_id,
                input_mode=input_mode,
            ),
        )
        return
    if action == "edit_text":
        await state.set_state(AufForm.waiting_prompt)
        await _edit_or_answer(
            callback,
            text="<b>Отправьте новый текст запроса.</b>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ К проверке",
                            callback_data=_callback(
                                "review",
                                workspace_id=workspace_id,
                            ),
                        ),
                        InlineKeyboardButton(
                            text="Отмена",
                            callback_data=_callback(
                                "cancel",
                                workspace_id=workspace_id,
                            ),
                        ),
                    ]
                ]
            ),
        )
        return
    if action == "edit_photos":
        await state.set_state(AufForm.collecting_references)
        _, input_mode, prompt, references = await _session_data(state)
        if input_mode is None:
            await callback.answer("Сессия Ауф устарела.", show_alert=True)
            return
        await _edit_or_answer(
            callback,
            text=_reference_collection_text(
                input_mode=input_mode,
                selected_count=len(references),
                prompt_present=bool(prompt),
            ),
            reply_markup=build_reference_source_keyboard(
                workspace_id=workspace_id,
                selected_count=len(references),
            ),
        )
        return
    if action == "request_confirm":
        await state.set_state(AufForm.choosing_model)
        await _edit_or_answer(
            callback,
            text=_model_selection_text(),
            reply_markup=build_model_keyboard(workspace_id=workspace_id),
        )
        return
    if action == "model":
        model = _parse_model(callback_data.value)
        if model not in {
            KieModelAlias.NANO_BANANA_PRO,
            KieModelAlias.SEEDREAM_5_PRO,
        }:
            await callback.answer("Неизвестная фото-модель.", show_alert=True)
            return
        try:
            kie_settings.models.provider_model(model)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await state.update_data(auf_model=model.value)
        await state.set_state(AufForm.choosing_quality)
        await _edit_or_answer(
            callback,
            text=_quality_selection_text(model),
            reply_markup=build_quality_keyboard(
                workspace_id=workspace_id,
                model=model,
            ),
        )
        return
    if action == "quality":
        data = await state.get_data()
        model = _parse_model(_state_value(data, "auf_model"))
        input_mode = _parse_mode(_state_value(data, "auf_input_mode"))
        prompt = str(_state_value(data, "auf_prompt") or "").strip()
        references = _references_from_data(_state_value(data, "auf_references"))
        resolution = callback_data.value.upper()
        if model is None or input_mode is None:
            await state.clear()
            await callback.answer("Сессия Ауф устарела.", show_alert=True)
            return
        try:
            request = KieGenerationRequest(
                model=model,
                input_mode=input_mode,
                prompt=prompt,
                references=references,
                content_mode=KieContentMode.MATURE,
                aspect_ratio="9:16",
                resolution=resolution,
                output_format="png",
            )
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
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
        chat_id = (
            callback.message.chat.id
            if isinstance(callback.message, Message)
            else None
        )
        result = await ai_task_queue_service.enqueue(
            AITaskRequest(
                scope=AIBudgetScope.VISION,
                task_type=KIE_GENERATION_TASK_TYPE,
                payload={
                    "request": request.to_task_payload(),
                    "chat_id": chat_id,
                    "user_id": callback.from_user.id,
                    "workspace_id": workspace_id,
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
                f"<b>Ауф · {escape(model.display_name)}</b>\n\n"
                "Задача поставлена в очередь. Worker скачает выбранные Telegram-фото, "
                "временно загрузит их в Kie и только затем вызовет модель.\n\n"
                f"Режим: <b>{escape(input_mode.display_name)}</b>\n"
                f"Фото: <b>{len(references)}</b>\n"
                f"Качество: <b>{escape(resolution)}</b>\n"
                "Контент: <b>Mature</b>\n"
                f"Себестоимость: <b>{_format_usd(estimated_usd)}</b> · "
                f"<b>{_format_rub(estimated_rub)}</b>\n"
                f"Задача: <code>{result.task.id}</code>"
            ),
            reply_markup=build_auf_root_keyboard(
                workspace_id=workspace_id,
                enabled=True,
            ),
        )
        return
    await callback.answer("Неизвестное действие Ауф.", show_alert=True)


async def handle_auf_prompt(
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
        await message.answer("Промт не может быть пустым.")
        return
    if len(prompt) > 8000:
        await message.answer("Промт слишком длинный. Максимум 8000 символов.")
        return
    workspace_id, input_mode, _, references = await _session_data(state)
    if input_mode is None:
        await state.clear()
        await message.answer("Сессия Ауф устарела. Откройте кнопку заново.")
        return
    await state.update_data(auf_prompt=prompt)
    if input_mode is KieInputMode.PHOTO_TEXT and not references:
        await state.set_state(AufForm.collecting_references)
        await message.answer(
            _reference_collection_text(
                input_mode=input_mode,
                selected_count=0,
                prompt_present=True,
            ),
            reply_markup=build_reference_source_keyboard(
                workspace_id=workspace_id,
                selected_count=0,
            ),
        )
        return
    await _show_review(message, state=state)


async def handle_auf_reference_message(
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
    workspace_id, input_mode, prompt, references = await _session_data(state)
    if input_mode not in {KieInputMode.PHOTO, KieInputMode.PHOTO_TEXT}:
        await message.answer("Эта сессия не принимает фото.")
        return
    if len(references) >= MAX_KIE_REFERENCES:
        await message.answer("Уже выбрано пять фото. Нажмите «Готово».")
        return
    reference: KieReferenceImage | None = None
    if message.photo:
        photo = message.photo[-1]
        reference = KieReferenceImage(
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            source="upload",
            mime_type="image/jpeg",
            file_name=f"telegram-{photo.file_unique_id}.jpg",
            file_size=photo.file_size,
        )
    elif message.document:
        validation_error = validate_reference_document(message.document)
        if validation_error is not None:
            await message.answer(validation_error)
            return
        suffix = Path(message.document.file_name or "reference.jpg").suffix.casefold()
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
            file_name=Path(message.document.file_name or "reference.jpg").name,
            file_size=message.document.file_size,
        )
    if reference is None:
        await message.answer("Отправьте фото или изображение JPG, PNG либо WEBP.")
        return
    duplicate = any(
        (
            reference.telegram_file_unique_id
            and item.telegram_file_unique_id == reference.telegram_file_unique_id
        )
        or item.telegram_file_id == reference.telegram_file_id
        for item in references
    )
    current = list(references)
    if not duplicate:
        current.append(reference)
        await _save_references(state, tuple(current))
    if (
        input_mode is KieInputMode.PHOTO_TEXT
        and not prompt
        and (message.caption or "").strip()
    ):
        prompt = (message.caption or "").strip()
        if len(prompt) <= 8000:
            await state.update_data(auf_prompt=prompt)
    await message.answer(
        (
            "Это фото уже выбрано."
            if duplicate
            else f"Фото добавлено. Выбрано: <b>{len(current)}/{MAX_KIE_REFERENCES}</b>."
        ),
        reply_markup=build_reference_source_keyboard(
            workspace_id=workspace_id,
            selected_count=len(current),
        ),
    )


async def handle_auf_reference_text(
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
        return
    workspace_id, input_mode, _, references = await _session_data(state)
    text = (message.text or "").strip()
    if input_mode is KieInputMode.PHOTO_TEXT and text:
        if len(text) > 8000:
            await message.answer("Промт слишком длинный. Максимум 8000 символов.")
            return
        await state.update_data(auf_prompt=text)
        await message.answer(
            "Текст сохранён. Теперь добавьте фото или нажмите «Готово», если они уже выбраны.",
            reply_markup=build_reference_source_keyboard(
                workspace_id=workspace_id,
                selected_count=len(references),
            ),
        )
        return
    await message.answer(
        "Сейчас ожидаются фото. Используйте кнопки ниже.",
        reply_markup=build_reference_source_keyboard(
            workspace_id=workspace_id,
            selected_count=len(references),
        ),
    )


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


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
    "AufCallback",
    "AufForm",
    "build_auf_mode_keyboard",
    "build_auf_root_keyboard",
    "build_quality_keyboard",
    "build_request_review_keyboard",
    "format_request_review",
    "handle_auf_action",
    "handle_auf_entry",
    "handle_auf_prompt",
    "handle_auf_reference_message",
    "handle_auf_reference_text",
)
