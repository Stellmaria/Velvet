from __future__ import annotations

from collections.abc import Sequence

from velvet_bot.database import Database
from velvet_bot.domains.roleplay.models import RoleplayMessage, RoleplaySession


class RoleplayRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_session(self, *, chat_id: int, user_id: int) -> RoleplaySession | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT chat_id,user_id,enabled,title,system_prompt,summary,
                          created_at,updated_at
                   FROM roleplay_sessions
                   WHERE chat_id=$1::BIGINT AND user_id=$2::BIGINT""",
                int(chat_id), int(user_id))
        return self._row_to_session(row) if row is not None else None

    async def ensure_session(self, *, chat_id: int, user_id: int) -> RoleplaySession:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """INSERT INTO roleplay_sessions(chat_id,user_id)
                   VALUES($1::BIGINT,$2::BIGINT)
                   ON CONFLICT(chat_id,user_id) DO UPDATE
                   SET updated_at=roleplay_sessions.updated_at
                   RETURNING chat_id,user_id,enabled,title,system_prompt,summary,
                             created_at,updated_at""", int(chat_id), int(user_id))
        if row is None:
            raise RuntimeError("Не удалось создать РЛ-сессию.")
        return self._row_to_session(row)

    async def set_enabled(self, *, chat_id: int, user_id: int,
                          enabled: bool) -> RoleplaySession:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """INSERT INTO roleplay_sessions(chat_id,user_id,enabled)
                   VALUES($1::BIGINT,$2::BIGINT,$3::BOOLEAN)
                   ON CONFLICT(chat_id,user_id) DO UPDATE
                   SET enabled=EXCLUDED.enabled,updated_at=NOW()
                   RETURNING chat_id,user_id,enabled,title,system_prompt,summary,
                             created_at,updated_at""",
                int(chat_id), int(user_id), bool(enabled))
        if row is None:
            raise RuntimeError("Не удалось изменить состояние РЛ-сессии.")
        return self._row_to_session(row)

    async def set_system_prompt(self, *, chat_id: int, user_id: int,
                                system_prompt: str) -> RoleplaySession:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """INSERT INTO roleplay_sessions(chat_id,user_id,system_prompt)
                   VALUES($1::BIGINT,$2::BIGINT,$3::TEXT)
                   ON CONFLICT(chat_id,user_id) DO UPDATE
                   SET system_prompt=EXCLUDED.system_prompt,updated_at=NOW()
                   RETURNING chat_id,user_id,enabled,title,system_prompt,summary,
                             created_at,updated_at""",
                int(chat_id), int(user_id), system_prompt)
        if row is None:
            raise RuntimeError("Не удалось сохранить канон РЛ-сессии.")
        return self._row_to_session(row)

    async def get_recent_messages(self, *, chat_id: int, user_id: int,
                                  limit: int) -> tuple[RoleplayMessage, ...]:
        safe_limit = max(1, min(int(limit), 200))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """SELECT id,chat_id,user_id,role,content,created_at FROM (
                       SELECT id,chat_id,user_id,role,content,created_at
                       FROM roleplay_messages
                       WHERE chat_id=$1::BIGINT AND user_id=$2::BIGINT
                       ORDER BY id DESC LIMIT $3::INTEGER
                   ) AS recent ORDER BY id ASC""",
                int(chat_id), int(user_id), safe_limit)
        return tuple(self._row_to_message(row) for row in rows)

    async def append_exchange(self, *, chat_id: int, user_id: int,
                              user_text: str, assistant_text: str) -> None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """INSERT INTO roleplay_sessions(chat_id,user_id,enabled)
                       VALUES($1::BIGINT,$2::BIGINT,TRUE)
                       ON CONFLICT(chat_id,user_id) DO UPDATE SET updated_at=NOW()""",
                    int(chat_id), int(user_id))
                await connection.executemany(
                    """INSERT INTO roleplay_messages(chat_id,user_id,role,content)
                       VALUES($1::BIGINT,$2::BIGINT,$3::VARCHAR,$4::TEXT)""",
                    ((int(chat_id), int(user_id), "user", user_text),
                     (int(chat_id), int(user_id), "assistant", assistant_text)))

    async def count_messages(self, *, chat_id: int, user_id: int) -> int:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """SELECT COUNT(*) FROM roleplay_messages
                   WHERE chat_id=$1::BIGINT AND user_id=$2::BIGINT""",
                int(chat_id), int(user_id))
        return int(value or 0)

    async def get_compaction_batch(self, *, chat_id: int, user_id: int,
                                   keep_recent: int,
                                   batch_limit: int = 80) -> tuple[RoleplayMessage, ...]:
        safe_keep = max(2, min(int(keep_recent), 200))
        safe_batch = max(2, min(int(batch_limit), 200))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """WITH ranked AS (
                       SELECT id,chat_id,user_id,role,content,created_at,
                              ROW_NUMBER() OVER(ORDER BY id DESC) AS reverse_position
                       FROM roleplay_messages
                       WHERE chat_id=$1::BIGINT AND user_id=$2::BIGINT)
                   SELECT id,chat_id,user_id,role,content,created_at FROM ranked
                   WHERE reverse_position>$3::INTEGER ORDER BY id ASC
                   LIMIT $4::INTEGER""",
                int(chat_id), int(user_id), safe_keep, safe_batch)
        return tuple(self._row_to_message(row) for row in rows)

    async def apply_compaction(self, *, chat_id: int, user_id: int,
                               message_ids: Sequence[int], summary: str) -> None:
        normalized_ids = tuple(int(value) for value in message_ids)
        if not normalized_ids:
            return
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """UPDATE roleplay_sessions SET summary=$3::TEXT,updated_at=NOW()
                       WHERE chat_id=$1::BIGINT AND user_id=$2::BIGINT""",
                    int(chat_id), int(user_id), summary)
                await connection.execute(
                    """DELETE FROM roleplay_messages
                       WHERE chat_id=$1::BIGINT AND user_id=$2::BIGINT
                         AND id=ANY($3::BIGINT[])""",
                    int(chat_id), int(user_id), list(normalized_ids))

    async def clear_history(self, *, chat_id: int, user_id: int) -> None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """DELETE FROM roleplay_messages
                       WHERE chat_id=$1::BIGINT AND user_id=$2::BIGINT""",
                    int(chat_id), int(user_id))
                await connection.execute(
                    """UPDATE roleplay_sessions SET summary='',updated_at=NOW()
                       WHERE chat_id=$1::BIGINT AND user_id=$2::BIGINT""",
                    int(chat_id), int(user_id))

    @staticmethod
    def _row_to_session(row: object) -> RoleplaySession:
        return RoleplaySession(
            chat_id=int(row["chat_id"]), user_id=int(row["user_id"]),
            enabled=bool(row["enabled"]), title=row["title"],
            system_prompt=str(row["system_prompt"] or ""),
            summary=str(row["summary"] or ""), created_at=row["created_at"],
            updated_at=row["updated_at"])  # type: ignore[index]

    @staticmethod
    def _row_to_message(row: object) -> RoleplayMessage:
        return RoleplayMessage(
            id=int(row["id"]), chat_id=int(row["chat_id"]),
            user_id=int(row["user_id"]), role=str(row["role"]),
            content=str(row["content"]),
            created_at=row["created_at"])  # type: ignore[index]


__all__ = ("RoleplayRepository",)
