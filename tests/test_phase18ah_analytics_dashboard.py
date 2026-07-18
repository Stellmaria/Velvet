from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import velvet_bot.analytics_dashboard as dashboard_module
from velvet_bot.analytics_dashboard import (
    DashboardOverview,
    DashboardPage,
    DashboardRankItem,
    DiscussionDashboard,
    DiscussionSource,
    PromptDashboard,
    get_dashboard_overview,
    get_discussion_dashboard,
    get_prompt_dashboard,
    list_character_dashboard,
    list_discussion_participants,
    list_discussion_sources,
    list_hashtag_dashboard,
    list_post_type_dashboard,
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


def _database(connection):
    context = _AsyncContext(connection)
    return SimpleNamespace(acquire=Mock(return_value=context)), context


class AnalyticsDashboardBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_module_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(dashboard_module)
        self.assertNotIn("._require_pool()", source)
        self.assertEqual(8, source.count("database.acquire()"))

    async def test_overview_preserves_two_query_mapping(self) -> None:
        since = datetime(2026, 7, 11, tzinfo=timezone.utc)
        first = datetime(2026, 1, 1, tzinfo=timezone.utc)
        last = datetime(2026, 7, 18, tzinfo=timezone.utc)
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                side_effect=[
                    {
                        "total_messages": "12",
                        "total_publications": 7,
                        "prompt_publications": 5,
                        "media_messages": 9,
                        "spoiler_messages": 2,
                        "edited_messages": 3,
                        "total_reactions": 44,
                        "captured_views": 1000,
                        "captured_forwards": 20,
                        "average_text_length": "321.5",
                        "first_post_at": first,
                        "last_post_at": last,
                    },
                    {"unique_characters": 6, "unique_hashtags": 18},
                ]
            )
        )
        database, context = _database(connection)

        with patch("velvet_bot.analytics_dashboard.period_since", return_value=since):
            result = await get_dashboard_overview(database, -10042, period="7d")

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        self.assertEqual(connection.fetchrow.await_count, 2)
        overview_sql, channel_id, overview_since = connection.fetchrow.await_args_list[0].args
        relation_sql, relation_channel_id, relation_since = connection.fetchrow.await_args_list[1].args
        self.assertIn("FROM channel_posts", overview_sql)
        self.assertIn("FROM channel_post_hashtags AS h", relation_sql)
        self.assertEqual((channel_id, overview_since), (-10042, since))
        self.assertEqual((relation_channel_id, relation_since), (-10042, since))
        self.assertEqual(
            result,
            DashboardOverview(
                channel_id=-10042,
                total_messages=12,
                total_publications=7,
                prompt_publications=5,
                media_messages=9,
                spoiler_messages=2,
                edited_messages=3,
                unique_characters=6,
                unique_hashtags=18,
                total_reactions=44,
                captured_views=1000,
                captured_forwards=20,
                average_text_length=321.5,
                first_post_at=first,
                last_post_at=last,
            ),
        )

    async def test_prompt_dashboard_preserves_metric_mapping(self) -> None:
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "total": 8,
                    "with_important": 7,
                    "with_strict": 6,
                    "with_negative": 5,
                    "with_technical": 4,
                    "with_palette": 3,
                    "average_length": "2048.25",
                }
            )
        )
        database, _ = _database(connection)

        with patch("velvet_bot.analytics_dashboard.period_since", return_value=None):
            result = await get_prompt_dashboard(database, 42, period="all")

        sql, channel_id, since = connection.fetchrow.await_args.args
        self.assertIn("has_important_section", sql)
        self.assertIn("has_palette", sql)
        self.assertEqual((channel_id, since), (42, None))
        self.assertEqual(result, PromptDashboard(8, 7, 6, 5, 4, 3, 2048.25))

    async def test_hashtag_page_preserves_filter_clamp_and_mapping(self) -> None:
        since = datetime(2026, 6, 18, tzinfo=timezone.utc)
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=21),
            fetch=AsyncMock(
                return_value=[
                    {
                        "normalized_hashtag": "каэль",
                        "hashtag": "Каэль",
                        "publication_count": 11,
                        "prompt_count": 9,
                        "character_name": "Каэль Лэнг",
                    }
                ]
            ),
        )
        database, _ = _database(connection)

        with patch("velvet_bot.analytics_dashboard.period_since", return_value=since):
            result = await list_hashtag_dashboard(
                database,
                42,
                period="30d",
                page=99,
                page_size=20,
                unresolved_only=True,
            )

        count_sql, count_channel_id, count_since = connection.fetchval.await_args.args
        list_sql, list_channel_id, list_since, offset, limit = connection.fetch.await_args.args
        self.assertIn("AND h.character_id IS NULL", count_sql)
        self.assertIn("AND h.character_id IS NULL", list_sql)
        self.assertEqual((count_channel_id, count_since), (42, since))
        self.assertEqual((list_channel_id, list_since, offset, limit), (42, since, 20, 10))
        self.assertEqual(
            result,
            DashboardPage(
                items=[DashboardRankItem("каэль", "#Каэль", 11, 9, "Каэль Лэнг")],
                page=2,
                page_size=10,
                total_items=21,
            ),
        )

    async def test_character_page_preserves_detail_and_minimum_page_size(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=1),
            fetch=AsyncMock(
                return_value=[
                    {
                        "id": 7,
                        "name": "Эрик",
                        "category": "Original",
                        "universe": None,
                        "short_label": "Walter",
                        "publication_count": 4,
                        "prompt_count": 3,
                    }
                ]
            ),
        )
        database, _ = _database(connection)

        with patch("velvet_bot.analytics_dashboard.period_since", return_value=None):
            result = await list_character_dashboard(
                database,
                42,
                period="all",
                page=-2,
                page_size=0,
            )

        _, channel_id, since, offset, limit = connection.fetch.await_args.args
        self.assertEqual((channel_id, since, offset, limit), (42, None, 0, 1))
        self.assertEqual(
            result.items,
            [DashboardRankItem("7", "Эрик", 4, 3, "Original / Walter")],
        )
        self.assertEqual((result.page, result.page_size, result.total_items), (0, 1, 1))

    async def test_post_types_and_discussion_sources_preserve_mapping(self) -> None:
        post_connection = SimpleNamespace(
            fetch=AsyncMock(
                return_value=[
                    {
                        "post_type": "prompt",
                        "publication_count": 12,
                        "average_confidence": 88,
                    }
                ]
            )
        )
        post_database, _ = _database(post_connection)
        with patch("velvet_bot.analytics_dashboard.period_since", return_value=None):
            post_result = await list_post_type_dashboard(
                post_database,
                42,
                period="all",
            )
        self.assertEqual(post_result, [DashboardRankItem("prompt", "prompt", 12, 88)])

        source_connection = SimpleNamespace(
            fetch=AsyncMock(return_value=[{"chat_id": "-1009", "title": "Lounge"}])
        )
        source_database, _ = _database(source_connection)
        source_result = await list_discussion_sources(
            source_database,
            parent_channel_id=-10042,
        )
        source_sql, parent_channel_id = source_connection.fetch.await_args.args
        self.assertIn("source_kind = 'discussion'", source_sql)
        self.assertEqual(parent_channel_id, -10042)
        self.assertEqual(source_result, [DiscussionSource(-1009, "Lounge")])

    async def test_discussion_dashboard_preserves_missing_source_fallback(self) -> None:
        connection = SimpleNamespace(fetchrow=AsyncMock(return_value=None))
        database, _ = _database(connection)

        with patch("velvet_bot.analytics_dashboard.period_since", return_value=None):
            result = await get_discussion_dashboard(database, -1009, period="all")

        self.assertEqual(
            result,
            DiscussionDashboard(
                chat_id=-1009,
                title="-1009",
                total_messages=0,
                unique_participants=0,
                reply_messages=0,
                media_messages=0,
                spoiler_messages=0,
                prompt_messages=0,
                total_reactions=0,
                first_message_at=None,
                last_message_at=None,
            ),
        )

    async def test_discussion_participants_preserve_page_clamp_and_mapping(self) -> None:
        since = datetime(2026, 7, 11, tzinfo=timezone.utc)
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=17),
            fetch=AsyncMock(
                return_value=[
                    {
                        "sender_id": "7221553045",
                        "sender_name": "Stellmaria",
                        "message_count": 30,
                        "reply_count": 12,
                    }
                ]
            ),
        )
        database, _ = _database(connection)

        with patch("velvet_bot.analytics_dashboard.period_since", return_value=since):
            result = await list_discussion_participants(
                database,
                -1009,
                period="7d",
                page=9,
                page_size=8,
            )

        _, chat_id, query_since, offset, limit = connection.fetch.await_args.args
        self.assertEqual((chat_id, query_since, offset, limit), (-1009, since, 16, 8))
        self.assertEqual(
            result,
            DashboardPage(
                items=[DashboardRankItem("7221553045", "Stellmaria", 30, 12)],
                page=2,
                page_size=8,
                total_items=17,
            ),
        )


if __name__ == "__main__":
    unittest.main()
