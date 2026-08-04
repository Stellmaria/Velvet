from __future__ import annotations

import importlib

from velvet_bot.app.auf_wallet_currency_ui import handle_auf_wallet_action

_INSTALLED = False


def install_auf_wallet_ui() -> None:
    """Route Auf wallet callbacks before the historical generic action handler."""

    global _INSTALLED
    if _INSTALLED:
        return

    controller = importlib.import_module(
        "velvet_bot.presentation.telegram.workspace_home_controller"
    )
    original = controller.handle_scoped_auf_action

    async def handle_scoped_auf_action_with_wallet(
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
        if callback_data.action.startswith("wallet"):
            await handle_auf_wallet_action(
                callback,
                callback_data,
                state,
                auf_wallet_service,
                auf_purchase_service,
            )
            return
        await original(
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

    controller.handle_scoped_auf_action = handle_scoped_auf_action_with_wallet
    _INSTALLED = True


__all__ = ("install_auf_wallet_ui",)
