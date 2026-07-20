from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest

from velvet_bot.archive_topic_links import list_characters_by_archive_topic
from velvet_bot.core.config.settings import DEFAULT_ADULT_CHANNEL_ID, parse_chat_id
from velvet_bot.domains.archive import ArchivePage, ArchivedMedia
from velvet_bot.domains.characters.models import CharacterRecord
from velvet_bot.domains.public_archive import PublicMediaState
from velvet_bot.domains.public_archive.visibility import (
    PUBLIC_IMAGE_MAX_BYTES,
    public_media_visibility_sql,
)
from velvet_bot.public_adult_access import has_adult_channel_access
from velvet_bot.public_archive_display import build_viewer_caption
from velvet_bot.public_manager_ui import build_manager_archive_keyboard


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class AdminPublicArchiveControlsTests(unittest.TestCase):
    def _page(
        self,
        *,
        is_public: bool = True,
        requires_adult_channel: bool = False,
    ) -> ArchivePage:
        return ArchivePage(
            character=CharacterRecord(
                id=7,
                name="Аид",
                created_by=1,
                created_in_chat=2,
                created_at=datetime(2026, 7, 19, tzinfo=UTC),
                archive_chat_id=-1001,
                archive_thread_id=10,
                archive_topic_url="https://t.me/c/1/10",
            ),
            media=ArchivedMedia(
                id=9,
                telegram_file_id="file",
                media_type="photo",
                original_file_name="aid.jpg",
                storage_file_name="stored.jpg",
                mime_type="image/jpeg",
                file_size=100,
                linked_at=datetime(2026, 7, 19, tzinfo=UTC),
                is_public=is_public,
                requires_adult_channel=requires_adult_channel,
            ),
            offset=0,
            total=1,
        )

    def test_manager_keyboard_has_visibility_and_adult_actions(self) -> None:
        page = self._page()
        keyboard = build_manager_archive_keyboard(
            page,
            PublicMediaState(
                like_count=3,
                liked_by_user=False,
                subscribed=False,
                subscriber_count=8,
            ),
            category="male",
            universe="original",
            story_id=0,
        )
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("🙈 Скрыть из публичного", labels)
        self.assertIn("🔞 Пометить как +18", labels)

    def test_manager_caption_shows_metrics_review_and_watermark_state(self) -> None:
        caption = build_viewer_caption(
            self._page(is_public=False, requires_adult_channel=True),
            PublicMediaState(
                like_count=2,
                liked_by_user=True,
                subscribed=True,
                subscriber_count=11,
                view_count=19,
                download_count=4,
                reviewed_by_owner=False,
                watermark_applied=True,
                watermark_approved=False,
            ),
            manager_access=True,
        )
        self.assertIn("Подписок на героя: <b>11</b>", caption)
        self.assertIn("Просмотров: <b>19</b>", caption)
        self.assertIn("Скачиваний: <b>4</b>", caption)
        self.assertIn("Просмотр 7221553045: <b>🆕 не просмотрено</b>", caption)
        self.assertIn("Watermark: <b>нанесён, ожидает одобрения</b>", caption)
        self.assertIn("Публичный архив: <b>скрыт</b>", caption)
        self.assertIn("Канал +18: <b>требуется подписка</b>", caption)

    def test_migrations_keep_access_metrics_and_shared_topics_separate(self) -> None:
        visibility = Path(
            "migrations/026_public_archive_visibility_and_adult_access.sql"
        ).read_text(encoding="utf-8")
        topics = Path("migrations/027_multi_character_archive_topics.sql").read_text(
            encoding="utf-8"
        )
        activity = Path(
            "migrations/105_public_archive_downloads_and_watermarks.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("is_public BOOLEAN", visibility)
        self.assertIn("requires_adult_channel BOOLEAN", visibility)
        self.assertIn("CREATE TABLE IF NOT EXISTS character_archive_topics", topics)
        self.assertIn("DROP INDEX IF EXISTS uq_characters_archive_topic", topics)
        self.assertIn(
            "PRIMARY KEY (character_id, archive_chat_id, archive_thread_id)",
            topics,
        )
        self.assertIn("watermark_approved BOOLEAN", activity)
        self.assertIn("CREATE TABLE IF NOT EXISTS public_media_view_stats", activity)
        self.assertIn("CREATE TABLE IF NOT EXISTS public_media_download_stats", activity)

    def test_public_queries_support_regular_and_member_visibility(self) -> None:
        self.assertEqual(20 * 1024 * 1024, PUBLIC_IMAGE_MAX_BYTES)
        regular = public_media_visibility_sql()
        member = public_media_visibility_sql(
            include_adult_restricted=True,
            include_oversized_images=True,
        )
        self.assertIn("cm.is_public = TRUE", regular)
        self.assertIn("cm.requires_adult_channel = FALSE", regular)
        self.assertIn("mf.file_size", regular)
        self.assertIn(str(PUBLIC_IMAGE_MAX_BYTES), regular)
        self.assertNotIn("requires_adult_channel = FALSE", member)
        self.assertNotIn("mf.file_size", member)

        for relative in (
            "velvet_bot/domains/archive/repository.py",
            "velvet_bot/domains/public_archive/repository.py",
            "velvet_bot/public_directory.py",
            "velvet_bot/public_media_lookup.py",
        ):
            with self.subTest(path=relative):
                source = Path(relative).read_text(encoding="utf-8")
                self.assertIn("public_media_visibility_sql", source)

    def test_rename_and_shared_topic_routes_are_registered(self) -> None:
        bundle = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        rename = Path(
            "velvet_bot/presentation/telegram/routers/characters/rename.py"
        ).read_text(encoding="utf-8")
        archive_save = Path(
            "velvet_bot/presentation/telegram/routers/archive/save.py"
        ).read_text(encoding="utf-8")
        self.assertIn("character_rename_router", bundle)
        self.assertIn("✏️ Переименовать", rename)
        self.assertIn("router.callback_query.register", rename)
        self.assertIn("for character in characters:", archive_save)
        self.assertIn("list_characters_by_archive_topic", archive_save)

    def test_member_channel_parser_uses_requested_velvet_default(self) -> None:
        self.assertEqual(-1003951213065, DEFAULT_ADULT_CHANNEL_ID)
        self.assertEqual(
            DEFAULT_ADULT_CHANNEL_ID,
            parse_chat_id(
                "",
                variable_name="ADULT_CHANNEL_ID",
                default=DEFAULT_ADULT_CHANNEL_ID,
            ),
        )
        self.assertEqual(-10042, parse_chat_id("-10042", variable_name="X", default=1))


class AdultChannelAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_membership_check_uses_configured_channel(self) -> None:
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status="member", is_member=True)
            )
        )
        self.assertTrue(
            await has_adult_channel_access(bot, 77, channel_id=-1003951213065)
        )
        bot.get_chat_member.assert_awaited_once_with(
            chat_id=-1003951213065,
            user_id=77,
        )

    async def test_missing_adult_channel_is_a_denied_check_not_an_error(self) -> None:
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=SimpleNamespace(),
                    message="Bad Request: chat not found",
                )
            )
        )
        with self.assertLogs("velvet_bot.public_adult_access", level="INFO") as logs:
            allowed = await has_adult_channel_access(bot, 77, channel_id=-10042)
        self.assertFalse(allowed)
        self.assertTrue(any("channel is unavailable" in line for line in logs.output))


class SharedArchiveTopicTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_topic_returns_multiple_characters(self) -> None:
        timestamp = datetime(2026, 7, 19, tzinfo=UTC)
        connection = SimpleNamespace(
            fetch=AsyncMock(
                return_value=[
                    {
                        "id": 1,
                        "name": "Аид",
                        "created_by": 1,
                        "created_in_chat": 2,
                        "created_at": timestamp,
                        "archive_chat_id": -1001,
                        "archive_thread_id": 10,
                        "archive_topic_url": "https://t.me/c/1/10",
                    },
                    {
                        "id": 2,
                        "name": "Тесса",
                        "created_by": 1,
                        "created_in_chat": 2,
                        "created_at": timestamp,
                        "archive_chat_id": -1001,
                        "archive_thread_id": 10,
                        "archive_topic_url": "https://t.me/c/1/10",
                    },
                ]
            )
        )
        database = SimpleNamespace(acquire=lambda: _AsyncContext(connection))

        characters = await list_characters_by_archive_topic(
            database,
            archive_chat_id=-1001,
            archive_thread_id=10,
        )

        self.assertEqual(["Аид", "Тесса"], [item.name for item in characters])
        connection.fetch.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
