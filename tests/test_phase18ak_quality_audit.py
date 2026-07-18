from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import velvet_bot.quality_audit as quality_audit
from velvet_bot.quality_audit import (
    STORY_REQUIRED_UNIVERSES,
    list_character_issues,
    list_unresolved_hashtags,
    reset_broken_file_checks,
)
from velvet_bot.quality_set_audit_compat import (
    _ORIGINAL_GET_QUALITY_SUMMARY as get_quality_summary,
    _ORIGINAL_LIST_MEDIA_ISSUES as list_media_issues,
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


class QualityAuditBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_module_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(quality_audit)
        self.assertNotIn("._require_pool()", source)
        self.assertEqual(5, source.count("database.acquire()"))

    async def test_summary_preserves_all_counters_and_problem_total(self) -> None:
        row = {
            "pending_duplicates": "1",
            "confirmed_duplicates": "2",
            "pending_scans": "3",
            "scan_errors": "4",
            "broken_files": "5",
            "unchecked_files": "6",
            "missing_category": "7",
            "missing_universe": "8",
            "missing_story": "9",
            "empty_characters": "10",
            "media_without_prompt": "11",
            "orphan_media": "12",
            "unresolved_hashtags": "13",
        }
        connection = SimpleNamespace(fetchrow=AsyncMock(return_value=row))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))

        result = await get_quality_summary(database)

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        sql, universes = connection.fetchrow.await_args.args
        self.assertIn("character_story_links", sql)
        self.assertEqual(universes, list(STORY_REQUIRED_UNIVERSES))
        self.assertEqual(result.pending_duplicates, 1)
        self.assertEqual(result.confirmed_duplicates, 2)
        self.assertEqual(result.unresolved_hashtags, 13)
        self.assertEqual(result.total_problems, 80)

    async def test_character_issue_missing_story_preserves_dynamic_positions(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=23),
            fetch=AsyncMock(
                return_value=[
                    {
                        "id": "9",
                        "name": "Каэль",
                        "category": "мужская",
                        "universe": "kr",
                        "media_count": "4",
                    }
                ]
            ),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await list_character_issues(
            database,
            "missing_story",
            page=99,
            page_size=99,
        )

        count_sql, universes = connection.fetchval.await_args.args
        self.assertIn("c.universe = ANY($1::TEXT[])", count_sql)
        self.assertEqual(universes, list(STORY_REQUIRED_UNIVERSES))
        list_sql, list_universes, offset, limit = connection.fetch.await_args.args
        self.assertIn("OFFSET $2 LIMIT $3", list_sql)
        self.assertEqual(list_universes, list(STORY_REQUIRED_UNIVERSES))
        self.assertEqual((offset, limit), (20, 10))
        self.assertEqual((result.page, result.page_size, result.total_items), (2, 10, 23))
        self.assertEqual(result.items[0].character_id, 9)
        self.assertIn("материалов: 4", result.items[0].detail)

    async def test_media_issue_preserves_error_priority_and_offset_mapping(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=11),
            fetch=AsyncMock(
                return_value=[
                    {
                        "character_id": "9",
                        "character_name": "Каэль",
                        "category": "мужская",
                        "media_id": "77",
                        "file_name": "kael.webp",
                        "media_type": "photo",
                        "visual_scan_error": "vision failed",
                        "error_text": "file broken",
                        "media_offset": "3",
                    }
                ]
            ),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await list_media_issues(
            database,
            "broken_files",
            page=99,
            page_size=99,
        )

        self.assertIn("fc.status = 'broken'", connection.fetchval.await_args.args[0])
        list_sql, offset, limit = connection.fetch.await_args.args
        self.assertIn("AS media_offset", list_sql)
        self.assertEqual((offset, limit), (10, 10))
        item = result.items[0]
        self.assertEqual((item.media_id, item.media_offset), (77, 3))
        self.assertEqual(item.character_id, 9)
        self.assertEqual(item.label, "Каэль · kael.webp")
        self.assertEqual(item.detail, "vision failed")

    async def test_unresolved_hashtags_preserve_page_ids_and_mapping(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=12),
            fetch=AsyncMock(
                return_value=[
                    {"normalized_hashtag": "kael", "hashtag": "Kael", "use_count": "6"},
                    {"normalized_hashtag": "eric", "hashtag": "Eric", "use_count": "4"},
                ]
            ),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await list_unresolved_hashtags(database, page=1, page_size=5)

        sql, offset, limit = connection.fetch.await_args.args
        self.assertIn("GROUP BY normalized_hashtag", sql)
        self.assertEqual((offset, limit), (5, 5))
        self.assertEqual((result.page, result.page_size, result.total_items), (1, 5, 12))
        self.assertEqual([item.id for item in result.items], [6, 7])
        self.assertEqual(result.items[0].label, "#Kael")
        self.assertEqual(result.items[0].detail, "использований: 6")

    async def test_reset_broken_checks_preserves_affected_row_mapping(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 17"))
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await reset_broken_file_checks(database)

        self.assertEqual(result, 17)
        sql = connection.execute.await_args.args[0]
        self.assertIn("SET status = 'unknown'", sql)
        self.assertIn("WHERE status = 'broken'", sql)

    async def test_invalid_sections_fail_before_database_access(self) -> None:
        database = SimpleNamespace(acquire=Mock())

        with self.assertRaisesRegex(ValueError, "раздел персонажей"):
            await list_character_issues(database, "not-a-section")
        with self.assertRaisesRegex(ValueError, "раздел медиа"):
            await list_media_issues(database, "not-a-section")

        database.acquire.assert_not_called()


if __name__ == "__main__":
    unittest.main()
