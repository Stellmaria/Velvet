from __future__ import annotations

import logging
from html import escape

from aiogram.exceptions import TelegramAPIError
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
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback
from velvet_bot.workspace_ui import workspace_callback

logger = logging.getLogger(__name__)

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
    return AufCallback(
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
                    text=f"{amount} вельветов",
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
        f"• <code>{invoice.public_code}</code> · {invoice.package_auf} вельветов · "
        f"{invoice.final_local_amount:.0f} ₽ · {escape(_INVOICE_LABELS[invoice.status])}"
    )


async def _notify_owner_purchase_intent(
    callback: CallbackQuery,
    *,
    workspace_id: int,
    invoice,
) -> None:
    username = callback.from_user.username
    user_label = f"@{escape(username)}" if username else escape(callback.from_user.full_name)
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Подтвердить оплату · {invoice.public_code}",
                    callback_data=_callback(
                        "wallet_invoice_confirm",
                        workspace_id=workspace_id,
                        value=invoice.public_code,
                    ),
                )
            ]
        ]
    )
    try:
        await callback.bot.send_message(
            GLOBAL_WORKSPACE_CREATOR_ID,
            "<b>Запрос на пополнение вельветов</b>\n\n"
            f"Пользователь: {user_label}\n"
            f"Telegram ID: <code>{callback.from_user.id}</code>\n"
            f"Пространство: <code>{workspace_id}</code>\n"
            f"Пакет: <b>{invoice.package_auf} вельветов</b>\n"
            f"К оплате: <b>{invoice.final_local_amount:.0f} ₽</b>\n"
            f"Счёт: <code>{invoice.public_code}</code>\n\n"
            "После получения оплаты нажмите кнопку подтверждения или используйте "
            f"<code>/velvet_grant {callback.from_user.id} {invoice.package_auf}</code>.",
            reply_markup=markup,
        )
    except TelegramAPIError:
        logger.exception(
            "Could not notify owner about Auf purchase intent invoice=%s",
            invoice.public_code,
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

    global_owner = wallet_service.is_global_owner(callback.from_user.id)
    wallet = overview.wallet
    history = "\n".join(_entry_line(item) for item in overview.recent_entries)
    packages = "\n".join(
        (
            f"• <b>{quote.amount_auf} вельветов</b> · {quote.price_rub:.0f} ₽"
            + (f" · ${quote.price_usd:.2f}" if global_owner else "")
        )
        for quote in quotes
    )
    invoice_lines = "\n".join(_invoice_line(item) for item in invoices)
    internal = ""
    if global_owner:
        settings = await wallet_service.economy_settings(actor_user_id=callback.from_user.id)
        internal = (
            "\n\n<b>Внутренняя экономика</b>\n"
            f"Покрытие API: <code>${settings.provider_auf_usd}</code> за вельвет\n"
            f"Базовая розница: <code>${settings.retail_auf_usd}</code> за вельвет\n"
            f"Расчётный курс: <code>{settings.billing_usd_to_rub} ₽/$</code>"
        )
    text = (
        "<b>💳 Кошелёк вельветов</b>\n\n"
        f"Доступно: <b>{format_auf_units(wallet.available_units)}</b>\n"
        f"В резерве: <b>{format_auf_units(wallet.reserved_units)}</b>\n"
        f"Потрачено за 30 дней: <b>{format_auf_units(overview.spent_30d_units)}</b>\n"
        f"Статус: <b>{'заморожен' if wallet.status is AufWalletStatus.FROZEN else 'активен'}</b>\n\n"
        "<b>Пакеты</b>\n"
        f"{packages}\n\n"
        "Нажмите пакет, чтобы создать заявку на пополнение. Цена фиксируется на 24 часа. "
        "После оплаты Стэл подтвердит заявку, и вельветы появятся на балансе.\n\n"
        "<b>Последние счета</b>\n"
        f"{invoice_lines or '• счетов пока нет'}\n\n"
        "<b>Последние операции</b>\n"
        f"{history or '• операций пока нет'}"
        f"{internal}"
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text,
            reply_markup=_wallet_keyboard(
                workspace_id=workspace_id,
                global_owner=global_owner,
                frozen=wallet.status is AufWalletStatus.FROZEN,
                invoices=invoices,
            ),
        )
    if answer_callback:
        await callback.answer()


async def handle_auf_wallet_action(
    callback: CallbackQuery,
    callback_data: AufCallback,
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
            await _notify_owner_purchase_intent(
                callback,
                workspace_id=workspace_id,
                invoice=invoice,
            )
            alert = (
                f"Заявка {invoice.public_code}: {invoice.package_auf} вельветов за "
                f"{invoice.final_local_amount:.0f} ₽. Стэл получила уведомление."
            )
        elif action == "wallet_invoice_confirm":
            invoice, _ = await auf_purchase_service.confirm_paid(
                public_code=callback_data.value,
                actor_user_id=callback.from_user.id,
            )
            alert = (
                f"Оплата {invoice.public_code} подтверждена. "
                f"Начислено {invoice.package_auf} вельветов."
            )
            if invoice.created_by_user_id != callback.from_user.id:
                try:
                    await callback.bot.send_message(
                        invoice.created_by_user_id,
                        "<b>Пополнение подтверждено</b>\n\n"
                        f"Начислено: <b>{invoice.package_auf} вельветов</b>\n"
                        f"Счёт: <code>{invoice.public_code}</code>",
                    )
                except TelegramAPIError:
                    logger.exception(
                        "Could not notify user about paid Auf invoice=%s",
                        invoice.public_code,
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


wallet_keyboard = _wallet_keyboard


def install_wallet_keyboard_builder(builder) -> None:
    """Install a wallet keyboard decorator through an explicit public hook."""

    global _wallet_keyboard, wallet_keyboard
    _wallet_keyboard = builder
    wallet_keyboard = builder
