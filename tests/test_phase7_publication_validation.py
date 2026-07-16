from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.publication import (
    DuplicateDraftInfo,
    DuplicatePostInfo,
    PublicationCharacterInfo,
    PublicationDraft,
    PublicationItem,
    PublicationValidationContext,
    PublicationValidationService,
)


def make_draft(*, text: str = "", items: tuple[PublicationItem, ...] = ()) -> PublicationDraft:
    return PublicationDraft(
        id=10,
        owner_id=20,
        target_chat_id=-100123,
        source_chat_id=20,
        source_message_id=30,
        source_media_group_id=None,
        text_content=text,
        status="draft",
        post_type="unknown",
        has_spoiler=False,
        content_hash="a" * 64,
        validation_status="pending",
        validation_error_count=0,
        validation_warning_count=0,
        validation_report=(),
        scheduled_at=None,
        published_at=None,
        published_message_ids=(),
        attempt_count=0,
        last_error=None,
        created_at=datetime(2026, 7, 16, tzinfo=UTC),
        updated_at=datetime(2026, 7, 16, tzinfo=UTC),
        items=items,
    )


class PublicationValidationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_publication_is_reported_as_error(self) -> None:
        draft = make_draft()
        drafts = SimpleNamespace(get_draft=AsyncMock(return_value=draft))
        validation = SimpleNamespace(
            load_context=AsyncMock(
                return_value=PublicationValidationContext((), None, None)
            ),
            save_result=AsyncMock(side_effect=lambda draft, **_: draft),
        )
        service = PublicationValidationService(
            drafts=drafts,
            validation=validation,
        )

        await service.validate(10, owner_id=20)

        call = validation.save_result.await_args
        issues = call.kwargs["issues"]
        self.assertTrue(any(item.code == "empty" and item.severity == "error" for item in issues))

    async def test_missing_character_metadata_is_reported(self) -> None:
        draft = make_draft(text="#Каэль")
        character = PublicationCharacterInfo(
            id=7,
            name="Каэль",
            category=None,
            universe=None,
            story_id=None,
            has_multi_story=False,
            normalized_alias="каэль",
        )
        drafts = SimpleNamespace(get_draft=AsyncMock(return_value=draft))
        validation = SimpleNamespace(
            load_context=AsyncMock(
                return_value=PublicationValidationContext((character,), None, None)
            ),
            save_result=AsyncMock(side_effect=lambda draft, **_: draft),
        )
        service = PublicationValidationService(drafts=drafts, validation=validation)

        await service.validate(10, owner_id=20)

        issues = validation.save_result.await_args.kwargs["issues"]
        codes = {item.code for item in issues}
        self.assertIn("category", codes)
        self.assertIn("universe", codes)

    async def test_duplicate_context_creates_warnings(self) -> None:
        draft = make_draft(text="Публикация")
        context = PublicationValidationContext(
            characters=(),
            duplicate_draft=DuplicateDraftInfo(id=11, status="scheduled"),
            duplicate_post=DuplicatePostInfo(
                message_id=99,
                message_url="https://t.me/example/99",
            ),
        )
        drafts = SimpleNamespace(get_draft=AsyncMock(return_value=draft))
        validation = SimpleNamespace(
            load_context=AsyncMock(return_value=context),
            save_result=AsyncMock(side_effect=lambda draft, **_: draft),
        )
        service = PublicationValidationService(drafts=drafts, validation=validation)

        await service.validate(10, owner_id=20)

        issues = validation.save_result.await_args.kwargs["issues"]
        codes = {item.code for item in issues}
        self.assertIn("duplicate_draft", codes)
        self.assertIn("duplicate_post", codes)

    async def test_mixed_document_album_is_rejected(self) -> None:
        base = dict(
            id=1,
            draft_id=10,
            telegram_file_unique_id=None,
            mime_type=None,
            file_name=None,
            file_size=None,
            source_message_id=None,
            has_spoiler=False,
        )
        items = (
            PublicationItem(position=0, telegram_file_id="doc", media_type="document", **base),
            PublicationItem(position=1, telegram_file_id="photo", media_type="photo", **base),
        )
        draft = make_draft(text="Альбом", items=items)
        drafts = SimpleNamespace(get_draft=AsyncMock(return_value=draft))
        validation = SimpleNamespace(
            load_context=AsyncMock(
                return_value=PublicationValidationContext((), None, None)
            ),
            save_result=AsyncMock(side_effect=lambda draft, **_: draft),
        )
        service = PublicationValidationService(drafts=drafts, validation=validation)

        await service.validate(10, owner_id=20)

        issues = validation.save_result.await_args.kwargs["issues"]
        self.assertTrue(any(item.code == "album_mixed_document" for item in issues))


if __name__ == "__main__":
    unittest.main()
