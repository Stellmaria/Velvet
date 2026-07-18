from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import velvet_bot.channel_analytics as channel_analytics
from velvet_bot.channel_analytics import (
    ParsedChannelPost,
    PromptSignals,
    get_channel_overview,
    get_hashtag_stat,
    get_prompt_structure_stats,
    ingest_channel_post,
    list_character_usage_stats,
    list_hashtag_stats,
    list_link_domain_stats,
    list_media_type_stats,
)


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


def _parsed_post() -> ParsedChannelPost:
    posted_at = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    return ParsedChannelPost(
        channel_id=-1001,
        message_id=77,
        publication_key="message:77",
        posted_at=posted_at,
        edited_at=None,
        title="Velvet Anatomy",
        username="velvetAnatomy",
        author_signature="Stellmaria",
        text_content="ВАЖНО:\nСТРОГО:\n#Kael #Unknown https://t.me/example/77",
        media_type="photo",
        media_group_id=None,
        has_spoiler=False,
        view_count=120,
        forward_count=4,
        message_url="https://t.me/velvetAnatomy/77",
        hashtags=(("Kael", "kael"), ("Unknown", "unknown")),
        links=(("https://t.me/example/77", "t.me", True),),
        prompt=PromptSignals(
            is_prompt=True,
            score=6,
            has_important=True,
            has_strict=True,
            has_negative=False,
            has_technical=False,
            has_palette=False,
        ),
    )


class ChannelAnalyticsBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_module_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(channel_analytics)
        self.assertNotIn("._require_pool()", source)
        self.assertEqual(8, source.count("database.acquire()"))

    async def test_ingest_preserves_transaction_and_child_replacement(self) -> None:
        parsed = _parsed_post()
        transaction = _TransactionContext()
        connection = SimpleNamespace(
            execute=AsyncMock(return_value="OK"),
            fetchval=AsyncMock(return_value=501),
            fetch=AsyncMock(
                return_value=[
                    {"id": "9", "name": "Каэль", "normalized_name": "Kael"}
                ]
            ),
            transaction=Mock(return_value=transaction),
        )
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        with patch(
            "velvet_bot.channel_analytics.parse_channel_post",
            new=Mock(return_value=parsed),
        ):
            result = await ingest_channel_post(database, SimpleNamespace())

        self.assertEqual(result, parsed)
        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        self.assertTrue(transaction.entered)
        self.assertTrue(transaction.exited)
        self.assertEqual(connection.fetchval.await_count, 1)
        post_sql = connection.fetchval.await_args.args[0]
        self.assertIn("INSERT INTO channel_posts", post_sql)
        self.assertIn("ON CONFLICT (channel_id, message_id)", post_sql)
        self.assertEqual(connection.fetch.await_args.args[0], "SELECT id, name, normalized_name FROM characters")

        calls = connection.execute.await_args_list
        self.assertEqual(len(calls), 6)
        self.assertIn("INSERT INTO tracked_channels", calls[0].args[0])
        self.assertEqual(calls[1].args, ("DELETE FROM channel_post_hashtags WHERE post_id = $1", 501))
        self.assertEqual(calls[2].args, ("DELETE FROM channel_post_links WHERE post_id = $1", 501))
        self.assertIn("INSERT INTO channel_post_hashtags", calls[3].args[0])
        self.assertEqual(calls[3].args[1:], (501, "Kael", "kael", 9, True))
        self.assertEqual(calls[4].args[1:], (501, "Unknown", "unknown", None, False))
        self.assertIn("INSERT INTO channel_post_links", calls[5].args[0])
        self.assertEqual(calls[5].args[1:], (501, "https://t.me/example/77", "t.me", True))

    async def test_overview_preserves_three_aggregate_queries_and_mapping(self) -> None:
        first = datetime(2026, 7, 1, tzinfo=timezone.utc)
        last = datetime(2026, 7, 18, tzinfo=timezone.utc)
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                side_effect=[
                    {
                        "total_messages": "11",
                        "total_publications": "8",
                        "prompt_publications": "5",
                        "media_messages": "9",
                        "spoiler_messages": "2",
                        "edited_messages": "3",
                        "first_post_at": first,
                        "last_post_at": last,
                        "average_text_length": "842.5",
                        "captured_views": "1200",
                        "captured_forwards": "44",
                    },
                    {
                        "total_hashtag_uses": "27",
                        "unique_hashtags": "12",
                        "unique_characters": "4",
                    },
                    {"total_links": "10", "telegram_links": "7"},
                ]
            )
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await get_channel_overview(database, -1001)

        self.assertEqual(connection.fetchrow.await_count, 3)
        self.assertIn("FROM channel_posts", connection.fetchrow.await_args_list[0].args[0])
        self.assertIn("FROM channel_post_hashtags", connection.fetchrow.await_args_list[1].args[0])
        self.assertIn("FROM channel_post_links", connection.fetchrow.await_args_list[2].args[0])
        self.assertEqual(result.channel_id, -1001)
        self.assertEqual((result.total_messages, result.total_publications), (11, 8))
        self.assertEqual((result.total_hashtag_uses, result.unique_characters), (27, 4))
        self.assertEqual((result.total_links, result.telegram_links), (10, 7))
        self.assertEqual(result.average_text_length, 842.5)
        self.assertEqual((result.first_post_at, result.last_post_at), (first, last))

    async def test_hashtag_list_clamps_limit_and_maps_rows(self) -> None:
        used_at = datetime(2026, 7, 18, tzinfo=timezone.utc)
        connection = SimpleNamespace(
            fetch=AsyncMock(
                return_value=[
                    {
                        "hashtag": "Kael",
                        "normalized_hashtag": "kael",
                        "publication_count": "6",
                        "prompt_count": "5",
                        "last_used_at": used_at,
                        "character_name": "Каэль",
                    }
                ]
            )
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await list_hashtag_stats(
            database,
            -1001,
            limit=999,
            prompt_only=True,
        )

        sql, channel_id, prompt_only, limit = connection.fetch.await_args.args
        self.assertIn("$2::BOOLEAN = FALSE OR p.is_prompt", sql)
        self.assertEqual((channel_id, prompt_only, limit), (-1001, True, 100))
        self.assertEqual(result[0].normalized_hashtag, "kael")
        self.assertEqual((result[0].publication_count, result[0].prompt_count), (6, 5))
        self.assertEqual(result[0].character_name, "Каэль")

    async def test_hashtag_detail_normalizes_input_and_handles_missing_row(self) -> None:
        connection = SimpleNamespace(fetchrow=AsyncMock(return_value=None))
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await get_hashtag_stat(database, -1001, " #KAEL ")

        self.assertIsNone(result)
        sql, channel_id, normalized = connection.fetchrow.await_args.args
        self.assertIn("h.normalized_hashtag = $2", sql)
        self.assertEqual((channel_id, normalized), (-1001, "kael"))

    async def test_character_usage_preserves_story_mapping_and_limit_clamp(self) -> None:
        connection = SimpleNamespace(
            fetch=AsyncMock(
                return_value=[
                    {
                        "character_id": "9",
                        "name": "Каэль",
                        "category": "КР",
                        "universe": "Тень",
                        "story_short_label": "Aster",
                        "story_title": "Берлин",
                        "publication_count": "7",
                        "prompt_count": "6",
                        "last_used_at": None,
                    }
                ]
            )
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await list_character_usage_stats(database, -1001, limit=0)

        sql, channel_id, limit = connection.fetch.await_args.args
        self.assertIn("LEFT JOIN character_stories", sql)
        self.assertEqual((channel_id, limit), (-1001, 1))
        self.assertEqual(result[0].character_id, 9)
        self.assertEqual((result[0].publication_count, result[0].prompt_count), (7, 6))
        self.assertEqual((result[0].story_short_label, result[0].story_title), ("Aster", "Берлин"))

    async def test_prompt_structure_preserves_numeric_mapping(self) -> None:
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "prompt_publications": "8",
                    "with_important": "7",
                    "with_strict": "6",
                    "with_negative": "5",
                    "with_technical": "4",
                    "with_palette": "3",
                    "average_prompt_length": "950.25",
                }
            )
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await get_prompt_structure_stats(database, -1001)

        self.assertEqual(result.prompt_publications, 8)
        self.assertEqual((result.with_important, result.with_strict), (7, 6))
        self.assertEqual((result.with_negative, result.with_technical, result.with_palette), (5, 4, 3))
        self.assertEqual(result.average_prompt_length, 950.25)

    async def test_named_count_queries_preserve_mapping_and_link_limit(self) -> None:
        media_connection = SimpleNamespace(
            fetch=AsyncMock(return_value=[{"name": "photo", "count": "12"}])
        )
        link_connection = SimpleNamespace(
            fetch=AsyncMock(return_value=[{"name": "t.me", "count": "9"}])
        )
        database = SimpleNamespace(
            acquire=Mock(
                side_effect=[
                    _AsyncContext(media_connection),
                    _AsyncContext(link_connection),
                ]
            )
        )

        media = await list_media_type_stats(database, -1001)
        links = await list_link_domain_stats(database, -1001, limit=999)

        self.assertEqual((media[0].name, media[0].count), ("photo", 12))
        self.assertEqual((links[0].name, links[0].count), ("t.me", 9))
        media_sql, media_channel = media_connection.fetch.await_args.args
        link_sql, link_channel, link_limit = link_connection.fetch.await_args.args
        self.assertIn("GROUP BY media_type", media_sql)
        self.assertIn("GROUP BY l.domain", link_sql)
        self.assertEqual(media_channel, -1001)
        self.assertEqual((link_channel, link_limit), (-1001, 50))


if __name__ == "__main__":
    unittest.main()
