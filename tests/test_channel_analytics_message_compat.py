from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from velvet_bot import channel_analytics
from velvet_bot.presentation.telegram.routers import analytics_controllers  # noqa: F401


class ChannelAnalyticsMessageCompatibilityTests(unittest.TestCase):
    @staticmethod
    def _message(**metrics):
        payload = {
            "text": "#Каэль",
            "caption": None,
            "media_group_id": None,
            "message_id": 77,
            "date": datetime(2026, 7, 23, 1, 18, tzinfo=UTC),
            "edit_date": None,
            "author_signature": "Velvet",
            "has_media_spoiler": False,
            "photo": [object()],
            "chat": SimpleNamespace(
                id=-1003802812639,
                title="Velvet Anatomy",
                username="velvetAnatomy",
            ),
        }
        payload.update(metrics)
        return SimpleNamespace(**payload)

    def test_bot_api_message_without_view_fields_is_ingested(self) -> None:
        parsed = channel_analytics.parse_channel_post(self._message())

        self.assertIsNone(parsed.view_count)
        self.assertIsNone(parsed.forward_count)
        self.assertEqual(77, parsed.message_id)
        self.assertEqual("photo", parsed.media_type)

    def test_imported_metrics_are_preserved_when_available(self) -> None:
        parsed = channel_analytics.parse_channel_post(
            self._message(views="125", forward_count=4)
        )

        self.assertEqual(125, parsed.view_count)
        self.assertEqual(4, parsed.forward_count)


if __name__ == "__main__":
    unittest.main()
