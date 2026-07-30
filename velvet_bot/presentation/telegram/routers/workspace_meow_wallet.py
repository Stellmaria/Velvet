from __future__ import annotations

from html import escape

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.domains.meow_wallet import (
    MeowWalletAccessError,
    MeowWalletOperation,
    MeowWalletService,
    MeowWalletStatus,
    format_auf_units,
)
from velvet_bot.presentation.telegram.routers.workspace_meow import MeowCallback
from velvet_bot.workspace_ui import workspace_callback

_OPERATION_LABELS = {
    MeowWalletOperation.GRANT: "начисление",
    MeowWalletOperation.PURCHASE: "покупка",
    MeowWalletOperation.RESERVE: "резерв",
    MeowWalletOperation.RELEASE: "возврат резерва",
    MeowWalletOperation.CAPTURE: "генерация",
    MeowWalletOperation.REFUND: "возврат",
    MeowWalletOperation.MANUAL_DEBIT: "ручное списание",
    MeowWalletOperation.ADJUSTMENT: "корректировка",
}


def _callback(action: str, *, workspace_id: int, value: str = "") -> str:
    return MeowCallback(
        action=action,
        workspace_id=int(workspace_id),
        value=value,
    ).pack()


def _wallet_keyboard(
    *,
    workspace_id: int,
    global_owner: bool,
    frozen: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if global_owner:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"+{amount}",
                    callback_data=_callback(
                        "wallet_grant",
                        workspace_id=workspace_id,
                        value=str(amount),
                    ),
                )
                for amount in (40, 100, 250)
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔓 Разморозить" if frozen else "🔒 Заморозить",
                    callback_data=_callback(
                        "wallet_unfreeze" if frozen else "wallet_freeze",
                        workspace_id=workspace_id,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Мяу",
                callback_data=workspace_callback("meow", workspace_id=workspace_id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _entry_line(entry) -> str:
    sign = "+" if entry.amount_units > 0 else "−"
    amount = format_auf_units(abs(entry.amount_units))
    label = _OPERATION_LABELS.get(entry.operation_type, entry.operation_type.value)
    comment = f" · {escape(entry.comment)}" if entry.comment else ""
    return f"• {sign}{amount} · {escape(label)}{comment}"


async def _render_wallet(
    callback: CallbackQuery,
    *,
    workspace_id: int,
    service: MeowWalletService,
) -> None:
    try:
        overview = await service.overview(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
            history_limit=8,
        )
        quotes = await service.package_quotes(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
        )
    except (PermissionError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    wallet = overview.wallet
    history = "\n".join(_entry_line(item) for item in overview.recent_entries)
    if not history:
        history = "• операций пока нет"
    packages = "\n".join(
        f"• <b>{quote.amount_auf} Ауф</b> · {quote.price_rub:.0f} ₽ · ${quote.price_usd:.2f}"
        for quote in quotes
    )
    text = (
        "<b>💳 Кошелёк Ауф</b>\n\n"
        f"Доступно: <b>{format_auf_units(wallet.available_units)}</b>\n"
        f"В резерве: <b>{format_auf_units(wallet.reserved_units)}</b>\n"
        f"Потрачено за 30 дней: <b>{format_auf_units(overview.spent_30d_units)}</b>\n"
        f"Статус: <b>{'заморожен' if wallet.status is MeowWalletStatus.FROZEN else 'активен'}</b>\n\n"
        "<b>Пакеты по текущему курсу</b>\n"
        f"{packages}\n\n"
        "<b>Последние операции</b>\n"
        f"{history}\n\n"
        "1 Ауф покрывает до $0.02 расходов API. Розничная цена одного Ауф — $0.03. "
        "Дополнительная наценка при списании за модель не применяется."
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text,
            reply_markup=_wallet_keyboard(
                workspace_id=workspace_id,
                global_owner=service.is_global_owner(callback.from_user.id),
                frozen=wallet.status is MeowWalletStatus.FROZEN,
            ),
        )
    await callback.answer()


async def handle_meow_wallet_action(
    callback: CallbackQuery,
    callback_data: MeowCallback,
    state: FSMContext,
    meow_wallet_service: MeowWalletService,
) -> None:
    workspace_id = int(callback_data.workspace_id)
    action = callback_data.action
    if action == "wallet":
        await state.clear()
        await _render_wallet(
            callback,
            workspace_id=workspace_id,
            service=meow_wallet_service,
        )
        return

    try:
        if action == "wallet_grant":
            amount = int(callback_data.value)
            await meow_wallet_service.grant(
                workspace_id=workspace_id,
                amount_auf=amount,
                actor_user_id=callback.from_user.id,
                comment="Ручное начисление через экран кошелька.",
                idempotency_key=f"telegram-wallet-grant:{callback.id}",
            )
        elif action == "wallet_freeze":
            await meow_wallet_service.set_frozen(
                workspace_id=workspace_id,
                frozen=True,
                actor_user_id=callback.from_user.id,
            )
        elif action == "wallet_unfreeze":
            await meow_wallet_service.set_frozen(
                workspace_id=workspace_id,
                frozen=False,
                actor_user_id=callback.from_user.id,
            )
        else:
            await callback.answer("Неизвестная команда кошелька Ауф.", show_alert=True)
            return
    except (MeowWalletAccessError, ValueError, RuntimeError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    await _render_wallet(
        callback,
        workspace_id=workspace_id,
        service=meow_wallet_service,
    )


__all__ = ("handle_meow_wallet_action",)
