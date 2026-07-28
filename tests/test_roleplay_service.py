from __future__ import annotations

import unittest
from datetime import datetime, timezone

from velvet_bot.domains.roleplay.client import GeneratedRoleplayText
from velvet_bot.domains.roleplay.models import RoleplayMessage, RoleplaySession
from velvet_bot.domains.roleplay.service import RoleplayInactiveError, RoleplayService

_NOW = datetime.now(timezone.utc)


class _MemoryRepository:
    def __init__(self, *, enabled: bool = True) -> None:
        self.session = RoleplaySession(
            chat_id=10, user_id=20, enabled=enabled, title=None,
            system_prompt="Эрик сдержан и не доверяет Каэлю.",
            summary="Они впервые встретились на дне рождения Сары.",
            created_at=_NOW, updated_at=_NOW)
        self.messages = (RoleplayMessage(
            id=1, chat_id=10, user_id=20, role="assistant",
            content="Эрик остановился напротив.", created_at=_NOW),)
        self.saved_exchange: tuple[str, str] | None = None

    async def get_session(self, *, chat_id: int, user_id: int) -> RoleplaySession:
        return self.session

    async def ensure_session(self, *, chat_id: int, user_id: int) -> RoleplaySession:
        return self.session

    async def set_enabled(self, *, chat_id: int, user_id: int,
                          enabled: bool) -> RoleplaySession:
        self.session = RoleplaySession(
            chat_id=self.session.chat_id, user_id=self.session.user_id,
            enabled=enabled, title=self.session.title,
            system_prompt=self.session.system_prompt, summary=self.session.summary,
            created_at=self.session.created_at, updated_at=self.session.updated_at)
        return self.session

    async def get_recent_messages(self, *, chat_id: int, user_id: int,
                                  limit: int) -> tuple[RoleplayMessage, ...]:
        return self.messages

    async def count_messages(self, *, chat_id: int, user_id: int) -> int:
        return len(self.messages)

    async def append_exchange(self, *, chat_id: int, user_id: int,
                              user_text: str, assistant_text: str) -> None:
        self.saved_exchange = (user_text, assistant_text)


class _RecordingClient:
    def __init__(self) -> None:
        self.instructions = ""
        self.messages: tuple[RoleplayMessage, ...] = ()

    async def generate(self, *, instructions: str,
                       messages: tuple[RoleplayMessage, ...]) -> GeneratedRoleplayText:
        self.instructions = instructions
        self.messages = tuple(messages)
        return GeneratedRoleplayText(
            text="Каэль лишь улыбнулся.", provider="openai", model="gpt-5-mini")


class RoleplayServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_turn_from_canon_summary_history_and_user_text(self) -> None:
        repository = _MemoryRepository()
        client = _RecordingClient()
        service = RoleplayService(
            repository=repository,  # type: ignore[arg-type]
            client=client, provider_label="openai", model_label="gpt-5-mini",
            max_history_messages=30)
        reply = await service.reply(
            chat_id=10, user_id=20, text="Каэль не отводит взгляд.")
        self.assertIn("Эрик сдержан", client.instructions)
        self.assertIn("дне рождения Сары", client.instructions)
        self.assertEqual(client.messages[0].content, "Эрик остановился напротив.")
        self.assertEqual(client.messages[-1].content, "Каэль не отводит взгляд.")
        self.assertEqual(repository.saved_exchange,
                         ("Каэль не отводит взгляд.", "Каэль лишь улыбнулся."))
        self.assertEqual(reply.provider, "openai")
        self.assertEqual(reply.model, "gpt-5-mini")

    async def test_rejects_plain_turn_when_session_is_inactive(self) -> None:
        repository = _MemoryRepository(enabled=False)
        service = RoleplayService(
            repository=repository,  # type: ignore[arg-type]
            client=_RecordingClient(), provider_label="openai",
            model_label="gpt-5-mini")
        with self.assertRaises(RoleplayInactiveError):
            await service.reply(chat_id=10, user_id=20, text="Продолжай.")


if __name__ == "__main__":
    unittest.main()
