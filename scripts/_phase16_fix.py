from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "velvet_bot/handlers/owner_actions.py"
text = path.read_text(encoding="utf-8")
marker = "\ndef _topic_line(character: Character) -> str:\n"
if text.count(marker) != 1:
    raise RuntimeError("Stable owner action tail marker not found")
prefix = text.split(marker, 1)[0].rstrip()

tail = r'''


@router.callback_query(OwnerActionCallback.filter())
async def handle_owner_action_callback(
    callback: CallbackQuery,
    callback_data: OwnerActionCallback,
    reference_uploads: ReferenceUploadSessions,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    action = callback_data.action
    if action == "menu":
        await _safe_edit(callback.message, _main_text(), _main_keyboard())
    elif action in {"characters", "media", "references", "aliases", "data"}:
        await _safe_edit(
            callback.message,
            _section_text(action),
            _section_keyboard(action),
        )
    elif action == "map":
        await _safe_edit(
            callback.message,
            _map_text(),
            InlineKeyboardMarkup(inline_keyboard=[_back_row()]),
        )
    elif action.startswith("form."):
        await _send_form(callback.message, action.removeprefix("form."))
    elif action.startswith("media."):
        await _send_media_form(callback.message, action.removeprefix("media."))
    elif action in {"direct.refdone", "direct.refcancel"}:
        session = finish_reference_upload(
            reference_uploads,
            user_id=callback.from_user.id,
        )
        if session is None:
            text = "Активной загрузки референсов нет."
        elif action == "direct.refdone":
            text = (
                "<b>Загрузка завершена</b>\n\n"
                f"Персонаж: <b>{escape(session.character_name)}</b>\n"
                f"Добавлено за сеанс: <b>{session.added_count}</b>"
            )
        else:
            text = "Загрузка референсов остановлена."
        await callback.message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[_back_row("references")]
            ),
        )
    elif action == "ask.aliasreindex":
        await _safe_edit(
            callback.message,
            "<b>Пересобрать индекс алиасов и связей хэштегов?</b>",
            _confirm_keyboard("aliasreindex", "🔄 Пересобрать", back="aliases"),
        )
    elif action == "do.aliasreindex":
        result = await rebuild_alias_index(database)
        await callback.message.answer(
            "<b>Индекс хэштегов пересобран.</b>\n\n"
            f"Новых основных алиасов: <b>{result.created_name_aliases}</b>\n"
            f"Распознано связей: <b>{result.matched_links}</b> из "
            f"<b>{result.total_hashtags}</b>.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[_back_row("aliases")]
            ),
        )
    else:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return
    await callback.answer()


@router.message(OwnerActionReplyFilter())
async def handle_owner_action_reply(
    message: Message,
    owner_action: str,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    reference_uploads: ReferenceUploadSessions,
    analytics_channel_ids: frozenset[int],
    publication_timezone: str = "Europe/Berlin",
) -> None:
    del publication_timezone
    value = (message.text or message.caption or "").strip()
    if value.casefold() in {"отмена", "cancel"}:
        await message.answer(_main_text(), reply_markup=_main_keyboard())
        return

    actor_id = message.from_user.id if message.from_user else None
    try:
        if await handle_owner_media_action(
            message=message,
            owner_action=owner_action,
            value=value,
            database=database,
            bot=bot,
            audit_logger=audit_logger,
            analytics_channel_ids=analytics_channel_ids,
            actor_id=actor_id,
        ):
            return
        if await handle_owner_profile_action(
            message=message,
            owner_action=owner_action,
            value=value,
            database=database,
            bot=bot,
            actor_id=actor_id,
        ):
            return
        if await handle_owner_reference_action(
            message=message,
            owner_action=owner_action,
            value=value,
            database=database,
            bot=bot,
            audit_logger=audit_logger,
            reference_uploads=reference_uploads,
            actor_id=actor_id,
        ):
            return
        if await handle_owner_data_action(
            message=message,
            owner_action=owner_action,
            value=value,
            database=database,
            bot=bot,
            analytics_channel_ids=analytics_channel_ids,
            actor_id=actor_id,
        ):
            return
        raise ValueError("Неизвестная форма действия.")
    except (ValueError, RuntimeError) as error:
        await message.answer(
            escape(str(error)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back_row()]),
        )


__all__ = (
    "OwnerActionCallback",
    "OwnerActionReplyFilter",
    "router",
)
'''

path.write_text(prefix + tail, encoding="utf-8")

(ROOT / "scripts/_phase16_fix.py").unlink()
(ROOT / ".github/workflows/phase16-fix.yml").unlink()
