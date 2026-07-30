from __future__ import annotations

from html import escape
from typing import Any

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message

from velvet_bot.domains.auf_wallet import AufWalletService, format_auf_units
from velvet_bot.domains.user_registry import (
    TelegramUserNotFound,
    TelegramUserRepository,
)

router = Router(name="velvet_bot.presentation.telegram.routers.user_management")


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
    try:
        amount = float(amount_text.replace(",", "."))
    except ValueError:
        await message.answer("Сумма должна быть числом больше нуля.")
        return
    if amount <= 0 or amount > 1_000_000:
        await message.answer("Сумма должна быть больше нуля и не превышать 1 000 000.")
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
        amount_auf=str(amount),
        actor_user_id=int(message.from_user.id),
        comment=comment,
        idempotency_key=f"telegram-command-grant:{message.chat.id}:{message.message_id}",
    )
    amount_label = format_auf_units(int(round(amount * 10_000)))
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
        f"<b>{float(profile['paid_rub'] or 0):.0f} ₽</b>"
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
        limit = int(args[0]) if args else 20
    except ValueError:
        limit = 20
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
