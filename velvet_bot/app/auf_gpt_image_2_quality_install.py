from __future__ import annotations

from html import escape
from typing import Mapping

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from velvet_bot.domains import codex_image as codex_domain
from velvet_bot.domains.codex_image import (
    CODEX_IMAGE_EFFORTS,
    CODEX_IMAGE_MODELS,
    CODEX_IMAGE_RESOLUTIONS,
    CodexImageRequest,
    GPT_IMAGE_2_NAME,
)
from velvet_bot.presentation.telegram.auf_editing import edit_or_answer_auf_callback
from velvet_bot.presentation.telegram.routers import workspace_auf_photo as photo_router

_MAX_REFERENCES = 6
_MAX_REFERENCE_BYTES = 8 * 1024 * 1024
_INSTALLED = False


def _provider_model(resolution: str, reference_count: int) -> str:
    if resolution == "1K" and reference_count <= 3:
        return "gpt-image-2"
    return "firefly-gpt-image-2"


def install_auf_gpt_image_2_quality() -> None:
    """Install the user-selected quality and strict GPT Image 2 route contract."""
    global _INSTALLED
    if _INSTALLED:
        return

    from velvet_bot.app import auf_gpt_image_2_install as gpt

    codex_domain.MAX_CODEX_IMAGE_REFERENCES = _MAX_REFERENCES
    codex_domain.MAX_CODEX_IMAGE_REFERENCE_BYTES = _MAX_REFERENCE_BYTES
    gpt.MAX_CODEX_IMAGE_REFERENCES = _MAX_REFERENCES

    original_show_ratios = gpt._show_ratios
    original_handle_input = gpt._handle_input

    async def show_modes(callback: CallbackQuery, state: FSMContext) -> None:
        workspace_id = int(
            gpt._state_value(await state.get_data(), "auf_workspace_id") or 0
        )
        await state.set_state(photo_router.AufPhotoForm.choosing_model)
        await edit_or_answer_auf_callback(
            callback,
            text=(
                f"<b>{GPT_IMAGE_2_NAME}</b>\n\n"
                "Только текст: 0 референсов.\n"
                "Фото + текст: от 1 до 6 общих референсов.\n"
                "Один файл: до 8 МБ · JPG, PNG или WEBP.\n"
                "Каэль анализирует запрос и референсы выбранной GPT-5.6 моделью.\n"
                "Промт: до 8000 символов двумя сообщениями.\n\n"
                "1K сначала использует Codex Plus. При чистом исчерпании лимита "
                "до запуска image_gen запрос один раз уходит в Byesu. Для 1K и "
                "не более трёх референсов выбирается дешёвый gpt-image-2; при "
                "четырёх-шести референсах — firefly-gpt-image-2. Качество 2K и "
                "4K сразу использует firefly-gpt-image-2, потому что Codex не "
                "получает права притворяться нативным 4K."
            ),
            reply_markup=gpt._markup(
                [
                    gpt._button(
                        "Только текст",
                        "gpt2_mode",
                        workspace_id=workspace_id,
                        value="text",
                    )
                ],
                [
                    gpt._button(
                        "Фото + текст",
                        "gpt2_mode",
                        workspace_id=workspace_id,
                        value="photo_text",
                    )
                ],
                [
                    gpt._button(
                        "К моделям",
                        "photo_choose_model",
                        workspace_id=workspace_id,
                    )
                ],
                [gpt._button("Отмена", "cancel", workspace_id=workspace_id)],
            ),
        )

    async def show_input(
        event: Message | CallbackQuery,
        state: FSMContext,
    ) -> None:
        data = await state.get_data()
        workspace_id = int(gpt._state_value(data, "auf_workspace_id") or 0)
        mode = str(gpt._state_value(data, "auf_input_mode") or "")
        parts = gpt._prompt_parts(data)
        prompt = gpt._prompt(data)
        refs = gpt._references(data)
        await state.set_state(photo_router.AufPhotoForm.collecting_input)
        lines = [
            f"<b>{GPT_IMAGE_2_NAME} · "
            f"{'Только текст' if mode == 'text' else 'Фото + текст'}</b>",
            "",
            f"Промт: <b>{len(prompt)}/{gpt.MAX_CODEX_IMAGE_PROMPT}</b> символов.",
            f"Частей текста: <b>{len(parts)}/{gpt._MAX_PROMPT_MESSAGES}</b>.",
        ]
        if mode == "photo_text":
            lines.extend(
                [
                    f"Референсы: <b>{len(refs)}/{_MAX_REFERENCES}</b>.",
                    "Один файл: <b>до 8 МБ</b> · JPG, PNG или WEBP.",
                    "Каэль сам определит назначение каждого изображения.",
                ]
            )
        lines.extend(
            ["", "Отправьте промт, а в режиме «Фото + текст» также изображения."]
        )
        markup = gpt._input_keyboard(
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

    async def handle_input(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        mode = str(gpt._state_value(data, "auf_input_mode") or "")
        refs = gpt._references(data)
        if mode == "photo_text" and (message.photo or message.document):
            if len(refs) >= _MAX_REFERENCES:
                await message.answer(
                    "GPT Image 2 принимает не больше шести референсов."
                )
                return
            file_size = None
            if message.photo:
                file_size = message.photo[-1].file_size
            elif message.document:
                file_size = message.document.file_size
            if file_size is not None and file_size > _MAX_REFERENCE_BYTES:
                await message.answer("Один референс должен быть не больше 8 МБ.")
                return
        await original_handle_input(message, state)

    async def show_resolutions(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        workspace_id = int(
            gpt._state_value(await state.get_data(), "auf_workspace_id") or 0
        )
        await state.set_state(photo_router.AufPhotoForm.choosing_resolution)
        await edit_or_answer_auf_callback(
            callback,
            text=(
                "<b>GPT Image 2 · качество</b>\n\n"
                "1K: сначала Codex Plus; при лимите Byesu автоматически выберет "
                "gpt-image-2 для 0–3 референсов или firefly-gpt-image-2 для 4–6.\n"
                "2K и 4K: сразу Byesu firefly-gpt-image-2.\n\n"
                "Искусственный апскейл не используется."
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        gpt._button(
                            resolution,
                            "gpt2_resolution",
                            workspace_id=workspace_id,
                            value=resolution,
                        )
                        for resolution in CODEX_IMAGE_RESOLUTIONS
                    ],
                    [
                        gpt._button(
                            "К проверке",
                            "gpt2_review",
                            workspace_id=workspace_id,
                        )
                    ],
                    [gpt._button("Отмена", "cancel", workspace_id=workspace_id)],
                ]
            ),
        )

    async def show_ratios(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        resolution = str(
            gpt._state_value(data, "auf_resolution") or ""
        ).strip().upper()
        if resolution not in CODEX_IMAGE_RESOLUTIONS:
            await show_resolutions(callback, state)
            return
        await original_show_ratios(callback, state)

    def request(data: Mapping[str, object]) -> CodexImageRequest:
        resolution = str(
            gpt._state_value(data, "auf_resolution") or "1K"
        ).strip().upper()
        if resolution not in CODEX_IMAGE_RESOLUTIONS:
            resolution = "1K"
        references = gpt._references(data)
        if len(references) > _MAX_REFERENCES:
            raise ValueError("GPT Image 2 принимает не больше шести референсов.")
        return CodexImageRequest(
            prompt=gpt._prompt(data),
            references=references,
            input_mode=str(
                gpt._state_value(data, "auf_input_mode") or "text"
            ),
            aspect_ratio=str(
                gpt._state_value(data, "auf_aspect_ratio") or "9:16"
            ),
            resolution=resolution,
            analysis_model=str(
                gpt._state_value(data, "auf_analysis_model")
                or "gpt-5.6-terra"
            ),
            reasoning_effort=str(
                gpt._state_value(data, "auf_reasoning_effort") or "high"
            ),
        )

    async def show_final(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        current = request(data)
        workspace_id = int(gpt._state_value(data, "auf_workspace_id") or 0)
        model_name = dict(CODEX_IMAGE_MODELS)[current.analysis_model]
        effort_name = dict(CODEX_IMAGE_EFFORTS)[current.reasoning_effort]
        image_model = _provider_model(
            current.resolution,
            len(current.references),
        )
        if current.resolution == "1K":
            route_text = (
                "Codex Plus → при чистом лимите Byesu "
                f"<code>{image_model}</code>"
            )
        else:
            route_text = "Byesu <code>firefly-gpt-image-2</code> напрямую"
        await state.set_state(photo_router.AufPhotoForm.confirming_generation)
        await edit_or_answer_auf_callback(
            callback,
            text=(
                "<b>Проверьте перед созданием</b>\n\n"
                f"Модель: <b>{GPT_IMAGE_2_NAME}</b>\n"
                f"Анализ: <b>{escape(model_name)} · {escape(effort_name)}</b>\n"
                f"Референсы: <b>{len(current.references)}/{_MAX_REFERENCES}</b>\n"
                f"Качество: <b>{current.resolution}</b>\n"
                f"Маршрут: <b>{route_text}</b>\n"
                f"Соотношение: <b>{current.aspect_ratio}</b>\n"
                "Результатов: <b>1</b>\n"
                "Автоперегенерация после начала инструмента: <b>нет</b>\n\n"
                f"<b>Текст</b>\n"
                f"{escape(photo_router._truncate(current.prompt, 2500))}"
            ),
            reply_markup=gpt._markup(
                [
                    gpt._button(
                        "Да, создать",
                        "gpt2_generate",
                        workspace_id=workspace_id,
                    )
                ],
                [
                    gpt._button(
                        "Качество",
                        "gpt2_choose_resolution",
                        workspace_id=workspace_id,
                    ),
                    gpt._button(
                        "Пропорция",
                        "gpt2_choose_ratio",
                        workspace_id=workspace_id,
                    ),
                ],
                [
                    gpt._button(
                        "Модель анализа",
                        "gpt2_choose_analysis",
                        workspace_id=workspace_id,
                    ),
                    gpt._button(
                        "Усилие",
                        "gpt2_choose_effort",
                        workspace_id=workspace_id,
                    ),
                ],
                [
                    gpt._button(
                        "Исходные данные",
                        "gpt2_input_back",
                        workspace_id=workspace_id,
                    )
                ],
                [gpt._button("Отмена", "cancel", workspace_id=workspace_id)],
            ),
        )

    gpt._show_modes = show_modes
    gpt._show_input = show_input
    gpt._handle_input = handle_input
    gpt._show_resolutions = show_resolutions
    gpt._show_ratios = show_ratios
    gpt._request = request
    gpt._show_final = show_final
    _INSTALLED = True


__all__ = ("install_auf_gpt_image_2_quality",)
