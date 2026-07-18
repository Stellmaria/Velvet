from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import velvet_bot.analytics_review as analytics_review
from velvet_bot.analytics_review import (
    PublicationReview,
    get_publication_review,
    get_unresolved_tag_review,
    list_character_picker,
    list_publication_reviews,
    list_unresolved_tag_reviews,
    reclassify_automatic_publications,
    reset_publication_type_to_automatic,
    set_manual_publication_type,
)
from velvet_bot.post_classification import POST_TYPE_LABELS


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.exited = True
        return False


class _TransactionContext:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.exited = True
        return False


def _publication(
    *,
    token_id: int = 5,
    post_type: str = "unknown",
    confidence: int = 40,
    source: str = "automatic",
) -> PublicationReview:
    return PublicationReview(
        token_id=token_id,
        publication_key="pub-1",
        message_id=77,
        posted_at=datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc),
        text_content="ВАЖНО: тестовый промт",
        media_type="photo",
        media_count=2,
        message_url="https://t.me/example/77",
        post_type=post_type,
        confidence=confidence,
        source=source,
        is_prompt=True,
        hashtags=(("Kael", "kael"),),
    )


class AnalyticsReviewBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_module_uses_only_public_database_boundary(self) -> None:
        source = inspect.getsource(analytics_review)
        self.assertNotIn("._require_pool()", source)
        self.assertEqual(9, source.count("database.acquire()"))

    async def test_unresolved_review_list_preserves_tokens_and_page_clamp(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(side_effect=[10, 77]),
            fetch=AsyncMock(
                return_value=[
                    {
                        "normalized_hashtag": "kael",
                        "hashtag": "Kael",
                        "publication_count": "4",
                        "prompt_count": "3",
                    }
                ]
            ),
        )
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await list_unresolved_tag_reviews(
            database,
            42,
            period="7d",
            page=99,
            page_size=99,
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        self.assertEqual((result.page, result.page_size, result.total_items), (1, 8, 10))
        self.assertEqual(result.items[0].token_id, 77)
        self.assertEqual(result.items[0].normalized_hashtag, "kael")
        self.assertEqual(result.items[0].publication_count, 4)
        count_sql, count_channel, since = connection.fetchval.await_args_list[0].args
        self.assertIn("h.character_id IS NULL", count_sql)
        self.assertEqual(count_channel, 42)
        self.assertIsNotNone(since)
        list_sql, list_channel, list_since, offset, limit = connection.fetch.await_args.args
        self.assertIn("OFFSET $3", list_sql)
        self.assertEqual((list_channel, list_since, offset, limit), (42, since, 8, 8))
        token_sql, token_channel, kind, key = connection.fetchval.await_args_list[1].args
        self.assertIn("analytics_review_items", token_sql)
        self.assertEqual((token_channel, kind, key), (42, "hashtag", "kael"))

    async def test_missing_unresolved_token_returns_none(self) -> None:
        connection = SimpleNamespace(fetchrow=AsyncMock(return_value=None))
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await get_unresolved_tag_review(database, token_id=404)

        self.assertIsNone(result)
        connection.fetchrow.assert_awaited_once()

    async def test_character_picker_preserves_mapping_and_pagination(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=21),
            fetch=AsyncMock(
                return_value=[
                    {
                        "id": "9",
                        "name": "Каэль",
                        "category": "КР",
                        "universe": "Тень",
                        "story_short_label": "Aster",
                    }
                ]
            ),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await list_character_picker(database, page=99, page_size=99)

        self.assertEqual((result.page, result.page_size, result.total_items), (2, 10, 21))
        self.assertEqual(result.items[0].id, 9)
        self.assertEqual(result.items[0].story_short_label, "Aster")
        sql, offset, limit = connection.fetch.await_args.args
        self.assertIn("ORDER BY LOWER(c.name), c.id", sql)
        self.assertEqual((offset, limit), (20, 10))

    async def test_publication_list_preserves_filter_tokens_and_mapping(self) -> None:
        posted_at = datetime(2026, 7, 18, 9, 0, tzinfo=timezone.utc)
        connection = SimpleNamespace(
            fetchval=AsyncMock(side_effect=[9, 501]),
            fetch=AsyncMock(
                return_value=[
                    {
                        "publication_key": "pub-1",
                        "message_id": "77",
                        "posted_at": posted_at,
                        "text_content": "prompt",
                        "media_type": "photo",
                        "message_url": None,
                        "post_type": "unknown",
                        "post_type_confidence": "64",
                        "post_type_source": "automatic",
                        "is_prompt": True,
                        "media_count": "2",
                    }
                ]
            ),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await list_publication_reviews(
            database,
            -1001,
            period="all",
            page=99,
            page_size=99,
            low_confidence_only=True,
        )

        self.assertEqual((result.page, result.page_size, result.total_items), (1, 8, 9))
        item = result.items[0]
        self.assertEqual((item.token_id, item.publication_key), (501, "pub-1"))
        self.assertEqual((item.message_id, item.media_count, item.confidence), (77, 2, 64))
        count_sql = connection.fetchval.await_args_list[0].args[0]
        list_sql, channel_id, since, offset, limit = connection.fetch.await_args.args
        self.assertIn("post_type_confidence < 75", count_sql)
        self.assertIn("post_type_confidence < 75", list_sql)
        self.assertEqual((channel_id, since, offset, limit), (-1001, None, 8, 8))
        token_args = connection.fetchval.await_args_list[1].args
        self.assertEqual(token_args[1:], (-1001, "publication", "pub-1"))

    async def test_publication_detail_preserves_media_and_hashtag_mapping(self) -> None:
        posted_at = datetime(2026, 7, 18, 9, 0, tzinfo=timezone.utc)
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                side_effect=[
                    {"channel_id": "-1001", "item_key": "pub-1"},
                    {
                        "message_id": "77",
                        "posted_at": posted_at,
                        "text_content": None,
                        "media_type": "photo",
                        "message_url": "https://t.me/example/77",
                        "post_type": "prompt",
                        "post_type_confidence": "93",
                        "post_type_source": "manual",
                        "is_prompt": True,
                    },
                ]
            ),
            fetchval=AsyncMock(return_value="3"),
            fetch=AsyncMock(
                return_value=[
                    {"hashtag": "Kael", "normalized_hashtag": "kael"},
                    {"hashtag": "Eric", "normalized_hashtag": "eric"},
                ]
            ),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await get_publication_review(database, token_id=5)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual((result.publication_key, result.media_count), ("pub-1", 3))
        self.assertEqual(result.text_content, "")
        self.assertEqual(result.hashtags, (("Kael", "kael"), ("Eric", "eric")))
        self.assertEqual(connection.fetchrow.await_count, 2)
        self.assertEqual(connection.fetchval.await_count, 1)
        self.assertEqual(connection.fetch.await_count, 1)

    async def test_manual_classification_preserves_transaction_and_audit(self) -> None:
        post_type = "prompt" if "prompt" in POST_TYPE_LABELS else next(iter(POST_TYPE_LABELS))
        before = _publication()
        after = _publication(post_type=post_type, confidence=100, source="manual")
        transaction = _TransactionContext()
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value="-1001"),
            execute=AsyncMock(return_value="UPDATE 2"),
            transaction=Mock(return_value=transaction),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))
        review_mock = AsyncMock(side_effect=[before, after])

        with patch(
            "velvet_bot.analytics_review.get_publication_review",
            new=review_mock,
        ):
            result = await set_manual_publication_type(
                database,
                token_id=5,
                post_type=post_type,
                changed_by=9,
            )

        self.assertEqual(result, after)
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)
        self.assertEqual(connection.execute.await_count, 2)
        audit_sql = connection.execute.await_args_list[0].args[0]
        update_sql, channel_id, publication_key, selected_type = (
            connection.execute.await_args_list[1].args
        )
        self.assertIn("post_classification_changes", audit_sql)
        self.assertIn("post_type_source = 'manual'", update_sql)
        self.assertEqual((channel_id, publication_key, selected_type), (-1001, "pub-1", post_type))
        self.assertEqual(review_mock.await_count, 2)

    async def test_automatic_reset_preserves_classification_transaction(self) -> None:
        before = _publication(post_type="other", confidence=41, source="manual")
        after = _publication(post_type="prompt", confidence=88, source="automatic")
        classification = SimpleNamespace(
            post_type="prompt",
            confidence=88,
            reason="sections detected",
        )
        transaction = _TransactionContext()
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value="-1001"),
            execute=AsyncMock(return_value="UPDATE 2"),
            transaction=Mock(return_value=transaction),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))
        review_mock = AsyncMock(side_effect=[before, after])

        with (
            patch(
                "velvet_bot.analytics_review.get_publication_review",
                new=review_mock,
            ),
            patch(
                "velvet_bot.analytics_review.classify_post",
                new=Mock(return_value=classification),
            ) as classify_mock,
        ):
            result = await reset_publication_type_to_automatic(
                database,
                token_id=5,
                changed_by=9,
            )

        self.assertEqual(result, after)
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)
        self.assertEqual(connection.execute.await_count, 3)
        self.assertIn(
            "post_classification_changes",
            connection.execute.await_args_list[0].args[0],
        )
        self.assertIn(
            "is_prompt = $3",
            connection.execute.await_args_list[1].args[0],
        )
        self.assertIn(
            "post_type_confidence = $4",
            connection.execute.await_args_list[2].args[0],
        )
        classify_mock.assert_called_once_with(
            before.text_content,
            before.hashtags,
            is_prompt=before.is_prompt,
            media_type=before.media_type,
        )

    async def test_batch_reclassification_counts_changed_publications(self) -> None:
        keys_connection = SimpleNamespace(
            fetch=AsyncMock(
                return_value=[
                    {"publication_key": "pub-1"},
                    {"publication_key": "pub-2"},
                ]
            )
        )
        first_token_connection = SimpleNamespace(fetchval=AsyncMock(return_value=11))
        second_token_connection = SimpleNamespace(fetchval=AsyncMock(return_value=12))
        database = SimpleNamespace(
            acquire=Mock(
                side_effect=[
                    _AsyncContext(keys_connection),
                    _AsyncContext(first_token_connection),
                    _AsyncContext(second_token_connection),
                ]
            )
        )
        before_one = _publication(token_id=11, post_type="unknown", confidence=40)
        before_two = _publication(token_id=12, post_type="prompt", confidence=90)
        after_one = _publication(token_id=11, post_type="prompt", confidence=88)
        after_two = _publication(token_id=12, post_type="prompt", confidence=90)
        get_mock = AsyncMock(side_effect=[before_one, before_two])
        reset_mock = AsyncMock(side_effect=[after_one, after_two])

        with (
            patch(
                "velvet_bot.analytics_review.get_publication_review",
                new=get_mock,
            ),
            patch(
                "velvet_bot.analytics_review.reset_publication_type_to_automatic",
                new=reset_mock,
            ),
        ):
            result = await reclassify_automatic_publications(
                database,
                channel_id=-1001,
                changed_by=9,
            )

        self.assertEqual(result, (1, 2))
        self.assertEqual(database.acquire.call_count, 3)
        self.assertEqual(get_mock.await_count, 2)
        self.assertEqual(reset_mock.await_count, 2)
        self.assertEqual(first_token_connection.fetchval.await_args.args[1:], (-1001, "publication", "pub-1"))
        self.assertEqual(second_token_connection.fetchval.await_args.args[1:], (-1001, "publication", "pub-2"))


if __name__ == "__main__":
    unittest.main()
