from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.presentation.telegram.routers import workspace_auf_photo as photo_router
from velvet_bot.presentation.telegram.routers.workspace_auf import (
    AufCallback,
    _callback,
    _edit_or_answer,
)


_ORIGINAL_EDIT_REFERENCES_KEYBOARD = photo_router._edit_references_keyboard


def build_edit_references_keyboard(
    workspace_id: int,
    reference_count: int,
) -> InlineKeyboardMarkup:
    """Add a non-destructive trim action to the photo-reference editor."""

    base = _ORIGINAL_EDIT_REFERENCES_KEYBOARD(workspace_id, reference_count)
    if reference_count <= 0:
        return base
    rows = [list(row) for row in base.inline_keyboard]
    rows.insert(
        1,
        [
            InlineKeyboardButton(
                text="Убрать последнее фото",
                callback_data=_callback(
                    "photo_remove_last",
                    workspace_id=workspace_id,
                ),
            )
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# The photo flow calls the module-level function at runtime, so this keeps the
# adjustment isolated instead of duplicating the entire router.
photo_router._edit_references_keyboard = build_edit_references_keyboard


async def handle_photo_remove_last(
    callback: CallbackQuery,
    callback_data: AufCallback,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    references = photo_router._references(data.get("meow_references"))
    if not references:
        await callback.answer("Фото уже отсутствуют.", show_alert=True)
        return
    remaining = references[:-1]
    await photo_router._save_references(state, remaining)
    await _edit_or_answer(
        callback,
        text=(
            "<b>Фото и референсы</b>\n\n"
            f"Последнее фото удалено. Сейчас выбрано: "
            f"<b>{len(remaining)}</b>."
        ),
        reply_markup=build_edit_references_keyboard(
            callback_data.workspace_id,
            len(remaining),
        ),
    )


__all__ = ("handle_photo_remove_last",)
