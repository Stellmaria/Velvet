import unittest
from dataclasses import replace
from datetime import UTC, datetime

from velvet_bot.archive_catalog import ArchivePage, ArchivedMedia
from velvet_bot.archive_ui import ArchiveMediaCallback, build_archive_navigation
from velvet_bot.database import Character
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers.media_prompt_binding import _prompt_marker


class MediaPromptBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        character = Character(
            id=7,
            name="Аид",
            created_by=1,
            created_in_chat=2,
            created_at=datetime(2026, 7, 15, tzinfo=UTC),
            archive_chat_id=None,
            archive_thread_id=None,
            archive_topic_url=None,
        )
        self.media = ArchivedMedia(
            id=11,
            telegram_file_id="photo-file-id",
            media_type="photo",
            original_file_name=None,
            storage_file_name="photo.jpg",
            mime_type="image/jpeg",
            file_size=100,
            linked_at=datetime(2026, 7, 15, tzinfo=UTC),
        )
        self.page = ArchivePage(character=character, media=self.media, offset=0, total=2)

    def test_owner_sees_bind_button_without_prompt(self) -> None:
        keyboard = build_archive_navigation(self.page)
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        bind = next(button for button in buttons if button.text == "📝 Привязать промт")
        callback = ArchiveMediaCallback.unpack(bind.callback_data)
        self.assertEqual("prompt", callback.action)
        self.assertEqual(11, callback.media_id)

    def test_owner_sees_open_change_and_remove_with_prompt(self) -> None:
        page = replace(
            self.page,
            media=replace(self.media, prompt_post_url="https://t.me/velvet/123"),
        )
        labels = [
            button.text
            for row in build_archive_navigation(page).inline_keyboard
            for button in row
        ]
        self.assertIn("📝 Открыть промт", labels)
        self.assertIn("✏️ Изменить", labels)
        self.assertIn("🗑 Убрать", labels)

    def test_prompt_marker_contains_exact_media_identity(self) -> None:
        self.assertEqual(
            "PROMPT_MEDIA:7:11:3",
            _prompt_marker(character_id=7, media_id=11, offset=3),
        )


if __name__ == "__main__":
    unittest.main()
