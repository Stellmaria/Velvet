from __future__ import annotations

import importlib

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.domains.auf_wallet import format_margin_summary

_INSTALLED = False


def install_auf_margin_dashboard() -> None:
    """Add an owner-only P&L screen without widening the public wallet UI."""

    global _INSTALLED
    if _INSTALLED:
        return

    wallet_ui = importlib.import_module("velvet_bot.app.auf_wallet_currency_ui")
    controller = importlib.import_module(
        "velvet_bot.presentation.telegram.workspace_home_controller"
    )
    original_keyboard = wallet_ui._wallet_keyboard
    original_action = controller.handle_scoped_auf_action

    def wallet_keyboard_with_margin(
        *,
        workspace_id: int,
        global_owner: bool,
        frozen: bool,
        invoices,
        currency: str,
    ) -> InlineKeyboardMarkup:
        markup = original_keyboard(
            workspace_id=workspace_id,
            global_owner=global_owner,
            frozen=frozen,
            invoices=invoices,
            currency=currency,
        )
        if not global_owner:
            return markup
        rows = [list(row) for row in markup.inline_keyboard]
        rows.insert(
            max(0, len(rows) - 1),
            [
                InlineKeyboardButton(
                    text="📊 P&L генераций · 30 дней",
                    callback_data=wallet_ui._callback(
                        "wallet_pnl",
                        workspace_id=workspace_id,
                    ),
                )
            ],
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def handle_scoped_auf_action_with_margin(
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
    ) -> None:
        if callback_data.action == "wallet_pnl":
            try:
                summary = await auf_wallet_service.margin_summary(
                    actor_user_id=callback.from_user.id,
                    days=30,
                )
            except (PermissionError, ValueError, RuntimeError) as error:
                await callback.answer(str(error), show_alert=True)
                return
            if isinstance(callback.message, Message):
                await callback.message.edit_text(
                    format_margin_summary(summary),
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="↩️ Кошелёк",
                                    callback_data=wallet_ui._callback(
                                        "wallet",
                                        workspace_id=int(callback_data.workspace_id),
                                    ),
                                )
                            ]
                        ]
                    ),
                )
            await callback.answer()
            return
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

    wallet_ui._wallet_keyboard = wallet_keyboard_with_margin
    controller.handle_scoped_auf_action = handle_scoped_auf_action_with_margin
    _INSTALLED = True


__all__ = ("install_auf_margin_dashboard",)
