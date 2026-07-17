import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest

import velvet_bot.analytics_review as analytics_review
from velvet_bot.media_quality import MediaScanTarget
from velvet_bot.runtime_log_hotfixes import (
    decide_duplicate_candidate,
    scan_media_target,
    set_manual_publication_type,
)


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Connection:
    def __init__(self):
        self.executed = []
        self.fetchval_calls = []

    def transaction(self):
        return _AsyncContext(self)

    async def fetchval(self, query, *args):
        self.fetchval_calls.append((query, args))
        if "SELECT channel_id" in query:
            return 123
        return 1

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "UPDATE 1"


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _AsyncContext(self.connection)


class _Database:
    def __init__(self):
        self.connection = _Connection()
        self.pool = _Pool(self.connection)

    def acquire(self):
        return self.pool.acquire()

    def _require_pool(self):
        return self.pool


class RuntimeLogHotfixTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_decision_uses_explicit_postgres_types(self):
        database = _Database()

        updated = await decide_duplicate_candidate(
            database,
            17,
            status="confirmed",
            decided_by=7221553045,
        )

        self.assertTrue(updated)
        query = database.connection.fetchval_calls[-1][0]
        self.assertIn("$2::VARCHAR", query)
        self.assertIn("NULL::BIGINT", query)
        self.assertIn("$3::BIGINT", query)

    async def test_manual_publication_type_uses_one_type_for_parameter(self):
        database = _Database()
        item = SimpleNamespace(
            publication_key="channel:message",
            post_type="unknown",
            confidence=40,
            source="automatic",
        )

        with patch.object(
            analytics_review,
            "get_publication_review",
            AsyncMock(side_effect=[item, item]),
        ), patch.object(
            analytics_review,
            "_record_classification_change",
            AsyncMock(),
        ):
            result = await set_manual_publication_type(
                database,
                token_id=9,
                post_type="prompt",
                changed_by=7221553045,
            )

        self.assertIs(result, item)
        query = database.connection.executed[-1][0]
        self.assertIn("post_type = $3::VARCHAR", query)
        self.assertIn("$3::VARCHAR = 'prompt'::VARCHAR", query)
        self.assertIn("publication_key = $2::VARCHAR", query)

    async def test_oversized_file_is_skipped_without_marking_it_broken(self):
        database = _Database()
        bot = SimpleNamespace(
            download=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=None,
                    message="file is too big",
                )
            )
        )
        target = MediaScanTarget(
            media_id=587,
            telegram_file_id="large-file-id",
            display_name="large.png",
        )

        await scan_media_target(bot, database, target)

        queries = [query for query, _ in database.connection.executed]
        self.assertTrue(any("visual_scan_status = 'error'" in query for query in queries))
        self.assertFalse(any("INSERT INTO media_file_checks" in query for query in queries))


if __name__ == "__main__":
    unittest.main()
