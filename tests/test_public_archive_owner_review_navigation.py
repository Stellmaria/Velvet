from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.archive import ArchivePage, ArchivedMedia
from velvet_bot.domains.characters.models import CharacterRecord
from velvet_bot.domains.public_archive import PublicMediaState
from velvet_bot.domains.public_archive.models import PUBLIC_ARCHIVE_REVIEWER_ID
from velvet_bot.presentation.telegram.routers.public_archive.media_display import (
    _PreparedMedia,
    _owner_review_media_after_navigation,
    _prepare_media,
    _record_target_view_before_display,
    handle_spoiler_aware_open,
)
from velvet_bot.public_ui import PublicArchiveCallback, build_public_archive_keyboard


class PublicArchiveOwnerReviewNavigationTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _page(*, media_id: int, offset: int, total: int = 3) -> ArchivePage:
        return ArchivePage(
            character=CharacterRecord(
                id=7,
                name="Аид",
                created_by=1,
                created_in_chat=2,
                created_at=datetime(2026, 7, 21, tzinfo=UTC),
                archive_chat_id=-1001,
                archive_thread_id=10,
                archive_topic_url="https://t.me/c/1/10",
            ),
            media=ArchivedMedia(
                id=media_id,
                telegram_file_id=f"file-{media_id}",
                media_type="photo",
                original_file_name=f"{media_id}.jpg",
                storage_file_name=f"stored-{media_id}.jpg",
                mime_type="image/jpeg",
                file_size=100,
                linked_at=datetime(2026, 7, 21, tzinfo=UTC),
                is_public=True,
            ),
            offset=offset,
            total=total,
        )

    @staticmethod
    def _state() -> PublicMediaState:
        return PublicMediaState(
            like_count=0,
            liked_by_user=False,
            subscribed=False,
        )

    def test_arrow_callbacks_carry_the_card_being_left(self) -> None:
        page = self._page(media_id=91, offset=1)
        keyboard = build_public_archive_keyboard(
            page,
            self._state(),
            viewer_user_id=PUBLIC_ARCHIVE_REVIEWER_ID,
        )
        arrows = [
            PublicArchiveCallback.unpack(button.callback_data)
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
            and PublicArchiveCallback.unpack(button.callback_data).action == "show"
        ]

        self.assertEqual({0, 2}, {item.offset for item in arrows})
        self.assertEqual({91}, {item.media_id for item in arrows})

    def test_first_owner_open_does_not_record_review(self) -> None:
        callback_data = PublicArchiveCallback(
            action="open",
            character_id=7,
            offset=0,
            media_id=91,
        )

        self.assertFalse(
            _record_target_view_before_display(
                action=callback_data.action,
                user_id=PUBLIC_ARCHIVE_REVIEWER_ID,
            )
        )
        self.assertIsNone(
            _owner_review_media_after_navigation(
                callback_data,
                user_id=PUBLIC_ARCHIVE_REVIEWER_ID,
            )
        )

    def test_regular_users_keep_immediate_view_metrics(self) -> None:
        self.assertTrue(
            _record_target_view_before_display(action="open", user_id=77)
        )
        self.assertTrue(
            _record_target_view_before_display(action="show", user_id=77)
        )

    async def test_show_accepts_source_media_id_in_callback(self) -> None:
        callback_data = PublicArchiveCallback(
            action="show",
            character_id=7,
            offset=2,
            media_id=91,
        )
        target_page = self._page(media_id=92, offset=2)

        with (
            patch(
                "velvet_bot.presentation.telegram.routers.public_archive.media_display.has_public_manager_access",
                return_value=True,
            ),
            patch(
                "velvet_bot.presentation.telegram.routers.public_archive.media_display._member_access",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "velvet_bot.presentation.telegram.routers.public_archive.media_display.get_archive_page",
                new=AsyncMock(return_value=target_page),
            ),
        ):
            prepared = await _prepare_media(
                callback_data=callback_data,
                database=SimpleNamespace(),
                bot=SimpleNamespace(),
                user_id=PUBLIC_ARCHIVE_REVIEWER_ID,
                user=SimpleNamespace(id=PUBLIC_ARCHIVE_REVIEWER_ID),
                access_policy=SimpleNamespace(),
                adult_channel_id=-1001,
            )

        self.assertIsNone(prepared.error)
        self.assertEqual(92, prepared.page.media.id if prepared.page and prepared.page.media else 0)

    async def test_owner_arrow_marks_previous_after_successful_display(self) -> None:
        source_media_id = 91
        target_page = self._page(media_id=92, offset=2)
        callback_data = PublicArchiveCallback(
            action="show",
            character_id=7,
            offset=2,
            media_id=source_media_id,
        )
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=PUBLIC_ARCHIVE_REVIEWER_ID),
            message=SimpleNamespace(),
            answer=AsyncMock(),
        )
        events: list[object] = []

        async def display(**_kwargs) -> None:
            events.append("display")

        async def record(_database, *, character_id, media_id, user_id) -> None:
            events.append(("record", character_id, media_id, user_id))

        with (
            patch(
                "velvet_bot.presentation.telegram.routers.public_archive.media_display._prepare_media",
                new=AsyncMock(
                    return_value=_PreparedMedia(
                        page=target_page,
                        manager_access=True,
                        member_access=True,
                    )
                ),
            ),
            patch(
                "velvet_bot.presentation.telegram.routers.public_archive.media_display._can_download",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "velvet_bot.presentation.telegram.routers.public_archive.media_display.replace_preview_archive_page",
                new=AsyncMock(side_effect=display),
            ),
            patch(
                "velvet_bot.presentation.telegram.routers.public_archive.media_display.record_public_media_view",
                new=AsyncMock(side_effect=record),
            ),
        ):
            await handle_spoiler_aware_open(
                callback=callback,
                callback_data=callback_data,
                database=SimpleNamespace(),
                bot=SimpleNamespace(),
                access_policy=SimpleNamespace(),
                adult_channel_id=-1001,
            )

        self.assertEqual(
            [
                "display",
                (
                    "record",
                    target_page.character.id,
                    source_media_id,
                    PUBLIC_ARCHIVE_REVIEWER_ID,
                ),
            ],
            events,
        )

    async def test_regular_user_still_records_target_before_display(self) -> None:
        target_page = self._page(media_id=92, offset=2)
        callback_data = PublicArchiveCallback(
            action="show",
            character_id=7,
            offset=2,
            media_id=91,
        )
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=77),
            message=SimpleNamespace(),
            answer=AsyncMock(),
        )
        events: list[object] = []

        async def display(**_kwargs) -> None:
            events.append("display")

        async def record(_database, *, character_id, media_id, user_id) -> None:
            events.append(("record", character_id, media_id, user_id))

        with (
            patch(
                "velvet_bot.presentation.telegram.routers.public_archive.media_display._prepare_media",
                new=AsyncMock(
                    return_value=_PreparedMedia(
                        page=target_page,
                        manager_access=False,
                        member_access=False,
                    )
                ),
            ),
            patch(
                "velvet_bot.presentation.telegram.routers.public_archive.media_display._can_download",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "velvet_bot.presentation.telegram.routers.public_archive.media_display.replace_preview_archive_page",
                new=AsyncMock(side_effect=display),
            ),
            patch(
                "velvet_bot.presentation.telegram.routers.public_archive.media_display.record_public_media_view",
                new=AsyncMock(side_effect=record),
            ),
        ):
            await handle_spoiler_aware_open(
                callback=callback,
                callback_data=callback_data,
                database=SimpleNamespace(),
                bot=SimpleNamespace(),
                access_policy=SimpleNamespace(),
                adult_channel_id=-1001,
            )

        self.assertEqual(
            [
                ("record", target_page.character.id, 92, 77),
                "display",
            ],
            events,
        )


if __name__ == "__main__":
    unittest.main()
