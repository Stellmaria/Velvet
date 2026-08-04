from __future__ import annotations

import logging
from decimal import Decimal
from html import escape

from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.domains.auf_wallet import (
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
from velvet_bot.presentation.telegram.routers import workspace_auf_wallet as legacy
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback
from velvet_bot.workspace_ui import workspace_callback

logger = logging.getLogger(__name__)

_CURRENCIES = ("RUB", "USD")
_PACKAGE_CALLBACK_SEPARATOR = "|"


def _normalize_currency(value: object) -> str:
    currency = str(value or "").strip().upper()
    return currency if currency in _CURRENCIES else "RUB"


def _package_callback_value(amount: int, currency: str) -> str:
    return (
        f"{int(amount)}{_PACKAGE_CALLBACK_SEPARATOR}"
        f"{_normalize_currency(currency)}"
    )


def _parse_package_callback_value(value: str) -> tuple[int, str]:
    amount_raw, separator, currency_raw = str(value or "").partition(
        _PACKAGE_CALLBACK_SEPARATOR
    )
    if not separator:
        return int(amount_raw), "RUB"
    return int(amount_raw), _normalize_currency(currency_raw)


def _format_money(amount: Decimal, currency: str) -> str:
    if _normalize_currency(currency) == "USD":
        return f"${Decimal(amount):.2f}"
    return f"{Decimal(amount):.0f} ₽"


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
    currency: str,
) -> InlineKeyboardMarkup:
    selected_currency = _normalize_currency(currency)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=("✅ RUB" if selected_currency == "RUB" else "RUB"),
                callback_data=_callback(
                    "wallet_currency",
                    workspace_id=workspace_id,
                    value="RUB",
                ),
            ),
            InlineKeyboardButton(
                text=("✅ USD" if selected_currency == "USD" else "USD"),
                callback_data=_callback(
                    "wallet_currency",
                    workspace_id=workspace_id,
                    value="USD",
                ),
            ),
        ]
    ]
    for package_row in (legacy.AUF_PACKAGES[:3], legacy.AUF_PACKAGES[3:]):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{amount} вельветов",
                    callback_data=_callback(
                        "wallet_buy",
                        workspace_id=workspace_id,
                        value=_package_callback_value(amount, selected_currency),
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
                        "wallet_invoice_confirm"
                        if global_owner
                        else "wallet_invoice_cancel",
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
                for amount in (20, 100, 250)
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


def _invoice_line(invoice) -> str:
    return (
        f"• <code>{invoice.public_code}</code> · {invoice.package_auf} вельветов · "
        f"{_format_money(invoice.final_local_amount, invoice.billing_currency)} · "
        f"{escape(legacy._INVOICE_LABELS[invoice.status])}"
    )


async def _notify_owner_purchase_intent(
    callback: CallbackQuery,
    *,
    workspace_id: int,
    invoice,
) -> bool:
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
            f"К оплате: <b>{_format_money(invoice.final_local_amount, invoice.billing_currency)}</b>\n"
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
        return False
    return True


async def _render_wallet(
    callback: CallbackQuery,
    *,
    workspace_id: int,
    wallet_service: AufWalletService,
    purchase_service: AufPurchaseService,
    currency: str,
    answer_callback: bool = True,
) -> None:
    selected_currency = _normalize_currency(currency)
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
    history = "\n".join(legacy._entry_line(item) for item in overview.recent_entries)
    packages = "\n".join(
        (
            f"• <b>{quote.amount_auf} вельветов</b> · "
            f"{quote.price_rub:.0f} ₽ · ${quote.price_usd:.2f}"
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
        f"Статус: <b>{'заморожен' if wallet.status is AufWalletStatus.FROZEN else 'активен'}</b>\n"
        f"Валюта нового счёта: <b>{selected_currency}</b>\n\n"
        "<b>Пакеты</b>\n"
        f"{packages}\n\n"
        "Выберите RUB или USD, затем нажмите пакет. Цена фиксируется на 24 часа. "
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
                currency=selected_currency,
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
    selected_currency = "RUB"

    if action == "wallet":
        await state.clear()
        await _render_wallet(
            callback,
            workspace_id=workspace_id,
            wallet_service=auf_wallet_service,
            purchase_service=auf_purchase_service,
            currency=selected_currency,
        )
        return

    if action == "wallet_currency":
        selected_currency = _normalize_currency(callback_data.value)
        await _render_wallet(
            callback,
            workspace_id=workspace_id,
            wallet_service=auf_wallet_service,
            purchase_service=auf_purchase_service,
            currency=selected_currency,
        )
        return

    alert: str | None = None
    try:
        if action == "wallet_buy":
            package_auf, selected_currency = _parse_package_callback_value(
                callback_data.value
            )
            invoice = await auf_purchase_service.create_invoice(
                workspace_id=workspace_id,
                package_auf=package_auf,
                actor_user_id=callback.from_user.id,
                idempotency_key=f"telegram-wallet-invoice:{callback.id}",
                billing_currency=selected_currency,
            )
            owner_notified = await _notify_owner_purchase_intent(
                callback,
                workspace_id=workspace_id,
                invoice=invoice,
            )
            if owner_notified:
                alert = (
                    f"Заявка {invoice.public_code}: {invoice.package_auf} вельветов за "
                    f"{_format_money(invoice.final_local_amount, invoice.billing_currency)}. "
                    "Стэл получила уведомление."
                )
            else:
                alert = (
                    f"Заявка {invoice.public_code} создана, но уведомление Стэл не "
                    "доставлено. Передайте ей код счёта вручную."
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
    except (
        AufInvoiceError,
        AufWalletAccessError,
        PermissionError,
        ValueError,
        RuntimeError,
    ) as error:
        await callback.answer(str(error), show_alert=True)
        return

    if alert:
        await callback.answer(alert, show_alert=True)
    await _render_wallet(
        callback,
        workspace_id=workspace_id,
        wallet_service=auf_wallet_service,
        purchase_service=auf_purchase_service,
        currency=selected_currency,
        answer_callback=alert is None,
    )


__all__ = (
    "_format_money",
    "_normalize_currency",
    "_package_callback_value",
    "_parse_package_callback_value",
    "handle_auf_wallet_action",
)
