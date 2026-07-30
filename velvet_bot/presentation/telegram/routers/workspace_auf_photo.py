from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Mapping, Sequence

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
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
from velvet_bot.presentation.telegram.routers.workspace_auf import (
    AufCallback,
    _budget_block_reason,
    _callback,
    _edit_or_answer,
    _format_rub,
    _format_usd,
    build_auf_root_keyboard,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_grs import (
    handle_auf_action,
)
from velvet_bot.reference_media import validate_reference_document


class AufPhotoForm(StatesGroup):
    collecting_input = State()
    reviewing_input = State()
    choosing_model = State()
    choosing_resolution = State()
    choosing_aspect_ratio = State()
    confirming_generation = State()


_PHOTO_MODELS = (
    KieModelAlias.NANO_BANANA_2,
    KieModelAlias.NANO_BANANA_PRO,
    KieModelAlias.SEEDREAM_5_PRO,
    KieModelAlias.QWEN2_IMAGE_EDIT,
    KieModelAlias.WAN_27_IMAGE,
    KieModelAlias.FLUX_2_PRO_IMAGE,
)


def _button(
    text: str,
    action: str,
    *,
    workspace_id: int,
    value: str = "",
    item_id: int = 0,
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=_callback(
            action,
            workspace_id=workspace_id,
            value=value,
            item_id=item_id,
        ),
    )


def _markup(*rows: Sequence[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(row) for row in rows])


def _input_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [_button("Референсы из архива", "photo_ref_sources", workspace_id=workspace_id)],
        [_button("Отмена", "cancel", workspace_id=workspace_id)],
    )


def _review_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [_button("Да, всё верно", "photo_input_confirm", workspace_id=workspace_id)],
        [
            _button("Изменить текст", "photo_edit_prompt", workspace_id=workspace_id),
            _button("Фото и референсы", "photo_edit_refs", workspace_id=workspace_id),
        ],
        [_button("Отмена", "cancel", workspace_id=workspace_id)],
    )


def _edit_references_keyboard(
    workspace_id: int,
    reference_count: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            _button("Добавить фото", "photo_add_upload", workspace_id=workspace_id),
            _button("Из архива", "photo_ref_sources", workspace_id=workspace_id),
        ]
    ]
    if reference_count:
        rows.append(
            [_button("Очистить фото", "photo_clear_refs", workspace_id=workspace_id)]
        )
    rows.extend(
        [
            [_button("К проверке", "photo_review", workspace_id=workspace_id)],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _model_keyboard(workspace_id: int, *, grs_enabled: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            _button(
                model.display_name,
                "photo_model",
                workspace_id=workspace_id,
                value=model.value,
            )
        ]
        for model in _PHOTO_MODELS
        if grs_enabled or not model.is_grs
    ]
    rows.extend(
        [
            [_button("К фото и тексту", "photo_review", workspace_id=workspace_id)],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _resolution_keyboard(
    workspace_id: int,
    model: KieModelAlias,
) -> InlineKeyboardMarkup:
    rows = [
        [
            _button(
                resolution,
                "photo_resolution",
                workspace_id=workspace_id,
                value=resolution,
            )
        ]
        for resolution in model.supported_photo_resolutions
    ]
    rows.extend(
        [
            [_button("К моделям", "photo_choose_model", workspace_id=workspace_id)],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _ratio_keyboard(
    workspace_id: int,
    model: KieModelAlias,
) -> InlineKeyboardMarkup:
    ratios = model.supported_aspect_ratios
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(ratios), 3):
        rows.append(
            [
                _button(
                    "Как исходник" if ratio == "auto" else ratio,
                    "photo_ratio",
                    workspace_id=workspace_id,
                    value=ratio,
                )
                for ratio in ratios[index : index + 3]
            ]
        )
    rows.extend(
        [
            [
                _button(
                    (
                        "К качеству"
                        if len(model.supported_photo_resolutions) > 1
                        else "К моделям"
                    ),
                    "photo_back_settings",
                    workspace_id=workspace_id,
                )
            ],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _final_keyboard(
    workspace_id: int,
    model: KieModelAlias,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [_button("Да, создать", "photo_generate", workspace_id=workspace_id)],
        [_button("Модель", "photo_choose_model", workspace_id=workspace_id)],
    ]
    if len(model.supported_photo_resolutions) > 1:
        rows.append(
            [_button("Качество", "photo_choose_resolution", workspace_id=workspace_id)]
        )
    if len(model.supported_aspect_ratios) > 1:
        rows.append(
            [
                _button(
                    "Соотношение сторон",
                    "photo_choose_ratio",
                    workspace_id=workspace_id,
                )
            ]
        )
    rows.extend(
        [
            [_button("Фото и текст", "photo_review", workspace_id=workspace_id)],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _source_keyboard(
    workspace_id: int,
    sources,
) -> InlineKeyboardMarkup:
    rows = [
        [
            _button(
                (
                    f"Системный · {row['name']}"
                    if bool(row["is_system"])
                    else f"Личное · {row['name']}"
                )[:64],
                "photo_ref_workspace",
                workspace_id=workspace_id,
                item_id=int(row["id"]),
            )
        ]
        for row in sources
    ]
    rows.extend(
        [
            [_button("К вводу", "photo_input_back", workspace_id=workspace_id)],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _character_keyboard(
    workspace_id: int,
    source_workspace_id: int,
    characters,
) -> InlineKeyboardMarkup:
    rows = [
        [
            _button(
                f"{row['name']} · {int(row['reference_count'])}"[:64],
                "photo_ref_character",
                workspace_id=workspace_id,
                value=str(source_workspace_id),
                item_id=int(row["id"]),
            )
        ]
        for row in characters
    ]
    rows.extend(
        [
            [_button("К источникам", "photo_ref_sources", workspace_id=workspace_id)],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _references(value: object) -> tuple[KieReferenceImage, ...]:
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
    legacy_key = key.replace("auf_", "meow_", 1)
    return data.get(legacy_key)

async def _session(
    state: FSMContext,
) -> tuple[int, str, tuple[KieReferenceImage, ...]]:
    data = await state.get_data()
    return (
        _optional_int(_state_value(data, "auf_workspace_id")) or 0,
        str(_state_value(data, "auf_prompt") or "").strip(),
        _references(_state_value(data, "auf_references")),
    )


async def _save_references(
    state: FSMContext,
    references: tuple[KieReferenceImage, ...],
) -> None:
    await state.update_data(
        auf_references=[reference.to_payload() for reference in references]
    )


def _input_text(
    prompt: str,
    references: tuple[KieReferenceImage, ...],
) -> str:
    if not prompt and not references:
        instruction = (
            "Отправьте фото или текстовый промт. После первого сообщения бот попросит "
            "недостающую часть. Фото с подписью принимается сразу."
        )
    elif references and not prompt:
        instruction = (
            f"Фото получено: <b>{len(references)}</b>. Теперь отправьте текстовый промт."
        )
    elif prompt and not references:
        instruction = (
            "Текст получен. Теперь отправьте фото или выберите референсы персонажа "
            "из архива."
        )
    else:
        instruction = (
            f"Фото и текст уже получены. Сейчас фото: <b>{len(references)}</b>. "
            "Отправьте дополнительные изображения или вернитесь к проверке."
        )
    return (
        "<b>Ауф · фото + текст</b>\n\n"
        f"{instruction}\n\n"
        f"До выбора модели можно собрать до <b>{MAX_KIE_REFERENCES}</b> фото. "
        "После выбора применяется лимит конкретной модели.\n"
        "Команда: <code>/refs</code> или <code>/refs Имя персонажа</code>."
    )


def _review_text(
    prompt: str,
    references: tuple[KieReferenceImage, ...],
) -> str:
    uploaded = sum(reference.source == "upload" for reference in references)
    system = sum(reference.source == "system" for reference in references)
    personal = sum(
        reference.source in {"personal", "library"} for reference in references
    )
    return (
        "<b>Проверьте фото и текст</b>\n\n"
        f"Фото: <b>{len(references)}</b>\n"
        f"Отправлено: <b>{uploaded}</b> · системный архив: <b>{system}</b> · "
        f"личное пространство: <b>{personal}</b>\n\n"
        f"<b>Текст</b>\n{escape(_truncate(prompt, 3000))}\n\n"
        "После подтверждения выбираются модель, качество и соотношение сторон."
    )


async def _show_input(
    event: Message | CallbackQuery,
    state: FSMContext,
) -> None:
    workspace_id, prompt, references = await _session(state)
    await state.set_state(AufPhotoForm.collecting_input)
    text = _input_text(prompt, references)
    keyboard = _input_keyboard(workspace_id)
    if isinstance(event, CallbackQuery):
        await _edit_or_answer(event, text=text, reply_markup=keyboard)
    else:
        await event.answer(text, reply_markup=keyboard)


async def _show_review(
    event: Message | CallbackQuery,
    state: FSMContext,
) -> None:
    workspace_id, prompt, references = await _session(state)
    if not references or not prompt:
        message = (
            "Сначала добавьте хотя бы одно фото."
            if not references
            else "Сначала добавьте текстовый промт."
        )
        if isinstance(event, CallbackQuery):
            await event.answer(message, show_alert=True)
        else:
            await event.answer(message)
        return
    await state.set_state(AufPhotoForm.reviewing_input)
    text = _review_text(prompt, references)
    keyboard = _review_keyboard(workspace_id)
    if isinstance(event, CallbackQuery):
        await _edit_or_answer(event, text=text, reply_markup=keyboard)
    else:
        await event.answer(text, reply_markup=keyboard)


async def _advance(
    event: Message | CallbackQuery,
    state: FSMContext,
) -> None:
    _, prompt, references = await _session(state)
    if prompt and references:
        await _show_review(event, state)
    else:
        await _show_input(event, state)


async def _load_sources(
    database: Database,
    *,
    user_id: int,
    active_workspace_id: int,
):
    async with database.acquire() as connection:
        return await connection.fetch(
            """
            SELECT DISTINCT workspace.id, workspace.name, workspace.is_system
            FROM workspaces AS workspace
            LEFT JOIN workspace_members AS membership
              ON membership.workspace_id = workspace.id
             AND membership.user_id = $1::BIGINT
            WHERE workspace.is_system = TRUE
               OR membership.user_id IS NOT NULL
               OR workspace.id = $2::BIGINT
            ORDER BY workspace.is_system DESC, workspace.name, workspace.id
            LIMIT 30
            """,
            int(user_id),
            int(active_workspace_id),
        )


async def _can_access_source(
    database: Database,
    *,
    user_id: int,
    active_workspace_id: int,
    source_workspace_id: int,
) -> bool:
    async with database.acquire() as connection:
        return bool(
            await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM workspaces AS workspace
                    LEFT JOIN workspace_members AS membership
                      ON membership.workspace_id = workspace.id
                     AND membership.user_id = $1::BIGINT
                    WHERE workspace.id = $3::BIGINT
                      AND (
                            workspace.is_system = TRUE
                         OR membership.user_id IS NOT NULL
                         OR workspace.id = $2::BIGINT
                      )
                )
                """,
                int(user_id),
                int(active_workspace_id),
                int(source_workspace_id),
            )
        )


async def _load_characters(
    database: Database,
    source_workspace_id: int,
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
            LIMIT 80
            """,
            int(source_workspace_id),
        )


async def _load_character_reference_rows(
    database: Database,
    *,
    source_workspace_id: int,
    character_id: int,
):
    async with database.acquire() as connection:
        workspace = await connection.fetchrow(
            "SELECT is_system FROM workspaces WHERE id = $1::BIGINT",
            int(source_workspace_id),
        )
        rows = await connection.fetch(
            """
            SELECT id, telegram_file_id, telegram_file_unique_id
            FROM character_references
            WHERE workspace_id = $1::BIGINT
              AND character_id = $2::BIGINT
            ORDER BY created_at, id
            """,
            int(source_workspace_id),
            int(character_id),
        )
    return bool(workspace and workspace["is_system"]), rows


async def _add_character_references(
    state: FSMContext,
    database: Database,
    *,
    source_workspace_id: int,
    character_id: int,
) -> tuple[int, int]:
    _, _, current_references = await _session(state)
    current = list(current_references)
    is_system, rows = await _load_character_reference_rows(
        database,
        source_workspace_id=source_workspace_id,
        character_id=character_id,
    )
    source = "system" if is_system else "personal"
    added = 0
    for row in rows:
        if len(current) >= MAX_KIE_REFERENCES:
            break
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
    await _save_references(state, tuple(current))
    return added, len(current)


def _model(value: object) -> KieModelAlias | None:
    try:
        parsed = KieModelAlias(str(value or ""))
    except ValueError:
        return None
    return parsed if parsed in _PHOTO_MODELS else None


def _infer_ratio(prompt: str, model: KieModelAlias) -> str:
    supported = model.supported_aspect_ratios
    normalized = prompt.casefold()
    for ratio in supported:
        if ratio != "auto" and ratio in normalized:
            return ratio
    if any(word in normalized for word in ("вертикаль", "сторис", "portrait")):
        for ratio in ("9:16", "3:4", "2:3"):
            if ratio in supported:
                return ratio
    if any(word in normalized for word in ("горизонт", "панорама", "landscape", "баннер")):
        for ratio in ("16:9", "21:9", "4:3", "3:2"):
            if ratio in supported:
                return ratio
    return model.default_photo_aspect_ratio


def _request(data: Mapping[str, object]) -> KieGenerationRequest:
    model = _model(_state_value(data, "auf_model"))
    if model is None:
        raise ValueError("Сначала выберите модель.")
    prompt = str(_state_value(data, "auf_prompt") or "").strip()
    resolution = str(_state_value(data, "auf_resolution") or "").strip().upper()
    if not resolution:
        resolution = model.supported_photo_resolutions[0]
    ratio = str(_state_value(data, "auf_aspect_ratio") or "").strip()
    if not ratio:
        ratio = _infer_ratio(prompt, model)
    return KieGenerationRequest(
        model=model,
        input_mode=KieInputMode.PHOTO_TEXT,
        prompt=prompt,
        references=_references(_state_value(data, "auf_references")),
        content_mode=KieContentMode.MATURE,
        aspect_ratio=ratio,
        resolution=resolution,
        output_format="png",
    )


async def _show_models(
    callback: CallbackQuery,
    state: FSMContext,
    kie_settings: KieSettings,
) -> None:
    workspace_id, prompt, references = await _session(state)
    if not prompt or not references:
        await callback.answer("Сначала подтвердите фото и текст.", show_alert=True)
        return
    await state.set_state(AufPhotoForm.choosing_model)
    await _edit_or_answer(
        callback,
        text=(
            "<b>Выберите модель</b>\n\n"
            f"Фото: <b>{len(references)}</b>.\n"
            "Лимиты: Banana — 5, Qwen — 3, FLUX — 8, Wan — 9, Seedream — 10."
        ),
        reply_markup=_model_keyboard(
            workspace_id,
            grs_enabled=bool(kie_settings.grs_api_key),
        ),
    )


async def _show_resolution(
    callback: CallbackQuery,
    state: FSMContext,
    model: KieModelAlias,
) -> None:
    workspace_id, _, _ = await _session(state)
    await state.set_state(AufPhotoForm.choosing_resolution)
    await _edit_or_answer(
        callback,
        text=(
            f"<b>{escape(model.display_name)}</b>\n\n"
            "Выберите качество. Количество результатов фиксировано: "
            "<b>одно изображение</b>."
        ),
        reply_markup=_resolution_keyboard(workspace_id, model),
    )


async def _show_ratios(
    callback: CallbackQuery,
    state: FSMContext,
    model: KieModelAlias,
) -> None:
    workspace_id, _, _ = await _session(state)
    await state.set_state(AufPhotoForm.choosing_aspect_ratio)
    await _edit_or_answer(
        callback,
        text=f"<b>{escape(model.display_name)} · соотношение сторон</b>",
        reply_markup=_ratio_keyboard(workspace_id, model),
    )


async def _show_final(
    callback: CallbackQuery,
    state: FSMContext,
    kie_settings: KieSettings,
) -> None:
    data = await state.get_data()
    try:
        request = _request(data)
        usd = kie_settings.pricing.estimate_usd(request)
        rub = kie_settings.pricing.estimate_rub(
            request,
            usd_to_rub=kie_settings.usd_to_rub,
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.set_state(AufPhotoForm.confirming_generation)
    ratio = "как у исходника" if request.aspect_ratio == "auto" else request.aspect_ratio
    await _edit_or_answer(
        callback,
        text=(
            "<b>Проверьте перед созданием</b>\n\n"
            f"Модель: <b>{escape(request.model.display_name)}</b>\n"
            f"Фото: <b>{len(request.references)}</b> из "
            f"{request.model.max_photo_references}\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Соотношение: <b>{escape(ratio)}</b>\n"
            "Результат: <b>1 изображение</b>\n"
            "Контент: <b>Mature</b>\n\n"
            f"<b>Текст</b>\n{escape(_truncate(request.prompt, 2200))}\n\n"
            f"Предварительная стоимость: <b>{_format_usd(usd)}</b> · "
            f"<b>{_format_rub(rub)}</b>\n"
            "<i>Оценка используется для подтверждения и бюджетного контроля; "
            "фактическое списание определяет провайдер.</i>"
        ),
        reply_markup=_final_keyboard(
            int(_state_value(data, "auf_workspace_id") or 0),
            request.model,
        ),
    )


async def _enqueue(
    callback: CallbackQuery,
    state: FSMContext,
    kie_settings: KieSettings,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    data = await state.get_data()
    workspace_id = _optional_int(_state_value(data, "auf_workspace_id")) or 0
    try:
        request = _request(data)
        usd = kie_settings.pricing.estimate_usd(request)
        rub = kie_settings.pricing.estimate_rub(
            request,
            usd_to_rub=kie_settings.usd_to_rub,
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    block_reason = _budget_block_reason(
        await ai_usage_service.status(),
        estimated_cost_rub=rub,
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
            },
            priority=40,
            max_attempts=3,
            created_by=callback.from_user.id,
            estimated_cost_rub=rub,
        )
    )
    await state.clear()
    await _edit_or_answer(
        callback,
        text=(
            f"<b>Ауф · {escape(request.model.display_name)}</b>\n\n"
            "Фото и текст зафиксированы, задача поставлена в асинхронную очередь.\n\n"
            f"Фото: <b>{len(request.references)}</b>\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Соотношение: <b>{escape(request.aspect_ratio)}</b>\n"
            f"Предварительная стоимость: <b>{_format_usd(usd)}</b> · "
            f"<b>{_format_rub(rub)}</b>\n"
            f"Задача: <code>{result.task.id}</code>"
        ),
        reply_markup=build_auf_root_keyboard(
            workspace_id=workspace_id,
            enabled=True,
        ),
    )


async def handle_auf_photo_action(
    callback: CallbackQuery,
    callback_data: AufCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
    database: Database,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    if not access_policy.allows_user(callback.from_user):
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
        await callback.answer("AI-генерация выключена на сервере.", show_alert=True)
        return
    if action == "create":
        await state.clear()
        await state.update_data(
            auf_workspace_id=workspace_id,
            auf_input_mode=KieInputMode.PHOTO_TEXT.value,
            auf_prompt="",
            auf_references=[],
            auf_model="",
            auf_resolution="",
            auf_aspect_ratio="",
        )
        await state.set_state(AufPhotoForm.collecting_input)
        await _edit_or_answer(
            callback,
            text=_input_text("", ()),
            reply_markup=_input_keyboard(workspace_id),
        )
        return
    if action == "photo_input_back":
        await _advance(callback, state)
        return
    if action == "photo_review":
        await _show_review(callback, state)
        return
    if action == "photo_edit_prompt":
        await state.update_data(auf_prompt="")
        await _show_input(callback, state)
        return
    if action == "photo_edit_refs":
        _, _, references = await _session(state)
        await state.set_state(AufPhotoForm.collecting_input)
        await _edit_or_answer(
            callback,
            text=(
                "<b>Фото и референсы</b>\n\n"
                f"Сейчас выбрано: <b>{len(references)}/{MAX_KIE_REFERENCES}</b>."
            ),
            reply_markup=_edit_references_keyboard(workspace_id, len(references)),
        )
        return
    if action == "photo_add_upload":
        await _show_input(callback, state)
        return
    if action == "photo_clear_refs":
        await _save_references(state, ())
        await _show_input(callback, state)
        return
    if action == "photo_ref_sources":
        sources = await _load_sources(
            database,
            user_id=callback.from_user.id,
            active_workspace_id=workspace_id,
        )
        if not sources:
            await callback.answer("Доступные архивы не найдены.", show_alert=True)
            return
        await _edit_or_answer(
            callback,
            text=(
                "<b>Откуда взять референсы?</b>\n\n"
                "Системный архив и личные пространства разделены. "
                "Показываются только персонажи с сохранёнными фото."
            ),
            reply_markup=_source_keyboard(workspace_id, sources),
        )
        return
    if action == "photo_ref_workspace":
        source_workspace_id = callback_data.item_id
        if not await _can_access_source(
            database,
            user_id=callback.from_user.id,
            active_workspace_id=workspace_id,
            source_workspace_id=source_workspace_id,
        ):
            await callback.answer("Нет доступа к этому архиву.", show_alert=True)
            return
        characters = await _load_characters(database, source_workspace_id)
        if not characters:
            await callback.answer(
                "В этом архиве нет персонажей с референсами.",
                show_alert=True,
            )
            return
        await _edit_or_answer(
            callback,
            text=(
                "<b>Выберите персонажа</b>\n\n"
                "Будут добавлены его сохранённые референсы до общего лимита."
            ),
            reply_markup=_character_keyboard(
                workspace_id,
                source_workspace_id,
                characters,
            ),
        )
        return
    if action == "photo_ref_character":
        source_workspace_id = _optional_int(callback_data.value)
        if source_workspace_id is None or not await _can_access_source(
            database,
            user_id=callback.from_user.id,
            active_workspace_id=workspace_id,
            source_workspace_id=source_workspace_id,
        ):
            await callback.answer("Источник архива недоступен.", show_alert=True)
            return
        added, total = await _add_character_references(
            state,
            database,
            source_workspace_id=source_workspace_id,
            character_id=callback_data.item_id,
        )
        await callback.answer(f"Добавлено: {added}. Всего фото: {total}.")
        await _advance(callback, state)
        return
    if action in {"photo_input_confirm", "photo_choose_model"}:
        await _show_models(callback, state, kie_settings)
        return
    if action == "photo_model":
        model = _model(callback_data.value)
        if model is None:
            await callback.answer("Неизвестная фото-модель.", show_alert=True)
            return
        if model.is_grs and not kie_settings.grs_api_key:
            await callback.answer(
                f"{model.display_name} требует GRS_API_KEY.",
                show_alert=True,
            )
            return
        try:
            kie_settings.models.provider_model(
                model,
                input_mode=KieInputMode.PHOTO_TEXT,
            )
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        _, prompt, references = await _session(state)
        if len(references) > model.max_photo_references:
            await callback.answer(
                f"{model.display_name} принимает максимум "
                f"{model.max_photo_references} фото. Уберите лишние.",
                show_alert=True,
            )
            return
        if len(prompt) > model.photo_prompt_limit:
            await callback.answer(
                f"{model.display_name} принимает промт до "
                f"{model.photo_prompt_limit} символов.",
                show_alert=True,
            )
            return
        await state.update_data(
            auf_model=model.value,
            auf_resolution="",
            auf_aspect_ratio="",
        )
        if len(model.supported_photo_resolutions) > 1:
            await _show_resolution(callback, state, model)
        else:
            await state.update_data(
                auf_resolution=model.supported_photo_resolutions[0]
            )
            await _show_ratios(callback, state, model)
        return
    if action in {"photo_choose_resolution", "photo_back_settings"}:
        model = _model((await state.get_data()).get("auf_model"))
        if model is None:
            await callback.answer("Сначала выберите модель.", show_alert=True)
            return
        if len(model.supported_photo_resolutions) > 1:
            await _show_resolution(callback, state, model)
        else:
            await _show_models(callback, state, kie_settings)
        return
    if action == "photo_resolution":
        model = _model((await state.get_data()).get("auf_model"))
        resolution = callback_data.value.upper()
        if model is None or resolution not in model.supported_photo_resolutions:
            await callback.answer("Недоступное качество.", show_alert=True)
            return
        await state.update_data(auf_resolution=resolution)
        await _show_ratios(callback, state, model)
        return
    if action == "photo_choose_ratio":
        model = _model((await state.get_data()).get("auf_model"))
        if model is None:
            await callback.answer("Сначала выберите модель.", show_alert=True)
            return
        await _show_ratios(callback, state, model)
        return
    if action == "photo_ratio":
        model = _model((await state.get_data()).get("auf_model"))
        ratio = callback_data.value
        if model is None or ratio not in model.supported_aspect_ratios:
            await callback.answer("Недоступное соотношение сторон.", show_alert=True)
            return
        await state.update_data(auf_aspect_ratio=ratio)
        await _show_final(callback, state, kie_settings)
        return
    if action == "photo_generate":
        await _enqueue(
            callback,
            state,
            kie_settings,
            ai_usage_service,
            ai_task_queue_service,
        )
        return
    await handle_auf_action(
        callback,
        callback_data,
        state,
        access_policy,
        kie_settings,
        database,
        ai_usage_service,
        ai_task_queue_service,
    )


async def handle_auf_photo_input(
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
        await message.answer("AI-генерация выключена на сервере.")
        return
    workspace_id, prompt, references = await _session(state)
    if not workspace_id:
        await state.clear()
        await message.answer("Сессия Ауф устарела. Откройте создание заново.")
        return
    if message.text:
        prompt = message.text.strip()
        if not prompt:
            await message.answer("Промт не может быть пустым.")
            return
        if len(prompt) > 8000:
            await message.answer("Промт слишком длинный. Максимум 8000 символов.")
            return
        await state.update_data(auf_prompt=prompt)
        await _advance(message, state)
        return
    if len(references) >= MAX_KIE_REFERENCES:
        await message.answer(
            f"Уже выбрано {MAX_KIE_REFERENCES} фото. Уберите лишнее на проверке."
        )
        return
    reference: KieReferenceImage | None = None
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
        suffix = Path(message.document.file_name or "reference.jpg").suffix.casefold()
        mime_type = (message.document.mime_type or "").strip().casefold()
        if not mime_type:
            mime_type = {".png": "image/png", ".webp": "image/webp"}.get(
                suffix,
                "image/jpeg",
            )
        reference = KieReferenceImage(
            telegram_file_id=message.document.file_id,
            telegram_file_unique_id=message.document.file_unique_id,
            source="upload",
            mime_type=mime_type,
            file_name=Path(message.document.file_name or "reference.jpg").name,
            file_size=message.document.file_size,
        )
    if reference is None:
        await message.answer("Отправьте текст, фото или файл JPG, PNG либо WEBP.")
        return
    duplicate = any(
        (
            reference.telegram_file_unique_id
            and item.telegram_file_unique_id == reference.telegram_file_unique_id
        )
        or item.telegram_file_id == reference.telegram_file_id
        for item in references
    )
    if not duplicate:
        await _save_references(state, (*references, reference))
    caption = (message.caption or "").strip()
    if caption:
        if len(caption) > 8000:
            await message.answer("Подпись слишком длинная. Максимум 8000 символов.")
            return
        await state.update_data(auf_prompt=caption)
    if duplicate:
        await message.answer("Это фото уже выбрано.")
    await _advance(message, state)


async def handle_auf_photo_command(
    message: Message,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
    database: Database,
) -> None:
    if not access_policy.allows_user(message.from_user):
        return
    if not kie_settings.enabled:
        await message.answer("AI-генерация выключена на сервере.")
        return
    workspace_id, _, _ = await _session(state)
    if not workspace_id:
        await message.answer("Сначала откройте «Ауф → Создать».")
        return
    raw = (message.text or "").strip().split(maxsplit=1)
    character_name = raw[1].strip() if len(raw) > 1 else ""
    if not character_name:
        sources = await _load_sources(
            database,
            user_id=message.from_user.id,
            active_workspace_id=workspace_id,
        )
        await message.answer(
            "<b>Откуда взять референсы?</b>",
            reply_markup=_source_keyboard(workspace_id, sources),
        )
        return
    async with database.acquire() as connection:
        character = await connection.fetchrow(
            """
            SELECT
                character.id,
                character.name,
                character.workspace_id
            FROM characters AS character
            JOIN workspaces AS workspace
              ON workspace.id = character.workspace_id
            LEFT JOIN workspace_members AS membership
              ON membership.workspace_id = workspace.id
             AND membership.user_id = $1::BIGINT
            WHERE (
                    workspace.is_system = TRUE
                 OR membership.user_id IS NOT NULL
                 OR workspace.id = $2::BIGINT
            )
              AND LOWER(character.name) = LOWER($3::TEXT)
              AND EXISTS (
                  SELECT 1
                  FROM character_references AS reference
                  WHERE reference.workspace_id = character.workspace_id
                    AND reference.character_id = character.id
              )
            ORDER BY
                CASE WHEN workspace.id = $2::BIGINT THEN 0
                     WHEN workspace.is_system THEN 1
                     ELSE 2 END,
                character.id
            LIMIT 1
            """,
            int(message.from_user.id),
            int(workspace_id),
            character_name,
        )
    if character is None:
        await message.answer(
            f"Персонаж «{escape(character_name)}» с референсами не найден."
        )
        return
    added, total = await _add_character_references(
        state,
        database,
        source_workspace_id=int(character["workspace_id"]),
        character_id=int(character["id"]),
    )
    await message.answer(
        f"Добавлено референсов «{escape(str(character['name']))}»: "
        f"<b>{added}</b>. Всего фото: <b>{total}</b>."
    )
    await _advance(message, state)


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _optional_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


__all__ = (
    "AufPhotoForm",
    "handle_auf_photo_action",
    "handle_auf_photo_command",
    "handle_auf_photo_input",
)
