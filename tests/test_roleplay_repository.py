from __future__ import annotations

import os
import unittest

from velvet_bot.database import Database
from velvet_bot.domains.roleplay import RoleplayCharacterDraft, RoleplayRepository


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class RoleplayRepositoryPostgreSQLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                TRUNCATE
                    rp_memories,
                    rp_messages,
                    rp_session_characters,
                    rp_sessions,
                    rp_characters
                RESTART IDENTITY CASCADE
                """
            )
        self.repository = RoleplayRepository(self.database)

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_character_session_message_and_memory_lifecycle(self) -> None:
        character = await self.repository.create_character(
            owner_user_id=1001,
            draft=RoleplayCharacterDraft(
                name="Аид",
                adult_confirmed=True,
                age_text="25+",
                appearance={"eyes": "gold"},
                personality={"traits": ["reserved"]},
                speech={"style": "brief"},
                canonical_facts=("правитель подземного мира",),
            ),
        )
        self.assertEqual(1001, character.owner_user_id)
        self.assertTrue(character.adult_confirmed)

        session = await self.repository.create_session(
            owner_user_id=1001,
            title="Тронный зал",
            model="velvet-rp",
            scenario="Первая встреча.",
            scene_state={"location": "hall"},
        )
        await self.repository.attach_character(
            owner_user_id=1001,
            session_id=session.id,
            character_id=character.id,
            role_order=1,
            current_state={"mood": "calm"},
        )

        user_message = await self.repository.append_message(
            owner_user_id=1001,
            session_id=session.id,
            role="user",
            content="Я вхожу в зал.",
        )
        assistant_message = await self.repository.append_message(
            owner_user_id=1001,
            session_id=session.id,
            role="assistant",
            speaker_key="P1",
            content="Аид поднимает взгляд.",
        )
        self.assertEqual(1, user_message.sequence_no)
        self.assertEqual(2, assistant_message.sequence_no)

        memory = await self.repository.add_memory(
            owner_user_id=1001,
            session_id=session.id,
            character_id=character.id,
            kind="episodic",
            content="Пользователь вошёл в тронный зал.",
            importance=70,
            source_message_id=user_message.id,
        )
        self.assertEqual("episodic", memory.kind)

        characters = await self.repository.list_session_characters(
            owner_user_id=1001,
            session_id=session.id,
        )
        messages = await self.repository.list_recent_messages(
            owner_user_id=1001,
            session_id=session.id,
        )
        memories = await self.repository.list_memories(
            owner_user_id=1001,
            session_id=session.id,
        )
        self.assertEqual((character.id,), tuple(item.id for item in characters))
        self.assertEqual((1, 2), tuple(item.sequence_no for item in messages))
        self.assertEqual((memory.id,), tuple(item.id for item in memories))

    async def test_archive_character_is_not_visible_as_roleplay_character(self) -> None:
        archive_character, _ = await self.database.create_character(
            "Архивный Аид",
            created_by=1001,
            created_in_chat=1001,
        )
        roleplay_characters = await self.repository.list_characters(
            owner_user_id=1001
        )
        self.assertGreater(archive_character.id, 0)
        self.assertEqual((), roleplay_characters)


if __name__ == "__main__":
    unittest.main()
