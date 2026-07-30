from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from velvet_bot.database import Database


@dataclass(frozen=True, slots=True)
class TelegramUserIdentity:
    user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    is_bot: bool = False
    is_premium: bool | None = None


class TelegramUserNotFound(LookupError):
    pass


class TelegramUserRepository:
    """Privacy-minimal user registry and usage-event ledger.

    The registry stores Telegram identity fields and interaction metadata, but never
    message text, prompts, media contents, callback values or file identifiers.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    async def observe(
        self,
        identity: TelegramUserIdentity,
        *,
        event_type: str,
        chat_id: int | None,
        chat_type: str | None,
        module_key: str | None = None,
        command_name: str | None = None,
        callback_action: str | None = None,
        workspace_id: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        event = _limited(event_type, 32) or "update"
        username = _username(identity.username)
        async with self._database.acquire() as connection:
            async with connection.transaction():
                if username:
                    await connection.execute(
                        """
                        UPDATE telegram_users
                        SET username = NULL, updated_at = NOW()
                        WHERE user_id <> $1::BIGINT
                          AND LOWER(username) = LOWER($2::VARCHAR)
                        """,
                        int(identity.user_id),
                        username,
                    )
                await connection.execute(
                    """
                    INSERT INTO telegram_users (
                        user_id, username, first_name, last_name, language_code,
                        is_bot, is_premium, first_seen_at, last_seen_at,
                        last_private_seen_at, last_chat_id, last_chat_type,
                        last_workspace_id, update_count, message_count,
                        callback_count, command_count, inline_count,
                        created_at, updated_at
                    )
                    VALUES (
                        $1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::VARCHAR, $5::VARCHAR,
                        $6::BOOLEAN, $7::BOOLEAN, NOW(), NOW(),
                        CASE WHEN $9::VARCHAR = 'private' THEN NOW() ELSE NULL END,
                        $8::BIGINT, $9::VARCHAR,
                        COALESCE(
                            $10::BIGINT,
                            (SELECT active_workspace_id
                             FROM user_workspace_preferences
                             WHERE user_id = $1::BIGINT)
                        ),
                        1,
                        CASE WHEN $11::VARCHAR IN ('message', 'command') THEN 1 ELSE 0 END,
                        CASE WHEN $11::VARCHAR = 'callback' THEN 1 ELSE 0 END,
                        CASE WHEN $11::VARCHAR = 'command' THEN 1 ELSE 0 END,
                        CASE WHEN $11::VARCHAR = 'inline' THEN 1 ELSE 0 END,
                        NOW(), NOW()
                    )
                    ON CONFLICT (user_id) DO UPDATE
                    SET username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        language_code = EXCLUDED.language_code,
                        is_bot = EXCLUDED.is_bot,
                        is_premium = EXCLUDED.is_premium,
                        last_seen_at = NOW(),
                        last_private_seen_at = CASE
                            WHEN EXCLUDED.last_chat_type = 'private' THEN NOW()
                            ELSE telegram_users.last_private_seen_at
                        END,
                        last_chat_id = EXCLUDED.last_chat_id,
                        last_chat_type = EXCLUDED.last_chat_type,
                        last_workspace_id = COALESCE(
                            EXCLUDED.last_workspace_id,
                            telegram_users.last_workspace_id
                        ),
                        update_count = telegram_users.update_count + 1,
                        message_count = telegram_users.message_count +
                            CASE WHEN $11::VARCHAR IN ('message', 'command') THEN 1 ELSE 0 END,
                        callback_count = telegram_users.callback_count +
                            CASE WHEN $11::VARCHAR = 'callback' THEN 1 ELSE 0 END,
                        command_count = telegram_users.command_count +
                            CASE WHEN $11::VARCHAR = 'command' THEN 1 ELSE 0 END,
                        inline_count = telegram_users.inline_count +
                            CASE WHEN $11::VARCHAR = 'inline' THEN 1 ELSE 0 END,
                        updated_at = NOW()
                    """,
                    int(identity.user_id),
                    username,
                    _limited(identity.first_name, 128),
                    _limited(identity.last_name, 128),
                    _limited(identity.language_code, 16),
                    bool(identity.is_bot),
                    identity.is_premium,
                    int(chat_id) if chat_id is not None else None,
                    _limited(chat_type, 24),
                    int(workspace_id) if workspace_id is not None else None,
                    event,
                )
                await connection.execute(
                    """
                    INSERT INTO telegram_user_events (
                        user_id, event_type, module_key, command_name,
                        callback_action, workspace_id, chat_id, chat_type, metadata
                    )
                    VALUES (
                        $1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::VARCHAR,
                        $5::VARCHAR, $6::BIGINT, $7::BIGINT, $8::VARCHAR, $9::JSONB
                    )
                    """,
                    int(identity.user_id),
                    event,
                    _limited(module_key, 48),
                    _limited(command_name, 64),
                    _limited(callback_action, 96),
                    int(workspace_id) if workspace_id is not None else None,
                    int(chat_id) if chat_id is not None else None,
                    _limited(chat_type, 24),
                    json.dumps(dict(metadata or {}), ensure_ascii=False, default=str),
                )

    async def resolve_user(self, selector: str | int) -> Mapping[str, Any]:
        raw = str(selector).strip()
        if not raw:
            raise TelegramUserNotFound("Укажите Telegram ID или @username.")
        async with self._database.acquire() as connection:
            if raw.lstrip("-").isdigit():
                row = await connection.fetchrow(
                    "SELECT * FROM telegram_users WHERE user_id = $1::BIGINT",
                    int(raw),
                )
            else:
                username = raw.lstrip("@").strip().casefold()
                row = await connection.fetchrow(
                    """
                    SELECT *
                    FROM telegram_users
                    WHERE LOWER(username) = $1::VARCHAR
                    ORDER BY last_seen_at DESC, user_id DESC
                    LIMIT 1
                    """,
                    username,
                )
        if row is None:
            raise TelegramUserNotFound(
                "Пользователь ещё не попадал в реестр бота. Он должен хотя бы один раз открыть бота."
            )
        return row

    async def resolve_personal_workspace(self, user_id: int) -> Mapping[str, Any]:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT workspace.id, workspace.name, membership.role
                FROM user_workspace_preferences AS preference
                JOIN workspaces AS workspace
                  ON workspace.id = preference.active_workspace_id
                 AND workspace.is_system = FALSE
                JOIN workspace_members AS membership
                  ON membership.workspace_id = workspace.id
                 AND membership.user_id = preference.user_id
                WHERE preference.user_id = $1::BIGINT
                LIMIT 1
                """,
                int(user_id),
            )
            if row is None:
                row = await connection.fetchrow(
                    """
                    SELECT workspace.id, workspace.name, membership.role
                    FROM workspace_members AS membership
                    JOIN workspaces AS workspace
                      ON workspace.id = membership.workspace_id
                     AND workspace.is_system = FALSE
                    WHERE membership.user_id = $1::BIGINT
                    ORDER BY
                        CASE membership.role
                            WHEN 'owner' THEN 0
                            WHEN 'admin' THEN 1
                            WHEN 'editor' THEN 2
                            WHEN 'reviewer' THEN 3
                            ELSE 4
                        END,
                        membership.updated_at DESC,
                        workspace.id DESC
                    LIMIT 1
                    """,
                    int(user_id),
                )
        if row is None:
            raise TelegramUserNotFound(
                "У пользователя нет личного пространства, поэтому начислять вельветы некуда."
            )
        return row

    async def recent_users(self, *, limit: int = 20) -> tuple[Mapping[str, Any], ...]:
        safe_limit = max(1, min(100, int(limit)))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    user.user_id, user.username, user.first_name, user.last_name,
                    user.first_seen_at, user.last_seen_at, user.update_count,
                    user.command_count, user.callback_count,
                    workspace.id AS workspace_id, workspace.name AS workspace_name,
                    wallet.available_units, wallet.reserved_units
                FROM telegram_users AS user
                LEFT JOIN workspaces AS workspace
                  ON workspace.id = user.last_workspace_id
                LEFT JOIN auf_wallets AS wallet
                  ON wallet.workspace_id = workspace.id
                ORDER BY user.last_seen_at DESC, user.user_id DESC
                LIMIT $1::INTEGER
                """,
                safe_limit,
            )
        return tuple(rows)

    async def user_profile(self, user_id: int) -> Mapping[str, Any]:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                WITH generation AS (
                    SELECT
                        COUNT(*) FILTER (WHERE task.status = 'success') AS success_count,
                        COUNT(*) FILTER (WHERE task.status = 'error') AS error_count,
                        COUNT(*) AS total_count,
                        COALESCE(SUM(charge.captured_units), 0) AS spent_units
                    FROM ai_tasks AS task
                    LEFT JOIN auf_task_charges AS charge ON charge.task_id = task.id
                    WHERE task.created_by = $1::BIGINT
                      AND task.task_type = 'media.generate.kie'
                ), purchase AS (
                    SELECT
                        COUNT(*) AS invoice_count,
                        COUNT(*) FILTER (WHERE status = 'paid') AS paid_invoice_count,
                        COALESCE(SUM(final_local_amount) FILTER (WHERE status = 'paid'), 0) AS paid_rub
                    FROM auf_purchase_invoices
                    WHERE created_by_user_id = $1::BIGINT
                )
                SELECT
                    user.*,
                    workspace.name AS workspace_name,
                    wallet.available_units,
                    wallet.reserved_units,
                    generation.success_count,
                    generation.error_count,
                    generation.total_count,
                    generation.spent_units,
                    purchase.invoice_count,
                    purchase.paid_invoice_count,
                    purchase.paid_rub
                FROM telegram_users AS user
                LEFT JOIN workspaces AS workspace ON workspace.id = user.last_workspace_id
                LEFT JOIN auf_wallets AS wallet ON wallet.workspace_id = workspace.id
                CROSS JOIN generation
                CROSS JOIN purchase
                WHERE user.user_id = $1::BIGINT
                """,
                int(user_id),
            )
        if row is None:
            raise TelegramUserNotFound("Пользователь не найден в реестре.")
        return row


def _username(value: object) -> str | None:
    normalized = str(value or "").strip().lstrip("@")
    return _limited(normalized, 64)


def _limited(value: object, limit: int) -> str | None:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized[:limit] if normalized else None


__all__ = (
    "TelegramUserIdentity",
    "TelegramUserNotFound",
    "TelegramUserRepository",
)
