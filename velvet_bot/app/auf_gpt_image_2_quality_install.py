from __future__ import annotations

from html import escape
from typing import Any, Mapping

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from velvet_bot.domains.codex_image import (
    CODEX_IMAGE_EFFORTS,
    CODEX_IMAGE_MODELS,
    CODEX_IMAGE_RESOLUTIONS,
    CodexImageRequest,
    GPT_IMAGE_2_NAME,
)
from velvet_bot.presentation.telegram.auf_editing import edit_or_answer_auf_callback
from velvet_bot.presentation.telegram.routers import workspace_auf_photo as photo_router

_INSTALLED = False


def install_auf_gpt_image_2_quality() -> None:
    """Restore an honest Byesu-only quality selector for GPT Image 2 fallback."""
    global _INSTALLED
    if _INSTALLED:
        return

    from velvet_bot.app import auf_gpt_image_2_install as gpt

    original_show_ratios = gpt._show_ratios

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
                "Фото + текст: от 1 до 5 общих референсов.\n"
                "Каэль анализирует запрос и референсы выбранной GPT-5.6 моделью.\n"
                "Промт: до 8000 символов двумя сообщениями.\n\n"
                "Основной маршрут: Codex Plus, нативный размер без апскейла.\n"
                "При чистом исчерпании лимита до запуска image_gen используется "
                "единственный резерв Byesu. Для него отдельно выбирается 1K, 2K "
                "или 4K. Автоматической повторной генерации после начала "
                "инструмента нет."
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
                "<b>GPT Image 2 · качество резерва Byesu</b>\n\n"
                "1K, 2K и 4K передаются в Byesu как настоящий размер запроса.\n"
                "Выбор не меняет нативное разрешение основного Codex/ImageGen "
                "маршрута и не включает искусственный апскейл."
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
            gpt._state_value(data, "auf_resolution") or "2K"
        ).strip().upper()
        if resolution not in CODEX_IMAGE_RESOLUTIONS:
            resolution = "2K"
        return CodexImageRequest(
            prompt=gpt._prompt(data),
            references=gpt._references(data),
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
        workspace_id = int(
            gpt._state_value(data, "auf_workspace_id") or 0
        )
        model_name = dict(CODEX_IMAGE_MODELS)[current.analysis_model]
        effort_name = dict(CODEX_IMAGE_EFFORTS)[current.reasoning_effort]
        await state.set_state(photo_router.AufPhotoForm.confirming_generation)
        await edit_or_answer_auf_callback(
            callback,
            text=(
                "<b>Проверьте перед созданием</b>\n\n"
                f"Модель: <b>{GPT_IMAGE_2_NAME}</b>\n"
                f"Анализ: <b>{escape(model_name)} · {escape(effort_name)}</b>\n"
                f"Референсы: <b>{len(current.references)}</b>\n"
                "Основной Codex: <b>нативный JPEG без апскейла</b>\n"
                f"Резерв Byesu: <b>{current.resolution}</b>\n"
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
                        "Качество Byesu",
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
    gpt._show_resolutions = show_resolutions
    gpt._show_ratios = show_ratios
    gpt._request = request
    gpt._show_final = show_final
    _INSTALLED = True


__all__ = ("install_auf_gpt_image_2_quality",)
