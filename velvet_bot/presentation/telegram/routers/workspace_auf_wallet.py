from __future__ import annotations

from html import escape

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.domains.auf_wallet import (
    AUF_PACKAGES,
    AufInvoiceError,
    AufInvoiceStatus,
    AufPurchaseService,
    AufWalletAccessError,
    AufWalletOperation,
    AufWalletService,
    AufWalletStatus,
    format_auf_units,
)
from velvet_bot.presentation.telegram.routers.workspace_meow import MeowCallback
from velvet_bot.workspace_ui import workspace_callback

_OPERATION_LABELS = {
    AufWalletOperation.GRANT: "начисление",
    AufWalletOperation.PURCHASE: "покупка",
    AufWalletOperation.RESERVE: "резерв",
    AufWalletOperation.RELEASE: "возврат резерва",
    AufWalletOperation.CAPTURE: "генерация",
    AufWalletOperation.REFUND: "возврат",
    AufWalletOperation.MANUAL_DEBIT: "ручное списание",
    AufWalletOperation.ADJUSTMENT: "корректировка",
}
_INVOICE_LABELS = {
    AufInvoiceStatus.CREATED: "ожидает оплаты",
    AufInvoiceStatus.PAID: "оплачен",
    AufInvoiceStatus.EXPIRED: "истёк",
    AufInvoiceStatus.CANCELLED: "отменён",
    AufInvoiceStatus.REFUNDED: "возвращён",
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
    invoices,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for package_row in (AUF_PACKAGES[:3], AUF_PACKAGES[3:]):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{amount} Ауф",
                    callback_data=_callback(
                        "wallet_buy",
                        workspace_id=workspace_id,
                        value=str(amount),
                    ),
                )
                for amount in package_row
            ]
        )
    pending = [item for item in invoices if item.status is AufInvoiceStatus.CREATED]
    for invoice in pending[:3]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"✅ Подтвердить {invoice.public_code}"
                        if global_owner
                        else f"✖ Отменить {invoice.public_code}"
                    ),
                    callback_data=_callback(
                        "wallet_invoice_confirm" if global_owner else "wallet_invoice_cancel",
                        workspace_id=workspace_id,
                        value=invoice.public_code,
                    ),
                )
            ]
        )
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
                text="↩️ Ауф",
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


def _invoice_line(invoice) -> str:
    return (
        f"• <code>{invoice.public_code}</code> · {invoice.package_auf} Ауф · "
        f"{invoice.final_local_amount:.0f} ₽ · {escape(_INVOICE_LABELS[invoice.status])}"
    )


async def _render_wallet(
    callback: CallbackQuery,
    *,
    workspace_id: int,
    wallet_service: AufWalletService,
    purchase_service: AufPurchaseService,
    answer_callback: bool = True,
) -> None:
    try:
        overview = await wallet_service.overview(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
            history_limit=8,
        )
        quotes = await wallet_service.package_quotes(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
        )
        invoices = await purchase_service.recent_invoices(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
            limit=5,
        )
    except (PermissionError, ValueError) as error:
        if answer_callback:
            await callback.answer(str(error), show_alert=True)
        return

    wallet = overview.wallet
    history = "\n".join(_entry_line(item) for item in overview.recent_entries)
    packages = "\n".join(
        f"• <b>{quote.amount_auf} Ауф</b> · {quote.price_rub:.0f} ₽ · ${quote.price_usd:.2f}"
        for quote in quotes
    )
    invoice_lines = "\n".join(_invoice_line(item) for item in invoices)
    text = (
        "<b>💳 Кошелёк Ауф</b>\n\n"
        f"Доступно: <b>{format_auf_units(wallet.available_units)}</b>\n"
        f"В резерве: <b>{format_auf_units(wallet.reserved_units)}</b>\n"
        f"Потрачено за 30 дней: <b>{format_auf_units(overview.spent_30d_units)}</b>\n"
        f"Статус: <b>{'заморожен' if wallet.status is AufWalletStatus.FROZEN else 'активен'}</b>\n\n"
        "<b>Пакеты по текущему курсу</b>\n"
        f"{packages}\n\n"
        "Нажмите пакет, чтобы создать счёт с зафиксированным курсом на 24 часа. "
        "Оплата подтверждается Стэл вручную; повторное подтверждение не начислит Ауф дважды.\n\n"
        "<b>Последние счета</b>\n"
        f"{invoice_lines or '• счетов пока нет'}\n\n"
        "<b>Последние операции</b>\n"
        f"{history or '• операций пока нет'}\n\n"
        "1 Ауф покрывает до $0.02 расходов API. Розничная цена одного Ауф — $0.03. "
        "Дополнительная наценка при списании за модель не применяется."
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text,
            reply_markup=_wallet_keyboard(
                workspace_id=workspace_id,
                global_owner=wallet_service.is_global_owner(callback.from_user.id),
                frozen=wallet.status is AufWalletStatus.FROZEN,
                invoices=invoices,
            ),
        )
    if answer_callback:
        await callback.answer()


async def handle_auf_wallet_action(
    callback: CallbackQuery,
    callback_data: MeowCallback,
    state: FSMContext,
    auf_wallet_service: AufWalletService,
    auf_purchase_service: AufPurchaseService,
) -> None:
    workspace_id = int(callback_data.workspace_id)
    action = callback_data.action
    if action == "wallet":
        await state.clear()
        await _render_wallet(
            callback,
            workspace_id=workspace_id,
            wallet_service=auf_wallet_service,
            purchase_service=auf_purchase_service,
        )
        return

    alert: str | None = None
    try:
        if action == "wallet_buy":
            invoice = await auf_purchase_service.create_invoice(
                workspace_id=workspace_id,
                package_auf=int(callback_data.value),
                actor_user_id=callback.from_user.id,
                idempotency_key=f"telegram-wallet-invoice:{callback.id}",
            )
            alert = (
                f"Счёт {invoice.public_code}: {invoice.package_auf} Ауф за "
                f"{invoice.final_local_amount:.0f} ₽. Курс зафиксирован на 24 часа."
            )
        elif action == "wallet_invoice_confirm":
            invoice, _ = await auf_purchase_service.confirm_paid(
                public_code=callback_data.value,
                actor_user_id=callback.from_user.id,
            )
            alert = (
                f"Оплата {invoice.public_code} подтверждена. "
                f"Начислено {invoice.package_auf} Ауф."
            )
        elif action == "wallet_invoice_cancel":
            invoice = await auf_purchase_service.cancel_invoice(
                public_code=callback_data.value,
                workspace_id=workspace_id,
                actor_user_id=callback.from_user.id,
            )
            alert = f"Счёт {invoice.public_code} отменён."
        elif action == "wallet_grant":
            amount = int(callback_data.value)
            await auf_wallet_service.grant(
                workspace_id=workspace_id,
                amount_auf=amount,
                actor_user_id=callback.from_user.id,
                comment="Ручное начисление через экран кошелька.",
                idempotency_key=f"telegram-wallet-grant:{callback.id}",
            )
        elif action == "wallet_freeze":
            await auf_wallet_service.set_frozen(
                workspace_id=workspace_id,
                frozen=True,
                actor_user_id=callback.from_user.id,
            )
        elif action == "wallet_unfreeze":
            await auf_wallet_service.set_frozen(
                workspace_id=workspace_id,
                frozen=False,
                actor_user_id=callback.from_user.id,
            )
        else:
            await callback.answer("Неизвестная команда кошелька Ауф.", show_alert=True)
            return
    except (AufInvoiceError, AufWalletAccessError, PermissionError, ValueError, RuntimeError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    if alert:
        await callback.answer(alert, show_alert=True)
    await _render_wallet(
        callback,
        workspace_id=workspace_id,
        wallet_service=auf_wallet_service,
        purchase_service=auf_purchase_service,
        answer_callback=alert is None,
    )



__all__ = ("handle_auf_wallet_action",)
