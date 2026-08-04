from __future__ import annotations

from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message

from velvet_bot.database import Database
from velvet_bot.domains.auf_wallet import (
    AufPricingRepository,
    AufWalletService,
    auf_to_units,
    format_auf_units,
)
from velvet_bot.domains.user_registry import (
    TelegramUserNotFound,
    TelegramUserRepository,
)

router = Router(name="velvet_bot.presentation.telegram.routers.user_management")
_AMOUNT_QUANT = Decimal("0.0001")
_MARKUP_QUANT = Decimal("0.01")
_MARKUP_RESET_WORDS = frozenset({"reset", "default", "сброс", "общая", "global"})


def _is_owner(message: Message, wallet_service: AufWalletService) -> bool:
    return bool(
        message.from_user
        and wallet_service.is_global_owner(int(message.from_user.id))
    )


def _args(message: Message) -> list[str]:
    return (message.text or "").split()[1:]


def _display_user(row: Any, *, fallback_id: int | None = None) -> str:
    user_id = int(row["user_id"]) if row is not None else int(fallback_id or 0)
    username = str(row["username"] or "").strip() if row is not None else ""
    name_parts = []
    if row is not None:
        name_parts = [
            str(row[key]).strip()
            for key in ("first_name", "last_name")
            if row[key]
        ]
    label = f"@{username}" if username else " ".join(name_parts) or str(user_id)
    return f"{escape(label)} · <code>{user_id}</code>"


def _positive_amount(raw: str) -> Decimal | None:
    try:
        amount = Decimal(raw.replace(",", "."))
        if not amount.is_finite():
            return None
        normalized = amount.quantize(_AMOUNT_QUANT)
    except InvalidOperation:
        return None
    if amount != normalized:
        return None
    if normalized <= 0 or normalized > Decimal("1000000"):
        return None
    return normalized if auf_to_units(normalized) > 0 else None


def _markup_percent(raw: str) -> Decimal | None:
    try:
        value = Decimal(raw.replace(",", "."))
        if not value.is_finite():
            return None
        normalized = value.quantize(_MARKUP_QUANT)
    except InvalidOperation:
        return None
    if value != normalized or normalized < 0 or normalized > Decimal("1000"):
        return None
    return normalized


def _compact_decimal(value: Decimal) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


@router.message(Command("velvet_grant"))
async def grant_velvets(
    message: Message,
    user_registry: TelegramUserRepository,
    auf_wallet_service: AufWalletService,
) -> None:
    if not _is_owner(message, auf_wallet_service):
        return
    args = _args(message)
    if len(args) < 2:
        await message.answer(
            "<b>Начисление вельветов</b>\n\n"
            "<code>/velvet_grant @username 100</code>\n"
            "<code>/velvet_grant 123456789 100 Бонус</code>"
        )
        return
    selector, amount_text = args[0], args[1]
    amount = _positive_amount(amount_text)
    if amount is None:
        await message.answer(
            "Сумма должна быть положительным числом до 1 000 000 "
            "с точностью не больше четырёх знаков."
        )
        return

    user_row = None
    try:
        user_row = await user_registry.resolve_user(selector)
        target_user_id = int(user_row["user_id"])
    except TelegramUserNotFound as error:
        raw = selector.strip()
        if not raw.lstrip("-").isdigit():
            await message.answer(str(error))
            return
        target_user_id = int(raw)

    try:
        workspace = await user_registry.resolve_personal_workspace(target_user_id)
    except TelegramUserNotFound as error:
        await message.answer(str(error))
        return

    comment = " ".join(args[2:]).strip() or "Начисление Стэл через /velvet_grant."
    wallet = await auf_wallet_service.grant(
        workspace_id=int(workspace["id"]),
        amount_auf=amount,
        actor_user_id=int(message.from_user.id),
        comment=comment,
        idempotency_key=f"telegram-command-grant:{message.chat.id}:{message.message_id}",
    )
    amount_label = format_auf_units(auf_to_units(amount))
    await message.answer(
        "<b>Вельветы начислены</b>\n\n"
        f"Пользователь: {_display_user(user_row, fallback_id=target_user_id)}\n"
        f"Пространство: <b>{escape(str(workspace['name']))}</b>\n"
        f"Начислено: <b>{amount_label}</b>\n"
        f"Новый баланс: <b>{format_auf_units(wallet.available_units)}</b>"
    )
    try:
        await message.bot.send_message(
            target_user_id,
            "<b>Баланс пополнен</b>\n\n"
            f"Начислено: <b>{amount_label}</b>\n"
            f"Доступно: <b>{format_auf_units(wallet.available_units)}</b>\n\n"
            f"Комментарий: {escape(comment)}",
        )
    except TelegramAPIError:
        await message.answer(
            "Начисление выполнено, но личное уведомление пользователю не доставлено."
        )


@router.message(Command("velvet_markup"))
async def set_user_markup(
    message: Message,
    user_registry: TelegramUserRepository,
    auf_wallet_service: AufWalletService,
    database: Database,
) -> None:
    if not _is_owner(message, auf_wallet_service):
        return
    args = _args(message)
    if not args:
        await message.answer(
            "<b>Индивидуальная наценка</b>\n\n"
            "Установить: <code>/velvet_markup @username 45</code>\n"
            "Минимум: <b>15%</b>\n"
            "Проверить: <code>/velvet_markup @username</code>\n"
            "Вернуть общую: <code>/velvet_markup @username reset</code>"
        )
        return
    try:
        user = await user_registry.resolve_user(args[0])
    except TelegramUserNotFound as error:
        await message.answer(str(error))
        return

    user_id = int(user["user_id"])
    pricing = AufPricingRepository(database)
    if len(args) == 1:
        policy = await pricing.user_markup_policy(user_id)
    elif args[1].strip().casefold() in _MARKUP_RESET_WORDS:
        policy = await pricing.clear_user_markup(user_id=user_id)
    else:
        percent = _markup_percent(args[1])
        if percent is None:
            await message.answer("Процент должен быть числом от 0 до 1000, максимум два знака после запятой.")
            return
        try:
            policy = await pricing.set_user_markup(
                user_id=user_id,
                markup_percent=percent,
                actor_user_id=int(message.from_user.id),
            )
        except ValueError as error:
            await message.answer(str(error))
            return

    if policy.override_markup_percent is None:
        mode = "общая"
        detail = "Индивидуальная настройка удалена."
    else:
        mode = "индивидуальная"
        detail = (
            "Общая наценка остаётся "
            f"{_compact_decimal(policy.global_markup_percent)}%. "
            "Защитный минимум индивидуальной наценки: "
            f"{_compact_decimal(policy.minimum_user_markup_percent)}%."
        )
    await message.answer(
        "<b>Наценка пользователя обновлена</b>\n\n"
        f"Пользователь: {_display_user(user)}\n"
        f"Режим: <b>{mode}</b>\n"
        "Эффективная наценка: "
        f"<b>{_compact_decimal(policy.effective_markup_percent)}%</b>\n"
        f"{detail}\n\n"
        "Новые расчёты цены будут использовать этот процент; уже подтверждённые задачи не меняются."
    )


@router.message(Command("velvet_user"))
async def show_velvet_user(
    message: Message,
    user_registry: TelegramUserRepository,
    auf_wallet_service: AufWalletService,
) -> None:
    if not _is_owner(message, auf_wallet_service):
        return
    args = _args(message)
    if not args:
        await message.answer("Использование: <code>/velvet_user @username</code>")
        return
    try:
        user = await user_registry.resolve_user(args[0])
        profile = await user_registry.user_profile(int(user["user_id"]))
    except TelegramUserNotFound as error:
        await message.answer(str(error))
        return

    available = int(profile["available_units"] or 0)
    reserved = int(profile["reserved_units"] or 0)
    workspace = escape(str(profile["workspace_name"] or "не выбрано"))
    await message.answer(
        "<b>Карточка пользователя</b>\n\n"
        f"Пользователь: {_display_user(profile)}\n"
        f"Первый вход: <b>{profile['first_seen_at']:%d.%m.%Y %H:%M}</b>\n"
        f"Последняя активность: <b>{profile['last_seen_at']:%d.%m.%Y %H:%M}</b>\n"
        f"Пространство: <b>{workspace}</b>\n"
        f"Баланс: <b>{format_auf_units(available)}</b> · резерв "
        f"<b>{format_auf_units(reserved)}</b>\n\n"
        f"Обновлений: <b>{int(profile['update_count'] or 0)}</b>\n"
        f"Команд: <b>{int(profile['command_count'] or 0)}</b> · кнопок: "
        f"<b>{int(profile['callback_count'] or 0)}</b>\n"
        f"Генераций: <b>{int(profile['total_count'] or 0)}</b> · успешно: "
        f"<b>{int(profile['success_count'] or 0)}</b> · ошибок: "
        f"<b>{int(profile['error_count'] or 0)}</b>\n"
        f"Списано за генерации: <b>{format_auf_units(int(profile['spent_units'] or 0))}</b>\n"
        f"Счетов: <b>{int(profile['invoice_count'] or 0)}</b> · оплачено: "
        f"<b>{int(profile['paid_invoice_count'] or 0)}</b> на "
        f"<b>{Decimal(profile['paid_rub'] or 0):.0f} ₽</b>"
    )


@router.message(Command("velvet_users"))
async def list_velvet_users(
    message: Message,
    user_registry: TelegramUserRepository,
    auf_wallet_service: AufWalletService,
) -> None:
    if not _is_owner(message, auf_wallet_service):
        return
    args = _args(message)
    try:
        requested = int(args[0]) if args else 20
    except ValueError:
        requested = 20
    limit = max(1, min(30, requested))
    rows = await user_registry.recent_users(limit=limit)
    lines = ["<b>Последние пользователи</b>"]
    for row in rows:
        balance = format_auf_units(int(row["available_units"] or 0))
        workspace = escape(str(row["workspace_name"] or "без пространства"))
        lines.append(
            f"• {_display_user(row)}\n"
            f"  {workspace} · {balance} · {row['last_seen_at']:%d.%m %H:%M}"
        )
    await message.answer("\n\n".join(lines) if rows else "Пользователей пока нет.")


__all__ = ("router",)
