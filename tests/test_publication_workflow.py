import unittest
from datetime import UTC, datetime

from aiogram.enums import ChatType
from aiogram.types import Chat, Message, User

from velvet_bot.presentation.telegram.routers.publication.center import PublicationCallback
from velvet_bot.presentation.telegram.routers.publication.safe import PublicationReplyMarkerFilter
from velvet_bot.publication_worker import split_publication_text
from velvet_bot.publication_workflow import (
    PublicationDraft,
    PublicationIssue,
    PublicationItem,
)


class PublicationWorkflowTests(unittest.TestCase):
    def test_long_text_is_split_within_telegram_limit(self) -> None:
        text = ("Абзац для публикации. " * 500).strip()
        chunks = split_publication_text(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(1 <= len(chunk) <= 4096 for chunk in chunks))
        self.assertEqual(" ".join(text.split()), " ".join(" ".join(chunks).split()))

    def test_callback_data_stays_under_telegram_limit(self) -> None:
        values = [
            PublicationCallback(
                action="open",
                draft_id=9_223_372_036_854_775_000,
                page=999,
                section="published",
            ).pack(),
            PublicationCallback(
                action="schedule",
                draft_id=9_223_372_036_854_775_000,
                page=999,
                section="cancelled",
            ).pack(),
        ]
        for value in values:
            self.assertLessEqual(len(value.encode("utf-8")), 64)

    def test_publication_models_keep_validation_report(self) -> None:
        issue = PublicationIssue("story", "error", "Нет истории", "Каэль")
        item = PublicationItem(
            id=1,
            draft_id=2,
            position=0,
            telegram_file_id="file-id",
            telegram_file_unique_id="unique-id",
            media_type="photo",
            mime_type="image/jpeg",
            file_name=None,
            file_size=100,
            source_message_id=50,
            has_spoiler=True,
        )
        draft = PublicationDraft(
            id=2,
            owner_id=10,
            target_chat_id=-1003802812639,
            source_chat_id=10,
            source_message_id=50,
            source_media_group_id=None,
            text_content="#Каэль",
            status="checked",
            post_type="art",
            has_spoiler=True,
            content_hash="0" * 64,
            validation_status="failed",
            validation_error_count=1,
            validation_warning_count=0,
            validation_report=(issue,),
            scheduled_at=datetime(2026, 7, 20, tzinfo=UTC),
            published_at=None,
            published_message_ids=(),
            attempt_count=0,
            last_error=None,
            created_at=datetime(2026, 7, 16, tzinfo=UTC),
            updated_at=datetime(2026, 7, 16, tzinfo=UTC),
            items=(item,),
        )
        self.assertEqual("story", draft.validation_report[0].code)
        self.assertTrue(draft.items[0].has_spoiler)


class PublicationReplyFilterTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def message(reply_text: str | None) -> Message:
        chat = Chat(id=10, type=ChatType.PRIVATE)
        user = User(id=10, is_bot=False, first_name="Owner")
        reply = None
        if reply_text is not None:
            reply = Message(
                message_id=1,
                date=datetime(2026, 7, 16, tzinfo=UTC),
                chat=chat,
                from_user=user,
                text=reply_text,
            )
        return Message(
            message_id=2,
            date=datetime(2026, 7, 16, tzinfo=UTC),
            chat=chat,
            from_user=user,
            text="Ответ",
            reply_to_message=reply,
        )

    async def test_marker_filter_accepts_only_publication_replies(self) -> None:
        filter_ = PublicationReplyMarkerFilter()
        self.assertTrue(await filter_(self.message("PUBLICATION_SCHEDULE:42")))
        self.assertTrue(await filter_(self.message("PUBLICATION_TEXT:42")))
        self.assertFalse(await filter_(self.message("PROMPT_MEDIA:42")))
        self.assertFalse(await filter_(self.message(None)))


if __name__ == "__main__":
    unittest.main()
