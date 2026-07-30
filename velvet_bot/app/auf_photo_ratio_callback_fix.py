from __future__ import annotations

import importlib

from aiogram.types import InlineKeyboardMarkup

from velvet_bot.presentation.telegram.routers import workspace_meow_photo as photo_router

_INSTALLED = False
_RATIO_SEPARATOR_REPLACEMENT = "x"


def encode_photo_ratio_callback_value(ratio: str) -> str:
    """Encode a ratio so aiogram's ':' callback separator is never embedded in a field."""

    return str(ratio).replace(":", _RATIO_SEPARATOR_REPLACEMENT)


def decode_photo_ratio_callback_value(value: str) -> str:
    """Restore the provider-facing ratio from its callback-safe representation."""

    normalized = str(value)
    if normalized == "auto":
        return normalized
    return normalized.replace(_RATIO_SEPARATOR_REPLACEMENT, ":")


def build_safe_photo_ratio_keyboard(workspace_id: int, model) -> InlineKeyboardMarkup:
    ratios = model.supported_aspect_ratios
    rows = []
    for index in range(0, len(ratios), 3):
        rows.append(
            [
                photo_router._button(
                    "Как исходник" if ratio == "auto" else ratio,
                    "photo_ratio",
                    workspace_id=workspace_id,
                    value=encode_photo_ratio_callback_value(ratio),
                )
                for ratio in ratios[index : index + 3]
            ]
        )
    rows.extend(
        [
            [
                photo_router._button(
                    (
                        "К качеству"
                        if len(model.supported_photo_resolutions) > 1
                        else "К моделям"
                    ),
                    "photo_back_settings",
                    workspace_id=workspace_id,
                )
            ],
            [photo_router._button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _copy_callback_value(callback_data, *, value: str):
    copy_method = getattr(callback_data, "model_copy", None)
    if copy_method is None:
        copy_method = callback_data.copy
    return copy_method(update={"value": value})


def install_auf_photo_ratio_callback_fix() -> None:
    """Keep aspect ratios compatible with aiogram CallbackData's ':' separator."""

    global _INSTALLED
    if _INSTALLED:
        return

    controller = importlib.import_module(
        "velvet_bot.presentation.telegram.workspace_home_controller"
    )
    original_action = controller.handle_scoped_meow_action

    async def handle_scoped_auf_action_with_safe_ratio(
        callback,
        callback_data,
        state,
        access_policy,
        kie_settings,
        database,
        ai_usage_service,
        ai_task_queue_service,
        meow_runtime_service,
        meow_wallet_service,
        meow_purchase_service,
    ) -> None:
        if callback_data.action == "photo_ratio":
            decoded = decode_photo_ratio_callback_value(callback_data.value)
            callback_data = _copy_callback_value(callback_data, value=decoded)
        await original_action(
            callback,
            callback_data,
            state,
            access_policy,
            kie_settings,
            database,
            ai_usage_service,
            ai_task_queue_service,
            meow_runtime_service,
            meow_wallet_service,
            meow_purchase_service,
        )

    photo_router._ratio_keyboard = build_safe_photo_ratio_keyboard
    controller.handle_scoped_meow_action = handle_scoped_auf_action_with_safe_ratio
    _INSTALLED = True


__all__ = (
    "build_safe_photo_ratio_keyboard",
    "decode_photo_ratio_callback_value",
    "encode_photo_ratio_callback_value",
    "install_auf_photo_ratio_callback_fix",
)
