from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Mapping
from uuid import uuid4

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
from velvet_bot.presentation.telegram.routers.workspace_auf_video import (
    AufVideoCallback,
    AufVideoForm,
    _callback as video_callback,
)
from velvet_bot.presentation.telegram.routers.workspace_auf import (
    AufCallback,
    build_auf_root_keyboard,
)


_GROK_MODEL_ID = "grok-imagine/image-to-video"
_GROK_15_MODEL_ID = "grok-imagine-video-1-5-preview"
_SEEDANCE_MODEL_ID = "bytedance/seedance-1.5-pro"
_WAN_MODEL_ID = "wan/2-7-image-to-video"
_MODEL_CODES = ("grok", "grok15", "seedance", "wan")
_MODEL_ALIASES = {
    "grok": KieModelAlias.GROK_IMAGINE_VIDEO,
    "grok15": KieModelAlias.GROK_IMAGINE_VIDEO_15,
    "seedance": KieModelAlias.SEEDANCE_15_PRO_VIDEO,
    # The internal alias is kept for queued-task compatibility. The provider route is Wan 2.7.
    "wan": KieModelAlias.WAN_26_IMAGE_TO_VIDEO,
}
_MODEL_NAMES = {
    "grok": "Grok Imagine v1",
    "grok15": "Grok Imagine Video 1.5",
    "seedance": "Seedance 1.5 Pro",
    "wan": "Wan 2.7",
}
_MODEL_EXPECTED_IDS = {
    "grok": _GROK_MODEL_ID,
    "grok15": _GROK_15_MODEL_ID,
    "seedance": _SEEDANCE_MODEL_ID,
    "wan": _WAN_MODEL_ID,
}
_GROK_RESOLUTIONS = ("480p", "720p")
_SEEDANCE_RESOLUTIONS = ("480p", "720p", "1080p")
_WAN_RESOLUTIONS = ("720p", "1080p")
_GROK_PRICING_DURATION_SECONDS = 6
_DEFAULT_VIDEO_DURATION_SECONDS = 5
_MIN_VIDEO_DURATION_SECONDS = 2
_MAX_VIDEO_DURATION_SECONDS = 15
_MAX_PROMPT_LENGTH = 5000
_WAN_MODES = ("first", "first_last")


def _selected(label: str, active: bool) -> str:
    return f"✓ {label}" if active else label


def build_video_model_keyboard(*, workspace_id: int, model: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_selected("Grok v1 · дёшево", model == "grok"), callback_data=video_callback("model", workspace_id=workspace_id, value="grok"))],
            [InlineKeyboardButton(text=_selected("Grok 1.5 · качество", model == "grok15"), callback_data=video_callback("model", workspace_id=workspace_id, value="grok15"))],
            [InlineKeyboardButton(text=_selected("Seedance 1.5 Pro", model == "seedance"), callback_data=video_callback("model", workspace_id=workspace_id, value="seedance"))],
            [InlineKeyboardButton(text=_selected("Wan 2.7", model == "wan"), callback_data=video_callback("model", workspace_id=workspace_id, value="wan"))],
            [
                InlineKeyboardButton(text="Изменить фото", callback_data=video_callback("change_photo", workspace_id=workspace_id)),
                InlineKeyboardButton(text="Изменить промт", callback_data=video_callback("change_prompt", workspace_id=workspace_id)),
            ],
            [InlineKeyboardButton(text="Отмена", callback_data=video_callback("cancel", workspace_id=workspace_id))],
        ]
    )


def build_video_settings_keyboard(
    *,
    workspace_id: int,
    model: str,
    resolution: str,
    duration: int,
    generate_audio: bool,
    wan_mode: str = "first",
    has_last_frame: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for values in _resolution_rows(model):
        rows.append([
            InlineKeyboardButton(
                text=_selected(item, item == resolution),
                callback_data=video_callback("resolution", workspace_id=workspace_id, value=item),
            )
            for item in values
        ])
    if model == "seedance":
        rows.append([
            InlineKeyboardButton(text=_selected("Без звука", not generate_audio), callback_data=video_callback("audio", workspace_id=workspace_id, value="off")),
            InlineKeyboardButton(text=_selected("Со звуком", generate_audio), callback_data=video_callback("audio", workspace_id=workspace_id, value="on")),
        ])
    if model == "wan":
        rows.append([
            InlineKeyboardButton(text=_selected("Первый кадр", wan_mode == "first"), callback_data=video_callback("wan_mode", workspace_id=workspace_id, value="first")),
            InlineKeyboardButton(text=_selected("Первый + последний", wan_mode == "first_last"), callback_data=video_callback("wan_mode", workspace_id=workspace_id, value="first_last")),
        ])
    if model in {"grok15", "seedance", "wan"}:
        rows.append([
            InlineKeyboardButton(text=f"Длительность · {duration} сек", callback_data=video_callback("duration_input", workspace_id=workspace_id)),
            InlineKeyboardButton(text="Изменить промт", callback_data=video_callback("change_prompt", workspace_id=workspace_id)),
        ])
        if model == "wan" and wan_mode == "first_last":
            rows.append([InlineKeyboardButton(
                text="Последний кадр · загружен" if has_last_frame else "Добавить последний кадр",
                callback_data=video_callback("last_frame", workspace_id=workspace_id),
            )])
        rows.append([InlineKeyboardButton(text="Стандартный шаблон", callback_data=video_callback("templates", workspace_id=workspace_id))])
    else:
        rows.append([InlineKeyboardButton(text="Изменить промт", callback_data=video_callback("change_prompt", workspace_id=workspace_id))])
    rows.extend([
        [InlineKeyboardButton(text="Проверить и запустить", callback_data=video_callback("review", workspace_id=workspace_id))],
        [
            InlineKeyboardButton(text="Изменить модель", callback_data=video_callback("models", workspace_id=workspace_id)),
            InlineKeyboardButton(text="Изменить фото", callback_data=video_callback("change_photo", workspace_id=workspace_id)),
        ],
        [InlineKeyboardButton(text="Отмена", callback_data=video_callback("cancel", workspace_id=workspace_id))],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_video_quality_keyboard(*, workspace_id: int, resolution: str) -> InlineKeyboardMarkup:
    return build_video_settings_keyboard(
        workspace_id=workspace_id,
        model="grok",
        resolution=resolution,
        duration=_GROK_PRICING_DURATION_SECONDS,
        generate_audio=False,
    )


def build_video_review_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Запустить видео", callback_data=video_callback("submit", workspace_id=workspace_id))],
        [
            InlineKeyboardButton(text="Изменить параметры", callback_data=video_callback("settings", workspace_id=workspace_id)),
            InlineKeyboardButton(text="Изменить модель", callback_data=video_callback("models", workspace_id=workspace_id)),
        ],
        [InlineKeyboardButton(text="Отмена", callback_data=video_callback("cancel", workspace_id=workspace_id))],
    ])


def build_video_template_keyboard(*, workspace_id: int, has_template: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Сохранить текущие стандартом", callback_data=video_callback("template_save", workspace_id=workspace_id))]]
    if has_template:
        rows.append([InlineKeyboardButton(text="Применить стандартный", callback_data=video_callback("template_apply", workspace_id=workspace_id))])
    rows.append([InlineKeyboardButton(text="К параметрам", callback_data=video_callback("settings", workspace_id=workspace_id))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _model_text(*, model: str) -> str:
    return (
        "<b>Мяу · Оживить · модель</b>\n\n"
        "Выберите движок видео. После выбора бот применит сохранённый стандартный "
        "шаблон этой модели, если он уже есть.\n\n"
        "• <b>Grok v1</b> — самый дешёвый вариант.\n"
        "• <b>Grok 1.5</b> — более качественное движение и длительность до 15 секунд.\n"
        "• <b>Seedance</b> — разрешение, длительность и звук.\n"
        "• <b>Wan 2.7</b> — первый кадр либо первый и последний кадры.\n\n"
        f"Текущая модель: <b>{escape(_MODEL_NAMES[model])}</b>."
    )


def _money_change_lines(change: Mapping[str, object] | None) -> list[str]:
    if not change:
        return []
    old_usd = Decimal(str(change.get("old_usd") or "0"))
    new_usd = Decimal(str(change.get("new_usd") or "0"))
    old_rub = Decimal(str(change.get("old_rub") or "0"))
    new_rub = Decimal(str(change.get("new_rub") or "0"))
    delta_usd = new_usd - old_usd
    delta_rub = new_rub - old_rub
    reason = escape(str(change.get("reason") or "Изменение параметров"))
    if delta_usd == 0 and delta_rub == 0:
        delta_line = "Разница: <b>цена не изменилась</b>"
    else:
        sign = "+" if delta_usd > 0 else "−"
        delta_line = (
            f"Разница: <b>{sign}{legacy._format_usd(abs(delta_usd))}</b> · "
            f"<b>{sign}{legacy._format_rub(abs(delta_rub))}</b>"
        )
    return [
        "",
        "<b>Предварительный анализ стоимости</b>",
        f"Было: <b>{legacy._format_usd(old_usd)}</b> · <b>{legacy._format_rub(old_rub)}</b>",
        f"Стало: <b>{legacy._format_usd(new_usd)}</b> · <b>{legacy._format_rub(new_rub)}</b>",
        delta_line,
        f"Причина: {reason}.",
    ]


def _settings_text(
    *,
    model: str,
    resolution: str,
    duration: int,
    generate_audio: bool,
    wan_mode: str = "first",
    has_last_frame: bool = False,
    estimated_usd: Decimal | None = None,
    estimated_rub: Decimal | None = None,
    cost_change: Mapping[str, object] | None = None,
) -> str:
    lines = [
        "<b>Мяу · Оживить · параметры</b>",
        "",
        f"Модель: <b>{escape(_MODEL_NAMES[model])}</b>",
        f"Разрешение: <b>{escape(resolution)}</b>",
        "Длительность: <b>автоматически</b>" if model == "grok" else f"Длительность: <b>{duration} сек</b>",
    ]
    if model == "seedance":
        lines.append(f"Звук: <b>{'включён' if generate_audio else 'выключен'}</b>")
    if model == "wan":
        lines.append(f"Режим кадров: <b>{_wan_mode_name(wan_mode)}</b>")
        if wan_mode == "first_last":
            lines.append(f"Последний кадр: <b>{'загружен' if has_last_frame else 'не загружен'}</b>")
    lines.extend(["Watermark: <b>выключен</b>", "NSFW checker Kie: <b>выключен</b>"])
    if model == "seedance":
        lines.append("Fixed lens: <b>выключен</b>")
    if estimated_usd is not None and estimated_rub is not None:
        lines.extend(["", f"Текущая расчётная стоимость: <b>{legacy._format_usd(estimated_usd)}</b> · <b>{legacy._format_rub(estimated_rub)}</b>"])
    lines.extend(_money_change_lines(cost_change))
    return "\n".join(lines)


def _review_text(
    *, prompt: str, model: str, resolution: str, duration: int,
    generate_audio: bool, wan_mode: str,
    estimated_usd: Decimal, estimated_rub: Decimal,
) -> str:
    settings = [
        "<b>Проверьте видео</b>", "",
        f"Модель: <b>{escape(_MODEL_NAMES[model])}</b>",
        f"Разрешение: <b>{escape(resolution)}</b>",
        "Длительность: <b>автоматически</b>" if model == "grok" else f"Длительность: <b>{duration} сек</b>",
    ]
    if model == "seedance":
        settings.append(f"Звук: <b>{'включён' if generate_audio else 'выключен'}</b>")
    if model == "wan":
        settings.append(f"Кадры: <b>{_wan_mode_name(wan_mode)}</b>")
    settings.extend([
        "Watermark: <b>выключен</b>",
        "NSFW checker Kie: <b>выключен</b>",
        f"Расчётная стоимость: <b>{legacy._format_usd(estimated_usd)}</b> · <b>{legacy._format_rub(estimated_rub)}</b>",
        "", f"<b>Движение и сцена</b>\n{escape(legacy._truncate(prompt, 3500))}", "",
        "После запуска задача попадёт в очередь. Повторное нажатие в этой сессии не создаст вторую платную генерацию.",
    ])
    return "\n".join(settings)


async def handle_auf_video_entry(
    callback: CallbackQuery, callback_data: AufCallback, state: FSMContext,
    access_policy: AccessPolicy, kie_settings: KieSettings,
) -> None:
    if not access_policy.allows_user(callback.from_user):
        await callback.answer("Оживление доступно только владельцу бота.", show_alert=True)
        return
    if not kie_settings.enabled:
        await callback.answer("Kie.ai выключен на сервере.", show_alert=True)
        return
    workspace_id = callback_data.workspace_id
    await state.clear()
    await state.update_data(
        auf_video_session_id=uuid4().hex,
        auf_video_workspace_id=workspace_id,
        auf_video_reference=None,
        auf_video_last_reference=None,
        auf_video_reference_target="first",
        auf_video_text_target="prompt",
        auf_video_prompt="",
        auf_video_model="grok",
        auf_video_resolution="480p",
        auf_video_duration=_GROK_PRICING_DURATION_SECONDS,
        auf_video_generate_audio=False,
        auf_video_wan_mode="first",
        auf_video_cost_change=None,
    )
    await state.set_state(AufVideoForm.choosing_reference)
    await legacy._edit_or_answer(
        callback,
        text=(
            "<b>Мяу · Оживить</b>\n\n"
            "Выберите первый кадр видео из базы или отправьте JPG, PNG либо WEBP до 10 МБ. "
            "Для Wan 2.7 последний кадр можно добавить позже в настройках."
        ),
        reply_markup=legacy.build_video_source_keyboard(workspace_id=workspace_id),
    )


async def handle_auf_video_reference_message(
    message: Message, state: FSMContext, access_policy: AccessPolicy,
    kie_settings: KieSettings,
) -> None:
    data = await state.get_data()
    if str(data.get("auf_video_reference_target") or "first") != "last":
        await legacy.handle_auf_video_reference_message(message, state, access_policy, kie_settings)
        return
    if not access_policy.allows_user(message.from_user):
        await state.clear()
        return
    if not kie_settings.enabled:
        await state.clear()
        await message.answer("Kie.ai выключен на сервере.")
        return
    reference = legacy._reference_from_message(message)
    if isinstance(reference, str):
        await message.answer(reference)
        return
    if reference is None:
        await message.answer("Отправьте фото или документ JPG, PNG либо WEBP.")
        return
    workspace_id = legacy._optional_int(data.get("auf_video_workspace_id")) or 0
    old_estimate = _estimate_from_data(data, kie_settings=kie_settings)
    await state.update_data(auf_video_last_reference=reference.to_payload(), auf_video_reference_target="first")
    new_data = await state.get_data()
    await _store_cost_change(
        state,
        old_estimate=old_estimate,
        new_estimate=_estimate_from_data(new_data, kie_settings=kie_settings),
        reason="добавление последнего кадра",
    )
    await state.set_state(AufVideoForm.choosing_settings)
    await _answer_settings(message, state=state, workspace_id=workspace_id, kie_settings=kie_settings)


async def handle_auf_video_prompt(
    message: Message, state: FSMContext, access_policy: AccessPolicy,
    kie_settings: KieSettings,
) -> None:
    if not access_policy.allows_user(message.from_user):
        await state.clear()
        return
    if not kie_settings.enabled:
        await state.clear()
        await message.answer("Kie.ai выключен на сервере.")
        return
    data = await state.get_data()
    target = str(data.get("auf_video_text_target") or "prompt")
    workspace_id = legacy._optional_int(data.get("auf_video_workspace_id")) or 0
    if target == "duration":
        duration = _parse_duration(message.text or "")
        model = _validated_model(data)
        if model not in {"grok15", "seedance", "wan"}:
            await message.answer("У этой модели длительность задаётся автоматически.")
            return
        if duration is None:
            await message.answer(f"Отправьте целое число от {_MIN_VIDEO_DURATION_SECONDS} до {_MAX_VIDEO_DURATION_SECONDS}. Например: 8")
            return
        old_estimate = _estimate_from_data(data, kie_settings=kie_settings)
        old_duration = _validated_duration(data, model=model)
        await state.update_data(auf_video_duration=duration, auf_video_text_target="prompt")
        new_data = await state.get_data()
        await _store_cost_change(
            state,
            old_estimate=old_estimate,
            new_estimate=_estimate_from_data(new_data, kie_settings=kie_settings),
            reason=f"длительность {old_duration} → {duration} сек",
        )
        await state.set_state(AufVideoForm.choosing_settings)
        await _answer_settings(message, state=state, workspace_id=workspace_id, kie_settings=kie_settings)
        return

    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer("Описание движения не может быть пустым.")
        return
    if len(prompt) > _MAX_PROMPT_LENGTH:
        await message.answer(f"Описание слишком длинное. Максимум {_MAX_PROMPT_LENGTH} символов.")
        return
    if legacy._reference_from_data(data.get("auf_video_reference")) is None:
        await state.clear()
        await message.answer("Сессия устарела: первый кадр не найден.")
        return
    had_prompt = bool(str(data.get("auf_video_prompt") or "").strip())
    await state.update_data(auf_video_prompt=prompt, auf_video_text_target="prompt")
    await state.set_state(AufVideoForm.choosing_settings)
    if had_prompt:
        await _answer_settings(message, state=state, workspace_id=workspace_id, kie_settings=kie_settings)
    else:
        model = _validated_model(data)
        await message.answer(_model_text(model=model), reply_markup=build_video_model_keyboard(workspace_id=workspace_id, model=model))


async def handle_auf_video_action(
    callback: CallbackQuery, callback_data: AufVideoCallback, state: FSMContext,
    access_policy: AccessPolicy, kie_settings: KieSettings, database: Database,
    ai_usage_service: AIUsageService, ai_task_queue_service: AITaskQueueService,
) -> None:
    action = callback_data.action
    workspace_id = callback_data.workspace_id
    custom_actions = {
        "model", "models", "resolution", "audio", "duration_input", "wan_mode",
        "last_frame", "templates", "template_save", "template_apply", "change_prompt",
        "settings", "review", "submit",
    }
    if action not in custom_actions:
        if action in {"change_photo", "sources", "upload", "database", "select_reference"}:
            await state.update_data(auf_video_reference_target="first")
        await legacy.handle_auf_video_action(
            callback, callback_data, state, access_policy, kie_settings, database,
            ai_usage_service, ai_task_queue_service,
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
        model = callback_data.value
        if model not in _MODEL_CODES:
            await callback.answer("Неизвестная модель видео.", show_alert=True)
            return
        data = await state.get_data()
        old_model = _validated_model(data)
        old_estimate = _estimate_from_data(data, kie_settings=kie_settings)
        template = await _load_template(database, workspace_id=workspace_id, model=model)
        await _apply_model_defaults(state, model=model, template=template)
        new_data = await state.get_data()
        reason = f"модель {_MODEL_NAMES[old_model]} → {_MODEL_NAMES[model]}"
        if template is not None:
            reason += " и применение стандартного шаблона"
        await _store_cost_change(state, old_estimate=old_estimate, new_estimate=_estimate_from_data(new_data, kie_settings=kie_settings), reason=reason)
        await _show_settings(callback, state=state, workspace_id=workspace_id, kie_settings=kie_settings)
        return
    if action == "models":
        await _show_models(callback, state=state, workspace_id=workspace_id)
        return
    if action == "resolution":
        data = await state.get_data()
        model = _validated_model(data)
        resolution = callback_data.value
        if resolution not in _allowed_resolutions(model):
            await callback.answer("Это разрешение не поддерживается моделью.", show_alert=True)
            return
        old_resolution = _validated_resolution(data, model=model)
        old_estimate = _estimate_from_data(data, kie_settings=kie_settings)
        await state.update_data(auf_video_resolution=resolution)
        new_data = await state.get_data()
        await _store_cost_change(state, old_estimate=old_estimate, new_estimate=_estimate_from_data(new_data, kie_settings=kie_settings), reason=f"разрешение {old_resolution} → {resolution}")
        await _show_settings(callback, state=state, workspace_id=workspace_id, kie_settings=kie_settings)
        return
    if action == "audio":
        data = await state.get_data()
        if _validated_model(data) != "seedance":
            await callback.answer("Звук доступен только Seedance.", show_alert=True)
            return
        old_audio = _validated_audio(data, model="seedance")
        new_audio = callback_data.value == "on"
        old_estimate = _estimate_from_data(data, kie_settings=kie_settings)
        await state.update_data(auf_video_generate_audio=new_audio)
        new_data = await state.get_data()
        reason = "включение генерации звука" if new_audio and not old_audio else "выключение генерации звука"
        await _store_cost_change(state, old_estimate=old_estimate, new_estimate=_estimate_from_data(new_data, kie_settings=kie_settings), reason=reason)
        await _show_settings(callback, state=state, workspace_id=workspace_id, kie_settings=kie_settings)
        return
    if action == "duration_input":
        data = await state.get_data()
        if _validated_model(data) not in {"grok15", "seedance", "wan"}:
            await callback.answer("Длительность этой модели задаётся автоматически.", show_alert=True)
            return
        await state.update_data(auf_video_text_target="duration")
        await state.set_state(AufVideoForm.waiting_prompt)
        await legacy._edit_or_answer(
            callback,
            text=(f"<b>Введите длительность</b>\n\nОтправьте целое число от {_MIN_VIDEO_DURATION_SECONDS} до {_MAX_VIDEO_DURATION_SECONDS} секунд. После ввода бот сразу пересчитает стоимость."),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="К параметрам", callback_data=video_callback("settings", workspace_id=workspace_id))]]),
        )
        return
    if action == "wan_mode":
        data = await state.get_data()
        if _validated_model(data) != "wan" or callback_data.value not in _WAN_MODES:
            await callback.answer("Неизвестный режим Wan 2.7.", show_alert=True)
            return
        old_mode = _validated_wan_mode(data)
        old_estimate = _estimate_from_data(data, kie_settings=kie_settings)
        await state.update_data(auf_video_wan_mode=callback_data.value)
        new_data = await state.get_data()
        await _store_cost_change(state, old_estimate=old_estimate, new_estimate=_estimate_from_data(new_data, kie_settings=kie_settings), reason=f"режим кадров {_wan_mode_name(old_mode)} → {_wan_mode_name(callback_data.value)}")
        await _show_settings(callback, state=state, workspace_id=workspace_id, kie_settings=kie_settings)
        return
    if action == "last_frame":
        data = await state.get_data()
        if _validated_model(data) != "wan" or _validated_wan_mode(data) != "first_last":
            await callback.answer("Сначала выберите режим первого и последнего кадра.", show_alert=True)
            return
        await state.update_data(auf_video_reference_target="last")
        await state.set_state(AufVideoForm.waiting_reference)
        await legacy._edit_or_answer(
            callback,
            text="<b>Отправьте последний кадр Wan 2.7</b>\n\nПринимаются Telegram-фото и документы JPG, PNG или WEBP до 10 МБ.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="К параметрам", callback_data=video_callback("settings", workspace_id=workspace_id)),
                InlineKeyboardButton(text="Отмена", callback_data=video_callback("cancel", workspace_id=workspace_id)),
            ]]),
        )
        return
    if action == "change_prompt":
        await state.update_data(auf_video_text_target="prompt")
        await state.set_state(AufVideoForm.waiting_prompt)
        await legacy._edit_or_answer(
            callback,
            text=f"<b>Измените промт движения</b>\n\nОтправьте новый текст до {_MAX_PROMPT_LENGTH} символов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="К параметрам", callback_data=video_callback("settings", workspace_id=workspace_id))]]),
        )
        return
    if action == "templates":
        await _show_templates(callback, state=state, workspace_id=workspace_id, database=database)
        return
    if action == "template_save":
        data = await state.get_data()
        model = _validated_model(data)
        if model not in {"seedance", "wan"}:
            await callback.answer("Шаблон для Grok не требуется.", show_alert=True)
            return
        await _save_template(
            database, workspace_id=workspace_id, model=model,
            resolution=_validated_resolution(data, model=model),
            duration=_validated_duration(data, model=model),
            generate_audio=_validated_audio(data, model=model),
            wan_mode=_validated_wan_mode(data), user_id=callback.from_user.id,
        )
        await callback.answer("Текущие параметры сохранены стандартным шаблоном.")
        await _show_templates(callback, state=state, workspace_id=workspace_id, database=database)
        return
    if action == "template_apply":
        data = await state.get_data()
        model = _validated_model(data)
        template = await _load_template(database, workspace_id=workspace_id, model=model)
        if template is None:
            await callback.answer("Стандартный шаблон ещё не сохранён.", show_alert=True)
            return
        old_estimate = _estimate_from_data(data, kie_settings=kie_settings)
        await _apply_template(state, model=model, template=template)
        new_data = await state.get_data()
        await _store_cost_change(state, old_estimate=old_estimate, new_estimate=_estimate_from_data(new_data, kie_settings=kie_settings), reason="применение стандартного шаблона")
        await _show_settings(callback, state=state, workspace_id=workspace_id, kie_settings=kie_settings)
        return
    if action == "settings":
        await state.update_data(auf_video_reference_target="first", auf_video_text_target="prompt")
        await _show_settings(callback, state=state, workspace_id=workspace_id, kie_settings=kie_settings)
        return
    if action == "review":
        await _show_review(callback, state=state, workspace_id=workspace_id, kie_settings=kie_settings)
        return
    await _submit_video(
        callback, state=state, workspace_id=workspace_id, kie_settings=kie_settings,
        ai_usage_service=ai_usage_service, ai_task_queue_service=ai_task_queue_service,
    )


async def _show_models(callback: CallbackQuery, *, state: FSMContext, workspace_id: int) -> None:
    model = _validated_model(await state.get_data())
    await state.set_state(AufVideoForm.choosing_settings)
    await legacy._edit_or_answer(callback, text=_model_text(model=model), reply_markup=build_video_model_keyboard(workspace_id=workspace_id, model=model))


async def _show_settings(
    callback: CallbackQuery, *, state: FSMContext, workspace_id: int,
    kie_settings: KieSettings,
) -> None:
    data = await state.get_data()
    model = _validated_model(data)
    resolution = _validated_resolution(data, model=model)
    duration = _validated_duration(data, model=model)
    generate_audio = _validated_audio(data, model=model)
    wan_mode = _validated_wan_mode(data)
    has_last_frame = legacy._reference_from_data(data.get("auf_video_last_reference")) is not None
    estimated_usd, estimated_rub = _estimate_from_data(data, kie_settings=kie_settings)
    cost_change = data.get("auf_video_cost_change")
    await state.set_state(AufVideoForm.choosing_settings)
    await legacy._edit_or_answer(
        callback,
        text=_settings_text(
            model=model, resolution=resolution, duration=duration,
            generate_audio=generate_audio, wan_mode=wan_mode,
            has_last_frame=has_last_frame, estimated_usd=estimated_usd,
            estimated_rub=estimated_rub,
            cost_change=cost_change if isinstance(cost_change, Mapping) else None,
        ),
        reply_markup=build_video_settings_keyboard(
            workspace_id=workspace_id, model=model, resolution=resolution,
            duration=duration, generate_audio=generate_audio,
            wan_mode=wan_mode, has_last_frame=has_last_frame,
        ),
    )


async def _answer_settings(
    message: Message, *, state: FSMContext, workspace_id: int,
    kie_settings: KieSettings,
) -> None:
    data = await state.get_data()
    model = _validated_model(data)
    resolution = _validated_resolution(data, model=model)
    duration = _validated_duration(data, model=model)
    generate_audio = _validated_audio(data, model=model)
    wan_mode = _validated_wan_mode(data)
    has_last_frame = legacy._reference_from_data(data.get("auf_video_last_reference")) is not None
    estimated_usd, estimated_rub = _estimate_from_data(data, kie_settings=kie_settings)
    cost_change = data.get("auf_video_cost_change")
    await message.answer(
        _settings_text(
            model=model, resolution=resolution, duration=duration,
            generate_audio=generate_audio, wan_mode=wan_mode,
            has_last_frame=has_last_frame, estimated_usd=estimated_usd,
            estimated_rub=estimated_rub,
            cost_change=cost_change if isinstance(cost_change, Mapping) else None,
        ),
        reply_markup=build_video_settings_keyboard(
            workspace_id=workspace_id, model=model, resolution=resolution,
            duration=duration, generate_audio=generate_audio,
            wan_mode=wan_mode, has_last_frame=has_last_frame,
        ),
    )


async def _show_templates(
    callback: CallbackQuery, *, state: FSMContext, workspace_id: int,
    database: Database,
) -> None:
    data = await state.get_data()
    model = _validated_model(data)
    if model not in {"seedance", "wan"}:
        await callback.answer("Шаблон для Grok не требуется.", show_alert=True)
        return
    template = await _load_template(database, workspace_id=workspace_id, model=model)
    lines = ["<b>Стандартный шаблон видео</b>", "", f"Модель: <b>{escape(_MODEL_NAMES[model])}</b>"]
    if template is None:
        lines.extend(["Шаблон: <b>ещё не сохранён</b>", "Сохраните текущую конфигурацию, и она будет применяться при выборе модели."])
    else:
        lines.extend([
            f"Разрешение: <b>{escape(str(template['resolution']))}</b>",
            f"Длительность: <b>{int(template['duration_seconds'])} сек</b>",
        ])
        if model == "seedance":
            lines.append(f"Звук: <b>{'включён' if bool(template['generate_audio']) else 'выключен'}</b>")
        else:
            lines.append(f"Кадры: <b>{_wan_mode_name(str(template['wan_mode']))}</b>")
    await legacy._edit_or_answer(
        callback, text="\n".join(lines),
        reply_markup=build_video_template_keyboard(workspace_id=workspace_id, has_template=template is not None),
    )


async def _show_review(
    callback: CallbackQuery, *, state: FSMContext, workspace_id: int,
    kie_settings: KieSettings,
) -> None:
    data = await state.get_data()
    reference = legacy._reference_from_data(data.get("auf_video_reference"))
    last_reference = legacy._reference_from_data(data.get("auf_video_last_reference"))
    prompt = str(data.get("auf_video_prompt") or "").strip()
    if reference is None or not prompt:
        await callback.answer("Сессия устарела: нужны первый кадр и промт.", show_alert=True)
        return
    model = _validated_model(data)
    wan_mode = _validated_wan_mode(data)
    if model == "wan" and wan_mode == "first_last" and last_reference is None:
        await callback.answer("Для этого режима загрузите последний кадр.", show_alert=True)
        return
    resolution = _validated_resolution(data, model=model)
    duration = _validated_duration(data, model=model)
    generate_audio = _validated_audio(data, model=model)
    request = _build_request(
        reference=reference, last_reference=last_reference, prompt=prompt,
        model=model, resolution=resolution, duration=duration,
        generate_audio=generate_audio, wan_mode=wan_mode,
    )
    estimated_usd = kie_settings.pricing.estimate_usd(request)
    estimated_rub = kie_settings.pricing.estimate_rub(request, usd_to_rub=kie_settings.usd_to_rub)
    await state.set_state(AufVideoForm.reviewing)
    await legacy._edit_or_answer(
        callback,
        text=_review_text(
            prompt=prompt, model=model, resolution=resolution, duration=duration,
            generate_audio=generate_audio, wan_mode=wan_mode,
            estimated_usd=estimated_usd, estimated_rub=estimated_rub,
        ),
        reply_markup=build_video_review_keyboard(workspace_id=workspace_id),
    )


async def _submit_video(
    callback: CallbackQuery, *, state: FSMContext, workspace_id: int,
    kie_settings: KieSettings, ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    data = await state.get_data()
    reference = legacy._reference_from_data(data.get("auf_video_reference"))
    last_reference = legacy._reference_from_data(data.get("auf_video_last_reference"))
    prompt = str(data.get("auf_video_prompt") or "").strip()
    session_id = str(data.get("auf_video_session_id") or "").strip()
    if reference is None or not prompt or not session_id:
        await state.clear()
        await callback.answer("Сессия Оживить устарела.", show_alert=True)
        return
    model = _validated_model(data)
    wan_mode = _validated_wan_mode(data)
    if model == "wan" and wan_mode == "first_last" and last_reference is None:
        await callback.answer("Для этого режима загрузите последний кадр.", show_alert=True)
        return
    alias = _MODEL_ALIASES[model]
    provider_model = kie_settings.models.provider_model(alias, input_mode=KieInputMode.PHOTO_TEXT)
    if provider_model != _MODEL_EXPECTED_IDS[model]:
        await callback.answer(f"Неверный model id {_MODEL_NAMES[model]}: {provider_model}", show_alert=True)
        return
    resolution = _validated_resolution(data, model=model)
    duration = _validated_duration(data, model=model)
    generate_audio = _validated_audio(data, model=model)
    request = _build_request(
        reference=reference, last_reference=last_reference, prompt=prompt,
        model=model, resolution=resolution, duration=duration,
        generate_audio=generate_audio, wan_mode=wan_mode,
    )
    estimated_usd = kie_settings.pricing.estimate_usd(request)
    estimated_rub = kie_settings.pricing.estimate_rub(request, usd_to_rub=kie_settings.usd_to_rub)
    budget_status = await ai_usage_service.status()
    block_reason = legacy._budget_block_reason(budget_status, estimated_cost_rub=estimated_rub)
    if block_reason is not None:
        await callback.answer(block_reason, show_alert=True)
        return
    chat_id = callback.message.chat.id if isinstance(callback.message, Message) else None
    result = await ai_task_queue_service.enqueue(AITaskRequest(
        scope=AIBudgetScope.VISION,
        task_type=KIE_GENERATION_TASK_TYPE,
        payload={
            "request": request.to_task_payload(), "chat_id": chat_id,
            "user_id": callback.from_user.id, "workspace_id": workspace_id,
            "delivery_kind": "video",
        },
        priority=35,
        dedupe_key=f"kie:video:{model}:{session_id}",
        max_attempts=3,
        created_by=callback.from_user.id,
        estimated_cost_rub=estimated_rub,
    ))
    await state.clear()
    created_line = "Задача поставлена в очередь." if result.created else "Эта задача уже была поставлена в очередь."
    details = [
        f"<b>Мяу · {escape(_MODEL_NAMES[model])}</b>", "", created_line,
        "Watermark и NSFW checker Kie выключены.", "",
        f"Разрешение: <b>{escape(resolution)}</b>",
    ]
    if model != "grok":
        details.append(f"Длительность: <b>{duration} сек</b>")
    if model == "seedance":
        details.append(f"Звук: <b>{'включён' if generate_audio else 'выключен'}</b>")
    if model == "wan":
        details.append(f"Кадры: <b>{_wan_mode_name(wan_mode)}</b>")
    details.extend([
        f"Расчётная стоимость: <b>{legacy._format_usd(estimated_usd)}</b> · <b>{legacy._format_rub(estimated_rub)}</b>",
        f"Задача: <code>{result.task.id}</code>",
    ])
    await legacy._edit_or_answer(callback, text="\n".join(details), reply_markup=build_auf_root_keyboard(workspace_id=workspace_id, enabled=True))


def _build_request(
    *, reference: KieReferenceImage, prompt: str, resolution: str,
    model: str = "grok", duration: int | None = None,
    generate_audio: bool = False,
    last_reference: KieReferenceImage | None = None,
    wan_mode: str = "first",
) -> KieGenerationRequest:
    if model == "grok15":
        return KieGenerationRequest(
            model=KieModelAlias.GROK_IMAGINE_VIDEO_15,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt=prompt,
            references=(reference,),
            content_mode=KieContentMode.MATURE,
            aspect_ratio="auto",
            resolution=resolution,
            duration_seconds=duration or 8,
            output_format="mp4",
            extra_input={"nsfw_checker": False},
        )
    if model == "seedance":
        return KieGenerationRequest(
            model=KieModelAlias.SEEDANCE_15_PRO_VIDEO,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt=prompt,
            references=(reference,),
            content_mode=KieContentMode.MATURE,
            aspect_ratio="1:1",
            resolution=resolution,
            duration_seconds=duration or _DEFAULT_VIDEO_DURATION_SECONDS,
            output_format="mp4",
            extra_input={"fixed_lens": False, "generate_audio": generate_audio, "nsfw_checker": False},
        )
    if model == "wan":
        references = (reference, last_reference) if wan_mode == "first_last" and last_reference is not None else (reference,)
        return KieGenerationRequest(
            model=KieModelAlias.WAN_26_IMAGE_TO_VIDEO,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt=prompt,
            references=references,
            content_mode=KieContentMode.MATURE,
            resolution=resolution,
            duration_seconds=duration or _DEFAULT_VIDEO_DURATION_SECONDS,
            output_format="mp4",
            extra_input={
                "wan_mode": wan_mode,
                "prompt_extend": True,
                "watermark": False,
                "nsfw_checker": False,
            },
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


def _estimate_from_data(data: Mapping[str, object], *, kie_settings: KieSettings) -> tuple[Decimal, Decimal]:
    reference = legacy._reference_from_data(data.get("auf_video_reference"))
    if reference is None:
        reference = KieReferenceImage(telegram_file_id="estimate", source="upload", mime_type="image/jpeg", file_name="estimate.jpg")
    model = _validated_model(data)
    request = _build_request(
        reference=reference,
        last_reference=legacy._reference_from_data(data.get("auf_video_last_reference")),
        prompt=str(data.get("auf_video_prompt") or "motion") or "motion",
        model=model,
        resolution=_validated_resolution(data, model=model),
        duration=_validated_duration(data, model=model),
        generate_audio=_validated_audio(data, model=model),
        wan_mode=_validated_wan_mode(data),
    )
    usd = kie_settings.pricing.estimate_usd(request)
    rub = kie_settings.pricing.estimate_rub(request, usd_to_rub=kie_settings.usd_to_rub)
    return usd, rub


async def _store_cost_change(
    state: FSMContext, *, old_estimate: tuple[Decimal, Decimal],
    new_estimate: tuple[Decimal, Decimal], reason: str,
) -> None:
    await state.update_data(auf_video_cost_change={
        "old_usd": str(old_estimate[0]), "old_rub": str(old_estimate[1]),
        "new_usd": str(new_estimate[0]), "new_rub": str(new_estimate[1]),
        "reason": reason,
    })


async def _apply_model_defaults(
    state: FSMContext, *, model: str,
    template: Mapping[str, object] | None = None,
) -> None:
    if model == "grok15":
        await state.update_data(auf_video_model=model, auf_video_resolution="480p", auf_video_duration=8, auf_video_generate_audio=False, auf_video_wan_mode="first")
    elif model == "seedance":
        await state.update_data(auf_video_model=model, auf_video_resolution="720p", auf_video_duration=5, auf_video_generate_audio=False, auf_video_wan_mode="first")
    elif model == "wan":
        await state.update_data(auf_video_model=model, auf_video_resolution="720p", auf_video_duration=5, auf_video_generate_audio=False, auf_video_wan_mode="first")
    else:
        await state.update_data(auf_video_model="grok", auf_video_resolution="480p", auf_video_duration=6, auf_video_generate_audio=False, auf_video_wan_mode="first")
    if template is not None and model in {"seedance", "wan"}:
        await _apply_template(state, model=model, template=template)


async def _apply_template(state: FSMContext, *, model: str, template: Mapping[str, object]) -> None:
    resolution = str(template.get("resolution") or "720p")
    if resolution not in _allowed_resolutions(model):
        resolution = "720p"
    duration = legacy._optional_int(template.get("duration_seconds"))
    if duration is None or not 2 <= duration <= 15:
        duration = 5
    wan_mode = str(template.get("wan_mode") or "first")
    await state.update_data(
        auf_video_model=model,
        auf_video_resolution=resolution,
        auf_video_duration=duration,
        auf_video_generate_audio=bool(template.get("generate_audio")) if model == "seedance" else False,
        auf_video_wan_mode=wan_mode if model == "wan" and wan_mode in _WAN_MODES else "first",
    )


async def _load_template(database: Database, *, workspace_id: int, model: str) -> Mapping[str, object] | None:
    if model not in {"seedance", "wan"}:
        return None
    async with database.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT resolution, duration_seconds, generate_audio, wan_mode
            FROM workspace_video_templates
            WHERE workspace_id = $1 AND model = $2
            """,
            int(workspace_id), model,
        )
    return row


async def _save_template(
    database: Database, *, workspace_id: int, model: str,
    resolution: str, duration: int, generate_audio: bool,
    wan_mode: str, user_id: int,
) -> None:
    async with database.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO workspace_video_templates (
                workspace_id, model, resolution, duration_seconds,
                generate_audio, wan_mode, updated_by_user_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (workspace_id, model) DO UPDATE
            SET resolution = EXCLUDED.resolution,
                duration_seconds = EXCLUDED.duration_seconds,
                generate_audio = EXCLUDED.generate_audio,
                wan_mode = EXCLUDED.wan_mode,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = NOW()
            """,
            int(workspace_id), model, resolution, int(duration),
            bool(generate_audio), wan_mode, int(user_id),
        )


def _validated_model(data: Mapping[str, object] | object) -> str:
    model = str(data.get("auf_video_model") or "grok") if isinstance(data, Mapping) else "grok"
    return model if model in _MODEL_CODES else "grok"


def _validated_resolution(data: Mapping[str, object] | object, *, model: str | None = None) -> str:
    resolved_model = model or _validated_model(data)
    resolution = str(data.get("auf_video_resolution") or "") if isinstance(data, Mapping) else ""
    allowed = _allowed_resolutions(resolved_model)
    default = "480p" if resolved_model in {"grok", "grok15"} else "720p"
    return resolution if resolution in allowed else default


def _validated_duration(data: Mapping[str, object] | object, *, model: str) -> int:
    if model == "grok":
        return _GROK_PRICING_DURATION_SECONDS
    value = legacy._optional_int(data.get("auf_video_duration")) if isinstance(data, Mapping) else None
    return value if value is not None and 2 <= value <= 15 else _DEFAULT_VIDEO_DURATION_SECONDS


def _validated_audio(data: Mapping[str, object] | object, *, model: str) -> bool:
    return bool(model == "seedance" and isinstance(data, Mapping) and data.get("auf_video_generate_audio") is True)


def _validated_wan_mode(data: Mapping[str, object] | object) -> str:
    value = str(data.get("auf_video_wan_mode") or "first") if isinstance(data, Mapping) else "first"
    return value if value in _WAN_MODES else "first"


def _allowed_resolutions(model: str) -> tuple[str, ...]:
    if model == "seedance":
        return _SEEDANCE_RESOLUTIONS
    if model == "wan":
        return _WAN_RESOLUTIONS
    return _GROK_RESOLUTIONS


def _resolution_rows(model: str) -> tuple[tuple[str, ...], ...]:
    return (_allowed_resolutions(model),)


def _parse_duration(value: str) -> int | None:
    cleaned = value.strip().casefold().replace("секунд", "").replace("сек", "").strip()
    try:
        duration = int(cleaned)
    except ValueError:
        return None
    return duration if 2 <= duration <= 15 else None


def _wan_mode_name(mode: str) -> str:
    return "первый + последний" if mode == "first_last" else "первый кадр"


__all__ = (
    "AufVideoCallback",
    "AufVideoForm",
    "build_video_model_keyboard",
    "build_video_quality_keyboard",
    "build_video_review_keyboard",
    "build_video_settings_keyboard",
    "build_video_template_keyboard",
    "handle_auf_video_action",
    "handle_auf_video_entry",
    "handle_auf_video_prompt",
    "handle_auf_video_reference_message",
)
