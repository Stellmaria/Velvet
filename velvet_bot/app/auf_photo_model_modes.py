from __future__ import annotations

import asyncio
import importlib
import os
from dataclasses import replace
from decimal import Decimal, ROUND_CEILING
from html import escape
from pathlib import Path
from typing import Any, Mapping, Sequence

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AITaskRequest
from velvet_bot.domains.auf_wallet import AufPricingRepository, format_auf_units
from velvet_bot.domains.auf_wallet.models import AUF_SCALE
from velvet_bot.domains.media_generation import (
    KIE_GENERATION_TASK_TYPE,
    KieContentMode,
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
    KiePricing,
    KieReferenceImage,
)

from velvet_bot.infrastructure.ai import KieClient, KieProtocolError, KieTaskFailed
from velvet_bot.presentation.telegram.auf_editing import edit_or_answer_auf_callback
from velvet_bot.presentation.telegram.routers import workspace_auf_photo as photo_router
from velvet_bot.presentation.telegram.routers.workspace_auf import (
    _budget_block_reason,
    build_auf_root_keyboard,
)
from velvet_bot.reference_media import validate_reference_document

_INSTALLED = False
_MAX_PROMPT_MESSAGES = 2
_TEXT_MODEL_IDS = {
    KieModelAlias.QWEN2_IMAGE_EDIT: ("KIE_QWEN2_TEXT_MODEL", "qwen2/text-to-image"),
    KieModelAlias.FLUX_2_PRO_IMAGE: (
        "KIE_FLUX_2_PRO_TEXT_MODEL",
        "flux-2/pro-text-to-image",
    ),
}
_PHOTO_MODELS = (
    KieModelAlias.NANO_BANANA_2,
    KieModelAlias.NANO_BANANA_PRO,
    KieModelAlias.SEEDREAM_5_PRO,
    KieModelAlias.WAN_27_IMAGE,
)
_ORIGINAL_PROVIDER_MODEL = KieModelCatalog.provider_model
_ORIGINAL_TO_INPUT = KieGenerationRequest.to_input
_ORIGINAL_ESTIMATE_USD = KiePricing.estimate_usd
_ORIGINAL_WAIT_FOR_TASK = KieClient.wait_for_task
_ORIGINAL_PHOTO_ACTION = photo_router.handle_auf_photo_action


class ModelFirstPhotoForm(StatesGroup):
    choosing_model = State()
    choosing_mode = State()
    collecting_input = State()
    reviewing_input = State()
    choosing_resolution = State()
    choosing_aspect_ratio = State()
    choosing_format = State()
    choosing_wan_options = State()
    confirming_generation = State()


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


def _model(value: object) -> KieModelAlias | None:
    try:
        parsed = KieModelAlias(str(value or ""))
    except ValueError:
        return None
    return parsed if parsed in _PHOTO_MODELS else None


def _input_mode(value: object) -> KieInputMode | None:
    try:
        parsed = KieInputMode(str(value or ""))
    except ValueError:
        return None
    return parsed if parsed in {KieInputMode.TEXT, KieInputMode.PHOTO_TEXT} else None


def _state_value(data: Mapping[str, object], key: str) -> object:
    return photo_router._state_value(data, key)


def _references(data: Mapping[str, object]) -> tuple[KieReferenceImage, ...]:
    return photo_router._references(_state_value(data, "auf_references"))


def _prompt_parts(data: Mapping[str, object]) -> tuple[str, ...]:
    value = _state_value(data, "auf_prompt_parts")
    if isinstance(value, (list, tuple)):
        parts = tuple(str(item).strip() for item in value if str(item).strip())
        if parts:
            return parts[:_MAX_PROMPT_MESSAGES]
    legacy = str(_state_value(data, "auf_prompt") or "").strip()
    return (legacy,) if legacy else ()


def _joined_prompt(data: Mapping[str, object]) -> str:
    return "\n\n".join(_prompt_parts(data)).strip()


async def _save_prompt_parts(state: FSMContext, parts: Sequence[str]) -> None:
    cleaned = tuple(str(part).strip() for part in parts if str(part).strip())
    joined = "\n\n".join(cleaned).strip()
    await state.update_data(
        auf_prompt_parts=list(cleaned),
        auf_prompt=joined,
    )


def _prompt_limit(model: KieModelAlias) -> int:
    return model.photo_prompt_limit


def _mode_name(mode: KieInputMode) -> str:
    return "Только текст" if mode is KieInputMode.TEXT else "Фото + текст"


def _result_count(data: Mapping[str, object], model: KieModelAlias) -> int:
    if model is not KieModelAlias.WAN_27_IMAGE:
        return 1
    try:
        value = int(str(_state_value(data, "auf_wan_n") or "1"))
    except (TypeError, ValueError):
        return 1
    maximum = 12 if bool(_state_value(data, "auf_wan_sequential")) else 4
    return max(1, min(maximum, value))


def _wan_sequential(data: Mapping[str, object]) -> bool:
    return bool(_state_value(data, "auf_wan_sequential"))


def _output_format(data: Mapping[str, object], model: KieModelAlias) -> str:
    if model is not KieModelAlias.SEEDREAM_5_PRO:
        return "png"
    value = str(_state_value(data, "auf_output_format") or "").strip().casefold()
    return value if value in {"png", "jpeg"} else ""


def _inputs_ready(data: Mapping[str, object]) -> bool:
    model = _model(_state_value(data, "auf_model"))
    mode = _input_mode(_state_value(data, "auf_input_mode"))
    prompt = _joined_prompt(data)
    if model is None or mode is None or not prompt:
        return False
    if mode is KieInputMode.TEXT:
        return True
    return bool(_references(data))


def _model_keyboard(workspace_id: int, *, grs_enabled: bool = True) -> InlineKeyboardMarkup:
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
    rows.append([_button("Отмена", "cancel", workspace_id=workspace_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _mode_keyboard(workspace_id: int, model: KieModelAlias) -> InlineKeyboardMarkup:
    return _markup(
        [
            _button(
                "Только текст",
                "photo_mode",
                workspace_id=workspace_id,
                value=KieInputMode.TEXT.value,
            )
        ],
        [
            _button(
                "Фото + текст",
                "photo_mode",
                workspace_id=workspace_id,
                value=KieInputMode.PHOTO_TEXT.value,
            )
        ],
        [_button("К моделям", "photo_choose_model", workspace_id=workspace_id)],
        [_button("Отмена", "cancel", workspace_id=workspace_id)],
    )


def _model_card(model: KieModelAlias) -> str:
    resolutions = ", ".join(model.supported_photo_resolutions)
    return (
        f"<b>{escape(model.display_name)}</b>\n\n"
        "Режимы: <b>только текст</b> или <b>фото + текст</b>.\n"
        f"Референсы: <b>до {model.max_photo_references}</b>.\n"
        "Максимальный размер одного файла: <b>10 МБ</b>.\n"
        f"Промт: <b>до {model.photo_prompt_limit} символов</b>, "
        "можно отправить двумя сообщениями.\n"
        f"Качество: <b>{escape(resolutions)}</b>.\n\n"
        "Выберите способ генерации."
    )


def _input_keyboard(
    workspace_id: int,
    *,
    mode: KieInputMode,
    prompt_parts: int,
    reference_count: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if mode is KieInputMode.PHOTO_TEXT:
        rows.append(
            [
                _button(
                    "Референсы из базы",
                    "photo_ref_sources",
                    workspace_id=workspace_id,
                )
            ]
        )
        if reference_count:
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
                    "photo_edit_prompt",
                    workspace_id=workspace_id,
                )
            ]
        )
    rows.extend(
        [
            [_button("К проверке", "photo_review", workspace_id=workspace_id)],
            [
                _button(
                    "Изменить режим",
                    "photo_change_mode",
                    workspace_id=workspace_id,
                ),
                _button(
                    "Изменить модель",
                    "photo_choose_model",
                    workspace_id=workspace_id,
                ),
            ],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _input_text(
    model: KieModelAlias,
    mode: KieInputMode,
    prompt: str,
    parts: tuple[str, ...],
    references: tuple[KieReferenceImage, ...],
) -> str:
    remaining = max(0, model.photo_prompt_limit - len(prompt))
    lines = [
        f"<b>{escape(model.display_name)} · {_mode_name(mode)}</b>",
        "",
        f"Промт: <b>{len(prompt)}/{model.photo_prompt_limit}</b> символов.",
        f"Частей текста: <b>{len(parts)}/{_MAX_PROMPT_MESSAGES}</b>.",
        f"Можно дописать ещё: <b>{remaining}</b> символов.",
    ]
    if mode is KieInputMode.PHOTO_TEXT:
        lines.extend(
            [
                f"Референсы: <b>{len(references)}/{model.max_photo_references}</b>.",
                "Максимальный размер одного файла: <b>10 МБ</b>.",
                "",
                "Отправьте JPG, PNG, WEBP или Telegram-фото. "
                "Подпись к фото станет частью промта.",
            ]
        )
    else:
        lines.extend(["", "Отправьте текстовый промт. Фото в этом режиме не требуется."])
    lines.extend(
        [
            "",
            "Промт можно отправить одним или двумя сообщениями. "
            "Бот ничего не обрезает молча.",
        ]
    )
    return "\n".join(lines)


def _review_keyboard(
    workspace_id: int,
    *,
    mode: KieInputMode,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [_button("Да, всё верно", "photo_input_confirm", workspace_id=workspace_id)],
        [_button("Изменить текст", "photo_edit_prompt", workspace_id=workspace_id)],
    ]
    if mode is KieInputMode.PHOTO_TEXT:
        rows.append(
            [_button("Изменить референсы", "photo_input_back", workspace_id=workspace_id)]
        )
    rows.extend(
        [
            [_button("Изменить режим", "photo_change_mode", workspace_id=workspace_id)],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _review_text(
    model: KieModelAlias,
    mode: KieInputMode,
    prompt: str,
    references: tuple[KieReferenceImage, ...],
) -> str:
    lines = [
        "<b>Проверьте исходные данные</b>",
        "",
        f"Модель: <b>{escape(model.display_name)}</b>",
        f"Режим: <b>{_mode_name(mode)}</b>",
    ]
    if mode is KieInputMode.PHOTO_TEXT:
        lines.extend(
            [
                f"Референсы: <b>{len(references)}/{model.max_photo_references}</b>",
                "Один файл: <b>до 10 МБ</b>",
            ]
        )
    lines.extend(
        [
            f"Промт: <b>{len(prompt)}/{model.photo_prompt_limit}</b> символов",
            "",
            f"<b>Текст</b>\n{escape(photo_router._truncate(prompt, 3000))}",
            "",
            "После подтверждения выбираются качество и соотношение сторон.",
        ]
    )
    return "\n".join(lines)


def _resolution_keyboard(workspace_id: int, model: KieModelAlias) -> InlineKeyboardMarkup:
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
            [_button("К вводу", "photo_review", workspace_id=workspace_id)],
            [_button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [_button("PNG", "photo_format", workspace_id=workspace_id, value="png")],
        [_button("JPEG", "photo_format", workspace_id=workspace_id, value="jpeg")],
        [_button("К соотношению сторон", "photo_choose_ratio", workspace_id=workspace_id)],
        [_button("Отмена", "cancel", workspace_id=workspace_id)],
    )


def _wan_keyboard(
    workspace_id: int,
    *,
    n: int,
    sequential: bool,
) -> InlineKeyboardMarkup:
    maximum = 12 if sequential else 4
    values = range(1, maximum + 1)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for value in values:
        row.append(
            _button(
                f"✓ {value}" if value == n else str(value),
                "photo_wan_n",
                workspace_id=workspace_id,
                value=str(value),
            )
        )
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.extend(
        [
            [
                _button(
                    (
                        "Связная серия: включена"
                        if sequential
                        else "Связная серия: выключена"
                    ),
                    "photo_wan_seq",
                    workspace_id=workspace_id,
                    value="off" if sequential else "on",
                )
            ],
            [_button("Продолжить", "photo_wan_done", workspace_id=workspace_id)],
            [_button("К соотношению сторон", "photo_choose_ratio", workspace_id=workspace_id)],
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
        [
            _button("Модель", "photo_choose_model", workspace_id=workspace_id),
            _button("Режим", "photo_change_mode", workspace_id=workspace_id),
        ],
        [_button("Текст", "photo_edit_prompt", workspace_id=workspace_id)],
    ]
    # Mode is checked at action time, so the reference editor can safely reject text-only.
    rows.append([_button("Исходные данные", "photo_input_back", workspace_id=workspace_id)])
    if len(model.supported_photo_resolutions) > 1:
        rows.append(
            [_button("Качество", "photo_choose_resolution", workspace_id=workspace_id)]
        )
    if len(model.supported_aspect_ratios) > 1:
        rows.append(
            [_button("Соотношение сторон", "photo_choose_ratio", workspace_id=workspace_id)]
        )
    if model is KieModelAlias.SEEDREAM_5_PRO:
        rows.append(
            [_button("Формат файла", "photo_choose_format", workspace_id=workspace_id)]
        )
    if model is KieModelAlias.WAN_27_IMAGE:
        rows.append(
            [_button("Количество и серия", "photo_wan_settings", workspace_id=workspace_id)]
        )
    rows.append([_button("Отмена", "cancel", workspace_id=workspace_id)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_models(
    event: CallbackQuery,
    state: FSMContext,
    kie_settings: Any,
) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    await state.set_state(ModelFirstPhotoForm.choosing_model)
    await edit_or_answer_auf_callback(
        event,
        text=(
            "<b>Выберите модель изображения</b>\n\n"
            "Сначала выбирается модель, затем режим и исходные данные. "
            "Уже отправленные фото и текст сохраняются при переходе между настройками."
        ),
        reply_markup=_model_keyboard(
            workspace_id,
            grs_enabled=bool(kie_settings.grs_api_key),
        ),
    )


async def _show_modes(
    event: CallbackQuery,
    state: FSMContext,
    model: KieModelAlias,
) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    await state.set_state(ModelFirstPhotoForm.choosing_mode)
    await edit_or_answer_auf_callback(
        event,
        text=_model_card(model),
        reply_markup=_mode_keyboard(workspace_id, model),
    )


async def _show_input(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    model = _model(_state_value(data, "auf_model"))
    mode = _input_mode(_state_value(data, "auf_input_mode"))
    if model is None or mode is None:
        if isinstance(event, CallbackQuery):
            await event.answer("Сначала выберите модель и режим.", show_alert=True)
        else:
            await event.answer("Сессия устарела. Выберите модель заново.")
        return
    parts = _prompt_parts(data)
    prompt = "\n\n".join(parts).strip()
    references = _references(data)
    await state.set_state(ModelFirstPhotoForm.collecting_input)
    text = _input_text(model, mode, prompt, parts, references)
    keyboard = _input_keyboard(
        workspace_id,
        mode=mode,
        prompt_parts=len(parts),
        reference_count=len(references),
    )
    if isinstance(event, CallbackQuery):
        await edit_or_answer_auf_callback(event, text=text, reply_markup=keyboard)
    else:
        await event.answer(text, reply_markup=keyboard)


async def _show_review(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    model = _model(_state_value(data, "auf_model"))
    mode = _input_mode(_state_value(data, "auf_input_mode"))
    prompt = _joined_prompt(data)
    references = _references(data)
    error: str | None = None
    if model is None or mode is None:
        error = "Сначала выберите модель и режим."
    elif not prompt:
        error = "Сначала добавьте текстовый промт."
    elif mode is KieInputMode.PHOTO_TEXT and not references:
        error = "Сначала добавьте хотя бы один референс."
    elif len(prompt) > model.photo_prompt_limit:
        error = f"Промт превышает лимит {model.photo_prompt_limit} символов."
    elif len(references) > model.max_photo_references:
        error = f"Модель принимает не больше {model.max_photo_references} референсов."
    if error:
        if isinstance(event, CallbackQuery):
            await event.answer(error, show_alert=True)
        else:
            await event.answer(error)
        return
    await state.set_state(ModelFirstPhotoForm.reviewing_input)
    text = _review_text(model, mode, prompt, references)
    keyboard = _review_keyboard(workspace_id, mode=mode)
    if isinstance(event, CallbackQuery):
        await edit_or_answer_auf_callback(event, text=text, reply_markup=keyboard)
    else:
        await event.answer(text, reply_markup=keyboard)


async def _show_resolution(
    callback: CallbackQuery,
    state: FSMContext,
    model: KieModelAlias,
) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    await state.set_state(ModelFirstPhotoForm.choosing_resolution)
    await edit_or_answer_auf_callback(
        callback,
        text=(
            f"<b>{escape(model.display_name)} · качество</b>\n\n"
            "Выберите разрешение результата."
        ),
        reply_markup=_resolution_keyboard(workspace_id, model),
    )


async def _show_ratios(
    callback: CallbackQuery,
    state: FSMContext,
    model: KieModelAlias,
) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    await state.set_state(ModelFirstPhotoForm.choosing_aspect_ratio)
    await edit_or_answer_auf_callback(
        callback,
        text=f"<b>{escape(model.display_name)} · соотношение сторон</b>",
        # The callback-safe ratio installer replaces this function later.
        reply_markup=photo_router._ratio_keyboard(workspace_id, model),
    )


async def _show_format(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    await state.set_state(ModelFirstPhotoForm.choosing_format)
    await edit_or_answer_auf_callback(
        callback,
        text=(
            "<b>Seedream 5 Pro · формат файла</b>\n\n"
            "PNG сохраняет изображение без потерь. JPEG обычно занимает меньше места."
        ),
        reply_markup=_format_keyboard(workspace_id),
    )


async def _show_wan_options(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    sequential = _wan_sequential(data)
    n = _result_count(data, KieModelAlias.WAN_27_IMAGE)
    maximum = 12 if sequential else 4
    if n > maximum:
        n = maximum
        await state.update_data(auf_wan_n=n)
    await state.set_state(ModelFirstPhotoForm.choosing_wan_options)
    await edit_or_answer_auf_callback(
        callback,
        text=(
            "<b>Wan 2.7 Image · количество результатов</b>\n\n"
            f"Изображений: <b>{n}</b>.\n"
            f"Связная серия: <b>{'включена' if sequential else 'выключена'}</b>.\n\n"
            "При включённой серии модель создаёт связанные последовательные кадры. "
            "Стоимость увеличивается пропорционально количеству изображений."
        ),
        reply_markup=_wan_keyboard(
            workspace_id,
            n=n,
            sequential=sequential,
        ),
    )


def _infer_ratio(prompt: str, model: KieModelAlias) -> str:
    return photo_router._infer_ratio(prompt, model)


def _request(data: Mapping[str, object]) -> KieGenerationRequest:
    model = _model(_state_value(data, "auf_model"))
    mode = _input_mode(_state_value(data, "auf_input_mode"))
    if model is None:
        raise ValueError("Сначала выберите модель.")
    if mode is None:
        raise ValueError("Сначала выберите режим.")
    prompt = _joined_prompt(data)
    references = _references(data) if mode is KieInputMode.PHOTO_TEXT else ()
    resolution = str(_state_value(data, "auf_resolution") or "").strip().upper()
    if not resolution:
        resolution = model.supported_photo_resolutions[-1]
    ratio = str(_state_value(data, "auf_aspect_ratio") or "").strip()
    if not ratio:
        ratio = _infer_ratio(prompt, model)
    output_format = _output_format(data, model) or "png"
    extra_input: dict[str, object] = {}
    if model is KieModelAlias.WAN_27_IMAGE:
        extra_input = {
            "n": _result_count(data, model),
            "enable_sequential": _wan_sequential(data),
        }
    return KieGenerationRequest(
        model=model,
        input_mode=mode,
        prompt=prompt,
        references=references,
        content_mode=KieContentMode.MATURE,
        aspect_ratio=ratio,
        resolution=resolution,
        output_format=output_format,
        extra_input=extra_input,
    )


async def _show_wallet_final(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    database: Any,
    wallet_service: Any,
) -> None:
    data = await state.get_data()
    request = _request(data)
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    if request.model is KieModelAlias.SEEDREAM_5_PRO and not _output_format(
        data, request.model
    ):
        await _show_format(callback, state)
        return
    if request.model is KieModelAlias.WAN_27_IMAGE and not bool(
        _state_value(data, "auf_wan_configured")
    ):
        await _show_wan_options(callback, state)
        return

    quote = await AufPricingRepository(database).quote(
        {
            "workspace_id": workspace_id,
            "request": request.to_task_payload(),
        }
    )
    await state.update_data(
        auf_expected_price_version=quote.version_key,
        auf_expected_quoted_units=quote.quoted_units,
    )
    overview = await wallet_service.overview(
        workspace_id=workspace_id,
        actor_user_id=callback.from_user.id,
        history_limit=1,
    )
    global_owner = wallet_service.is_global_owner(callback.from_user.id)
    available_units = overview.wallet.available_units
    enough = global_owner or available_units >= quote.quoted_units
    remaining_units = max(0, available_units - quote.quoted_units)
    if global_owner:
        wallet_line = (
            f"Учётная цена: <b>{format_auf_units(quote.quoted_units, max_places=0)}</b>\n"
            "Списание Стэл: <b>0 вельветов</b>"
        )
    elif enough:
        wallet_line = (
            f"Цена: <b>{format_auf_units(quote.quoted_units, max_places=0)}</b>\n"
            f"Доступно: <b>{format_auf_units(available_units)}</b>\n"
            f"Останется: <b>{format_auf_units(remaining_units)}</b>"
        )
    else:
        missing = quote.quoted_units - available_units
        wallet_line = (
            f"Цена: <b>{format_auf_units(quote.quoted_units, max_places=0)}</b>\n"
            f"Доступно: <b>{format_auf_units(available_units)}</b>\n"
            f"Не хватает: <b>{format_auf_units(missing)}</b>"
        )

    owner_block = ""
    if global_owner:
        owner_block = (
            "\n\n<b>Служебная экономика · только Стэл</b>\n"
            f"Себестоимость: <b>${quote.provider_cost_usd:.4f}</b> · "
            f"<b>{quote.provider_cost_rub:.2f} ₽ РФ</b> · "
            f"<b>{quote.provider_cost_byn:.2f} Br</b>\n"
            f"Цена +{quote.markup_percent}%: <b>${quote.target_retail_usd:.4f}</b> · "
            f"<b>{quote.target_retail_rub:.2f} ₽ РФ</b> · "
            f"<b>{quote.target_retail_byn:.2f} Br</b>"
        )

    ratio = "как у исходника" if request.aspect_ratio == "auto" else request.aspect_ratio
    lines = [
        "<b>Проверьте перед созданием</b>",
        "",
        f"Модель: <b>{escape(request.model.display_name)}</b>",
        f"Режим: <b>{_mode_name(request.input_mode)}</b>",
    ]
    if request.input_mode is KieInputMode.PHOTO_TEXT:
        lines.append(
            f"Референсы: <b>{len(request.references)}/{request.model.max_photo_references}</b>"
        )
    lines.extend(
        [
            f"Промт: <b>{len(request.prompt)}/{request.model.photo_prompt_limit}</b> символов",
            f"Качество: <b>{escape(request.resolution)}</b>",
            f"Соотношение: <b>{escape(ratio)}</b>",
        ]
    )
    if request.model is KieModelAlias.SEEDREAM_5_PRO:
        lines.append(
            f"Формат: <b>{'PNG' if request.output_format == 'png' else 'JPEG'}</b>"
        )
    count = int(request.extra_input.get("n", 1))
    lines.append(f"Результатов: <b>{count}</b>")
    if request.model is KieModelAlias.WAN_27_IMAGE:
        lines.append(
            f"Связная серия: <b>{'включена' if request.extra_input.get('enable_sequential') else 'выключена'}</b>"
        )
    lines.extend(
        [
            "",
            "<b>Стоимость в вельветах</b>",
            wallet_line + owner_block,
            "",
            f"<b>Текст</b>\n{escape(photo_router._truncate(request.prompt, 2200))}",
            "",
            "<i>Цена фиксируется при подтверждении. Если тариф изменится до запуска, "
            "бот попросит подтвердить новую сумму.</i>",
        ]
    )
    await state.set_state(ModelFirstPhotoForm.confirming_generation)
    photo_ui = importlib.import_module("velvet_bot.app.auf_photo_ui_install")
    await edit_or_answer_auf_callback(
        callback,
        text="\n".join(lines),
        reply_markup=photo_ui._final_keyboard(
            workspace_id=workspace_id,
            model=request.model,
            quoted_units=quote.quoted_units,
        ),
    )


async def _enqueue_photo(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    kie_settings: Any,
    ai_usage_service: Any,
    ai_task_queue_service: Any,
    database: Any,
) -> None:
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    request = _request(data)
    expected_version = str(data.get("auf_expected_price_version") or "").strip()
    expected_units = int(data.get("auf_expected_quoted_units") or 0)
    if not expected_version or expected_units <= 0:
        await callback.answer(
            "Цена устарела. Вернитесь к настройкам и подтвердите её снова.",
            show_alert=True,
        )
        return
    rub = kie_settings.pricing.estimate_rub(
        request,
        usd_to_rub=kie_settings.usd_to_rub,
    )
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
                "auf_expected_price_version": expected_version,
                "auf_expected_quoted_units": expected_units,
            },
            priority=40,
            max_attempts=3,
            created_by=callback.from_user.id,
            estimated_cost_rub=rub,
        )
    )
    await state.clear()
    count = int(request.extra_input.get("n", 1))
    await edit_or_answer_auf_callback(
        callback,
        text=(
            f"<b>Ауф · {escape(request.model.display_name)}</b>\n\n"
            "Данные зафиксированы, задача поставлена в очередь.\n\n"
            f"Режим: <b>{_mode_name(request.input_mode)}</b>\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Результатов: <b>{count}</b>\n"
            f"Зарезервировано: <b>{format_auf_units(expected_units)}</b>\n"
            f"Задача: <code>{result.task.id}</code>"
        ),
        reply_markup=build_auf_root_keyboard(
            workspace_id=workspace_id,
            enabled=True,
        ),
    )


async def _add_character_references(
    state: FSMContext,
    database: Any,
    *,
    source_workspace_id: int,
    character_id: int,
) -> tuple[int, int, int]:
    data = await state.get_data()
    model = _model(_state_value(data, "auf_model"))
    if model is None:
        return 0, len(_references(data)), 0
    current = list(_references(data))
    is_system, rows = await photo_router._load_character_reference_rows(
        database,
        source_workspace_id=source_workspace_id,
        character_id=character_id,
    )
    source = "system" if is_system else "personal"
    added = 0
    skipped = 0
    for row in rows:
        if len(current) >= model.max_photo_references:
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


async def _handle_action(
    callback: CallbackQuery,
    callback_data: Any,
    state: FSMContext,
    access_policy: Any,
    kie_settings: Any,
    database: Any,
    ai_usage_service: Any,
    ai_task_queue_service: Any,
) -> None:
    if not access_policy.allows_user(callback.from_user):
        await callback.answer("Ауф доступен только владельцу пространства.", show_alert=True)
        return
    action = callback_data.action
    workspace_id = callback_data.workspace_id
    if action == "cancel":
        await state.clear()
        await edit_or_answer_auf_callback(
            callback,
            text="<b>Ауф</b>\n\nГенерация отменена.",
            reply_markup=build_auf_root_keyboard(
                workspace_id=workspace_id,
                enabled=kie_settings.enabled,
            ),
        )
        return
    if not kie_settings.enabled:
        await callback.answer("Генерация сейчас недоступна.", show_alert=True)
        return
    if action == "create":
        await state.clear()
        await state.update_data(
            auf_workspace_id=workspace_id,
            auf_model="",
            auf_input_mode="",
            auf_prompt="",
            auf_prompt_parts=[],
            auf_references=[],
            auf_resolution="",
            auf_aspect_ratio="",
            auf_output_format="",
            auf_wan_n=1,
            auf_wan_sequential=False,
            auf_wan_configured=False,
        )
        await _show_models(callback, state, kie_settings)
        return
    if action == "photo_choose_model":
        await _show_models(callback, state, kie_settings)
        return
    if action == "photo_model":
        model = _model(callback_data.value)
        if model is None:
            await callback.answer("Неизвестная модель.", show_alert=True)
            return
        if model.is_grs and not kie_settings.grs_api_key:
            await callback.answer("Эта модель сейчас недоступна.", show_alert=True)
            return
        await state.update_data(
            auf_model=model.value,
            auf_input_mode="",
            auf_resolution="",
            auf_aspect_ratio="",
            auf_output_format="",
            auf_wan_n=1,
            auf_wan_sequential=False,
            auf_wan_configured=False,
        )
        await _show_modes(callback, state, model)
        return
    if action == "photo_change_mode":
        model = _model(_state_value(await state.get_data(), "auf_model"))
        if model is None:
            await _show_models(callback, state, kie_settings)
            return
        await _show_modes(callback, state, model)
        return
    if action == "photo_mode":
        data = await state.get_data()
        model = _model(_state_value(data, "auf_model"))
        mode = _input_mode(callback_data.value)
        if model is None or mode is None:
            await callback.answer("Сначала выберите модель и режим.", show_alert=True)
            return
        updates: dict[str, object] = {
            "auf_input_mode": mode.value,
            "auf_resolution": "",
            "auf_aspect_ratio": "",
            "auf_output_format": "",
            "auf_wan_configured": False,
        }
        if mode is KieInputMode.TEXT:
            updates["auf_references"] = []
        await state.update_data(**updates)
        await _show_input(callback, state)
        return
    if action in {"photo_input_back", "photo_add_upload", "photo_edit_refs"}:
        data = await state.get_data()
        mode = _input_mode(_state_value(data, "auf_input_mode"))
        if mode is KieInputMode.TEXT and action == "photo_edit_refs":
            await callback.answer("В режиме «Только текст» референсы не используются.", show_alert=True)
            return
        await _show_input(callback, state)
        return
    if action == "photo_review":
        await _show_review(callback, state)
        return
    if action == "photo_edit_prompt":
        await _save_prompt_parts(state, ())
        await _show_input(callback, state)
        return
    if action == "photo_clear_refs":
        await photo_router._save_references(state, ())
        await _show_input(callback, state)
        return
    if action == "photo_remove_last":
        data = await state.get_data()
        references = _references(data)
        if not references:
            await callback.answer("Референсов уже нет.", show_alert=True)
            return
        await photo_router._save_references(state, references[:-1])
        await _show_input(callback, state)
        return
    if action == "photo_ref_sources":
        data = await state.get_data()
        if _input_mode(_state_value(data, "auf_input_mode")) is not KieInputMode.PHOTO_TEXT:
            await callback.answer("Референсы доступны только в режиме «Фото + текст».", show_alert=True)
            return
        sources = await photo_router._load_sources(
            database,
            user_id=callback.from_user.id,
            active_workspace_id=workspace_id,
        )
        if not sources:
            await callback.answer("Доступные базы не найдены.", show_alert=True)
            return
        await edit_or_answer_auf_callback(
            callback,
            text="<b>Откуда взять референсы?</b>\n\nОдин файл может быть не больше 10 МБ.",
            reply_markup=photo_router._source_keyboard(workspace_id, sources),
        )
        return
    if action == "photo_ref_workspace":
        source_workspace_id = callback_data.item_id
        if not await photo_router._can_access_source(
            database,
            user_id=callback.from_user.id,
            active_workspace_id=workspace_id,
            source_workspace_id=source_workspace_id,
        ):
            await callback.answer("Нет доступа к этой базе.", show_alert=True)
            return
        characters = await photo_router._load_characters(database, source_workspace_id)
        if not characters:
            await callback.answer("В этой базе нет персонажей с референсами.", show_alert=True)
            return
        model = _model(_state_value(await state.get_data(), "auf_model"))
        await edit_or_answer_auf_callback(
            callback,
            text=(
                "<b>Выберите персонажа</b>\n\n"
                f"Будут добавлены референсы до лимита <b>{model.max_photo_references if model else 0}</b>. "
                "Один файл может быть не больше 10 МБ."
            ),
            reply_markup=photo_router._character_keyboard(
                workspace_id,
                source_workspace_id,
                characters,
            ),
        )
        return
    if action == "photo_ref_character":
        source_workspace_id = photo_router._optional_int(callback_data.value)
        if source_workspace_id is None or not await photo_router._can_access_source(
            database,
            user_id=callback.from_user.id,
            active_workspace_id=workspace_id,
            source_workspace_id=source_workspace_id,
        ):
            await callback.answer("Источник недоступен.", show_alert=True)
            return
        added, total, skipped = await _add_character_references(
            state,
            database,
            source_workspace_id=source_workspace_id,
            character_id=callback_data.item_id,
        )
        text = f"Добавлено: {added}. Всего референсов: {total}."
        if skipped:
            text += f" Не добавлено из-за лимита: {skipped}."
        await callback.answer(text)
        await _show_input(callback, state)
        return
    if action == "photo_input_confirm":
        data = await state.get_data()
        if not _inputs_ready(data):
            await callback.answer("Не хватает текста или референсов.", show_alert=True)
            return
        model = _model(_state_value(data, "auf_model"))
        assert model is not None
        if len(model.supported_photo_resolutions) > 1:
            await _show_resolution(callback, state, model)
        else:
            await state.update_data(auf_resolution=model.supported_photo_resolutions[0])
            await _show_ratios(callback, state, model)
        return
    if action in {"photo_choose_resolution", "photo_back_settings"}:
        model = _model(_state_value(await state.get_data(), "auf_model"))
        if model is None:
            await callback.answer("Сначала выберите модель.", show_alert=True)
            return
        await _show_resolution(callback, state, model)
        return
    if action == "photo_resolution":
        model = _model(_state_value(await state.get_data(), "auf_model"))
        resolution = str(callback_data.value).upper()
        if model is None or resolution not in model.supported_photo_resolutions:
            await callback.answer("Недоступное качество.", show_alert=True)
            return
        await state.update_data(auf_resolution=resolution)
        await _show_ratios(callback, state, model)
        return
    if action == "photo_choose_ratio":
        model = _model(_state_value(await state.get_data(), "auf_model"))
        if model is None:
            await callback.answer("Сначала выберите модель.", show_alert=True)
            return
        await _show_ratios(callback, state, model)
        return
    if action == "photo_choose_format":
        model = _model(_state_value(await state.get_data(), "auf_model"))
        if model is not KieModelAlias.SEEDREAM_5_PRO:
            await callback.answer("Формат для этой модели задаётся автоматически.", show_alert=True)
            return
        await _show_format(callback, state)
        return
    if action == "photo_format":
        await callback.answer("Формат будет применён на следующем экране.", show_alert=True)
        return
    if action == "photo_wan_settings":
        await _show_wan_options(callback, state)
        return
    if action == "photo_wan_seq":
        sequential = callback_data.value == "on"
        data = await state.get_data()
        n = _result_count(data, KieModelAlias.WAN_27_IMAGE)
        if not sequential and n > 4:
            n = 4
        await state.update_data(
            auf_wan_sequential=sequential,
            auf_wan_n=n,
            auf_wan_configured=False,
        )
        await _show_wan_options(callback, state)
        return
    if action == "photo_wan_n":
        data = await state.get_data()
        sequential = _wan_sequential(data)
        try:
            n = int(callback_data.value)
        except (TypeError, ValueError):
            n = 0
        maximum = 12 if sequential else 4
        if not 1 <= n <= maximum:
            await callback.answer("Недоступное количество результатов.", show_alert=True)
            return
        await state.update_data(auf_wan_n=n, auf_wan_configured=False)
        await _show_wan_options(callback, state)
        return
    if action == "photo_wan_done":
        await callback.answer("Настройки будут применены на следующем экране.", show_alert=True)
        return
    # photo_ratio and photo_generate are intercepted by the installed wallet layer.
    await _ORIGINAL_PHOTO_ACTION(
        callback,
        callback_data,
        state,
        access_policy,
        kie_settings,
        database,
        ai_usage_service,
        ai_task_queue_service,
    )


async def _append_prompt_from_message(
    message: Message,
    state: FSMContext,
    *,
    text: str,
) -> bool:
    data = await state.get_data()
    model = _model(_state_value(data, "auf_model"))
    if model is None:
        await message.answer("Сначала выберите модель.")
        return False
    parts = _prompt_parts(data)
    normalized = text.strip()
    if not normalized:
        await message.answer("Промт не может быть пустым.")
        return False
    if len(parts) >= _MAX_PROMPT_MESSAGES:
        await message.answer(
            "Промт уже состоит из двух сообщений. Очистите текст, чтобы заменить его."
        )
        return False
    candidate = (*parts, normalized)
    joined = "\n\n".join(candidate)
    if len(joined) > model.photo_prompt_limit:
        separator = 2 if parts else 0
        remaining = max(0, model.photo_prompt_limit - len("\n\n".join(parts)) - separator)
        await message.answer(
            f"Для {model.display_name} осталось {remaining} символов. "
            f"Новая часть содержит {len(normalized)} и не была добавлена."
        )
        return False
    await _save_prompt_parts(state, candidate)
    return True


async def _handle_input(
    message: Message,
    state: FSMContext,
    access_policy: Any,
    kie_settings: Any,
) -> None:
    if not access_policy.allows_user(message.from_user):
        await state.clear()
        return
    if not kie_settings.enabled:
        await state.clear()
        await message.answer("Генерация сейчас недоступна.")
        return
    data = await state.get_data()
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    model = _model(_state_value(data, "auf_model"))
    mode = _input_mode(_state_value(data, "auf_input_mode"))
    if not workspace_id or model is None or mode is None:
        await state.clear()
        await message.answer("Сессия устарела. Откройте создание изображения заново.")
        return
    if message.text:
        added = await _append_prompt_from_message(message, state, text=message.text)
        if added:
            data = await state.get_data()
            if len(_prompt_parts(data)) >= _MAX_PROMPT_MESSAGES and _inputs_ready(data):
                await _show_review(message, state)
            else:
                await _show_input(message, state)
        return
    if mode is KieInputMode.TEXT:
        await message.answer("В режиме «Только текст» отправьте промт, а не изображение.")
        return
    references = _references(data)
    if len(references) >= model.max_photo_references:
        await message.answer(
            f"{model.display_name} принимает не больше {model.max_photo_references} референсов. "
            "Новое изображение не добавлено."
        )
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
    except ValueError as error:
        await message.answer(str(error))
        return
    if reference is None:
        await message.answer(
            "Отправьте текст, Telegram-фото или файл JPG, PNG либо WEBP до 10 МБ."
        )
        return
    duplicate = any(
        (
            reference.telegram_file_unique_id
            and item.telegram_file_unique_id == reference.telegram_file_unique_id
        )
        or item.telegram_file_id == reference.telegram_file_id
        for item in references
    )
    if duplicate:
        await message.answer("Это изображение уже выбрано.")
        return
    await photo_router._save_references(state, (*references, reference))
    caption = (message.caption or "").strip()
    if caption:
        await _append_prompt_from_message(message, state, text=caption)
    await _show_input(message, state)


async def _handle_command(
    message: Message,
    state: FSMContext,
    access_policy: Any,
    kie_settings: Any,
    database: Any,
) -> None:
    if not access_policy.allows_user(message.from_user):
        return
    data = await state.get_data()
    if _input_mode(_state_value(data, "auf_input_mode")) is not KieInputMode.PHOTO_TEXT:
        await message.answer("Референсы доступны только в режиме «Фото + текст».")
        return
    workspace_id = int(_state_value(data, "auf_workspace_id") or 0)
    model = _model(_state_value(data, "auf_model"))
    if not workspace_id or model is None:
        await message.answer("Сначала выберите модель.")
        return
    raw = (message.text or "").strip().split(maxsplit=1)
    character_name = raw[1].strip() if len(raw) > 1 else ""
    if not character_name:
        sources = await photo_router._load_sources(
            database,
            user_id=message.from_user.id,
            active_workspace_id=workspace_id,
        )
        await message.answer(
            (
                "<b>Откуда взять референсы?</b>\n\n"
                f"Лимит модели: <b>{model.max_photo_references}</b>. "
                "Один файл: <b>до 10 МБ</b>."
            ),
            reply_markup=photo_router._source_keyboard(workspace_id, sources),
        )
        return
    sources = await photo_router._load_sources(
        database,
        user_id=message.from_user.id,
        active_workspace_id=workspace_id,
    )
    character = None
    async with database.acquire() as connection:
        for source in sources:
            character = await connection.fetchrow(
                """
                SELECT id, name, workspace_id
                FROM characters
                WHERE workspace_id = $1::BIGINT
                  AND LOWER(name) = LOWER($2::TEXT)
                  AND EXISTS (
                      SELECT 1
                      FROM character_references AS reference
                      WHERE reference.workspace_id = characters.workspace_id
                        AND reference.character_id = characters.id
                  )
                ORDER BY id
                LIMIT 1
                """,
                int(source["id"]),
                character_name,
            )
            if character is not None:
                break
    if character is None:
        await message.answer(
            f"Персонаж «{escape(character_name)}» с референсами не найден."
        )
        return
    added, total, skipped = await _add_character_references(
        state,
        database,
        source_workspace_id=int(character["workspace_id"]),
        character_id=int(character["id"]),
    )
    suffix = f" Не добавлено из-за лимита: {skipped}." if skipped else ""
    await message.answer(
        f"Добавлено референсов «{escape(str(character['name']))}»: "
        f"<b>{added}</b>. Всего: <b>{total}/{model.max_photo_references}</b>.{suffix}"
    )
    await _show_input(message, state)


def _provider_model(
    self: KieModelCatalog,
    alias: KieModelAlias,
    *,
    input_mode: KieInputMode | None = None,
) -> str:
    if alias in _TEXT_MODEL_IDS and input_mode is KieInputMode.TEXT:
        variable, default = _TEXT_MODEL_IDS[alias]
        return os.getenv(variable, default).strip() or default
    if alias is KieModelAlias.NANO_BANANA_PRO:
        primary = os.getenv(
            "GRS_NANO_BANANA_PRO_VT_MODEL",
            "nano-banana-pro-vt",
        ).strip()
        return primary or "nano-banana-pro-vt"
    return _ORIGINAL_PROVIDER_MODEL(self, alias, input_mode=input_mode)


def _to_input(self: KieGenerationRequest) -> dict[str, object]:
    mature_override = self.content_mode is not KieContentMode.MATURE
    if self.model is KieModelAlias.QWEN2_IMAGE_EDIT:
        payload: dict[str, object] = {
            "prompt": self.provider_prompt,
            "image_size": self.aspect_ratio.strip(),
            "output_format": self.output_format.strip() or "png",
            "nsfw_checker": mature_override,
        }
        if self.input_mode is not KieInputMode.TEXT:
            payload["image_url"] = (
                self.image_urls[0]
                if len(self.image_urls) == 1
                else list(self.image_urls)
            )
        payload.update(dict(self.extra_input))
        return payload
    if self.model is KieModelAlias.WAN_27_IMAGE:
        n = max(1, int(self.extra_input.get("n", 1)))
        sequential = bool(self.extra_input.get("enable_sequential", False))
        maximum = 12 if sequential else 4
        payload = {
            "prompt": self.provider_prompt,
            "n": min(maximum, n),
            "enable_sequential": sequential,
            "resolution": self.resolution.upper(),
            "aspect_ratio": self.aspect_ratio.strip(),
            "nsfw_checker": mature_override,
        }
        if self.input_mode is not KieInputMode.TEXT:
            payload["input_urls"] = list(self.image_urls)
        return payload
    if self.model is KieModelAlias.FLUX_2_PRO_IMAGE:
        payload = {
            "prompt": self.provider_prompt,
            "aspect_ratio": self.aspect_ratio.strip(),
            "resolution": self.resolution.upper(),
            "nsfw_checker": mature_override,
        }
        if self.input_mode is not KieInputMode.TEXT:
            payload["input_urls"] = list(self.image_urls)
        payload.update(dict(self.extra_input))
        return payload
    return _ORIGINAL_TO_INPUT(self)


def _estimate_usd(self: KiePricing, request: KieGenerationRequest) -> Decimal:
    value = _ORIGINAL_ESTIMATE_USD(self, request)
    if request.model is KieModelAlias.WAN_27_IMAGE:
        try:
            n = max(1, int(request.extra_input.get("n", 1)))
        except (TypeError, ValueError):
            n = 1
        return value * Decimal(n)
    return value


async def _quote_with_wan_count(
    connection: Any,
    payload: Mapping[str, object],
) -> Any:
    pricing = importlib.import_module("velvet_bot.domains.auf_wallet.pricing")
    original_quote = getattr(pricing, "_original_model_first_quote")
    quote = await original_quote(connection, payload)
    request_value = payload.get("request")
    if not isinstance(request_value, Mapping):
        return quote
    if str(request_value.get("model") or "") != KieModelAlias.WAN_27_IMAGE.value:
        return quote
    extra = request_value.get("extra_input")
    extra_input = dict(extra) if isinstance(extra, Mapping) else {}
    try:
        n = max(1, int(extra_input.get("n", 1)))
    except (TypeError, ValueError):
        n = 1
    if n <= 1:
        return quote
    provider_cost = quote.provider_cost_usd * Decimal(n)
    target_retail_usd = provider_cost * (
        Decimal("1") + quote.markup_percent / Decimal("100")
    )
    package_floor_rub = await connection.fetchval(
        """
        SELECT MIN(price_rub / package_auf::NUMERIC)
        FROM auf_package_prices
        WHERE is_active = TRUE
          AND effective_from <= NOW()
          AND (effective_to IS NULL OR effective_to > NOW())
        """
    )
    if package_floor_rub is not None:
        minimum_rub_per_auf = Decimal(package_floor_rub)
    else:
        retail_auf_usd = await connection.fetchval(
            """
            SELECT retail_auf_usd
            FROM auf_economy_settings
            WHERE singleton_id = 1
            """
        )
        minimum_rub_per_auf = Decimal(retail_auf_usd) * quote.billing_usd_to_rub
    target_retail_rub = target_retail_usd * quote.billing_usd_to_rub
    whole_auf = max(
        1,
        int(
            (target_retail_rub / minimum_rub_per_auf).to_integral_value(
                rounding=ROUND_CEILING
            )
        ),
    )
    quoted_units = whole_auf * AUF_SCALE
    minimum_revenue_rub = minimum_rub_per_auf * Decimal(whole_auf)
    return replace(
        quote,
        provider_cost_usd=provider_cost,
        target_retail_usd=target_retail_usd,
        minimum_revenue_usd=minimum_revenue_rub / quote.billing_usd_to_rub,
        quoted_units=quoted_units,
    )


async def _submit_grs_model(
    client: KieClient,
    request: KieGenerationRequest,
    model_id: str,
) -> str:
    if client.grs_api_key is None:
        raise KieProtocolError("Сервис генерации не настроен.")
    payload = request.to_grs_input(model_id=model_id)
    payload["replyType"] = "async"
    response = await asyncio.to_thread(
        client._transport,
        "POST",
        f"{client.grs_base_url}/v1/api/generate",
        client._headers(client.grs_api_key),
        payload,
        client.timeout_seconds,
    )
    raw_task_id = str(response.get("id") or "").strip()
    if not raw_task_id:
        raise KieProtocolError(
            str(
                response.get("message")
                or response.get("msg")
                or response.get("error")
                or "Сервис генерации не вернул id задачи."
            )
        )
    task_id = f"grs:{raw_task_id}"
    client._grs_initial_responses[task_id] = dict(response)
    return task_id


async def _create_grs_with_vt_fallback(
    self: KieClient,
    request: KieGenerationRequest,
) -> str:
    primary_model = self.models.provider_model_for_request(request)
    task_id = await _submit_grs_model(self, request, primary_model)
    if request.model is KieModelAlias.NANO_BANANA_PRO:
        fallback = os.getenv(
            "GRS_NANO_BANANA_PRO_FALLBACK_MODEL",
            "nano-banana-pro",
        ).strip()
        if fallback and fallback != primary_model:
            mapping = getattr(self, "_grs_model_fallbacks", None)
            if not isinstance(mapping, dict):
                mapping = {}
                setattr(self, "_grs_model_fallbacks", mapping)
            mapping[task_id] = (request, fallback)
    return task_id


async def _wait_with_vt_fallback(
    self: KieClient,
    task_id: str,
    *,
    on_update: Any = None,
) -> Any:
    mapping = getattr(self, "_grs_model_fallbacks", None)
    try:
        result = await _ORIGINAL_WAIT_FOR_TASK(
            self,
            task_id,
            on_update=on_update,
        )
    except KieTaskFailed:
        fallback = mapping.pop(task_id, None) if isinstance(mapping, dict) else None
        if fallback is None:
            raise
        request, fallback_model = fallback
        fallback_task_id = await _submit_grs_model(
            self,
            request,
            fallback_model,
        )
        return await _ORIGINAL_WAIT_FOR_TASK(
            self,
            fallback_task_id,
            on_update=on_update,
        )
    else:
        if isinstance(mapping, dict):
            mapping.pop(task_id, None)
        return result


def install_auf_photo_model_modes() -> None:
    """Install model-first photo input, text routes and provider-safe fallbacks."""

    global _INSTALLED
    if _INSTALLED:
        return

    photo_ui = importlib.import_module("velvet_bot.app.auf_photo_ui_install")
    pricing = importlib.import_module("velvet_bot.domains.auf_wallet.pricing")

    photo_router.AufPhotoForm = ModelFirstPhotoForm  # type: ignore[assignment]
    photo_router._PHOTO_MODELS = _PHOTO_MODELS  # type: ignore[assignment]
    photo_router._model = _model  # type: ignore[assignment]
    photo_router._model_keyboard = _model_keyboard  # type: ignore[assignment]
    photo_router._input_keyboard = _input_keyboard  # type: ignore[assignment]
    photo_router._review_keyboard = _review_keyboard  # type: ignore[assignment]
    photo_router._resolution_keyboard = _resolution_keyboard  # type: ignore[assignment]
    photo_router._final_keyboard = _final_keyboard  # type: ignore[assignment]
    photo_router._request = _request  # type: ignore[assignment]
    photo_router.handle_auf_photo_action = _handle_action  # type: ignore[assignment]
    photo_router.handle_auf_photo_input = _handle_input  # type: ignore[assignment]
    photo_router.handle_auf_photo_command = _handle_command  # type: ignore[assignment]

    photo_ui._show_auf_final = _show_wallet_final
    photo_ui._enqueue_auf_photo = _enqueue_photo

    KieModelCatalog.provider_model = _provider_model  # type: ignore[method-assign]
    KieGenerationRequest.to_input = _to_input  # type: ignore[method-assign]
    KiePricing.estimate_usd = _estimate_usd  # type: ignore[method-assign]

    if not hasattr(pricing, "_original_model_first_quote"):
        setattr(pricing, "_original_model_first_quote", pricing.quote_auf_payload)
        pricing.quote_auf_payload = _quote_with_wan_count

    KieClient._create_grs_task = _create_grs_with_vt_fallback  # type: ignore[method-assign]
    KieClient.wait_for_task = _wait_with_vt_fallback  # type: ignore[method-assign]

    controller = importlib.import_module(
        "velvet_bot.presentation.telegram.workspace_home_controller"
    )
    original_controller_action = controller.handle_scoped_auf_action

    async def handle_scoped_auf_action_with_photo_options(
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
        if callback_data.action == "photo_format":
            if callback_data.value not in {"png", "jpeg"}:
                await callback.answer("Недоступный формат.", show_alert=True)
                return
            await state.update_data(auf_output_format=callback_data.value)
            await photo_ui._show_auf_final(
                callback,
                state,
                database=database,
                wallet_service=auf_wallet_service,
            )
            return
        if callback_data.action == "photo_wan_done":
            await state.update_data(auf_wan_configured=True)
            await photo_ui._show_auf_final(
                callback,
                state,
                database=database,
                wallet_service=auf_wallet_service,
            )
            return
        await original_controller_action(
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

    controller.handle_scoped_auf_action = handle_scoped_auf_action_with_photo_options
    _INSTALLED = True


__all__ = (
    "ModelFirstPhotoForm",
    "install_auf_photo_model_modes",
)
