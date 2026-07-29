from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from velvet_bot.app.channel_analytics_datetime_compat import (
    _normalize_telegram_datetime,
    _parse_channel_post_with_normalized_dates,
)


def _message(*, date_value: object, edit_date_value: object) -> SimpleNamespace:
    return SimpleNamespace(
        text="ВАЖНО:\nСТРОГО:\n#Kael",
        caption=None,
        media_group_id=None,
        message_id=77,
        date=date_value,
        edit_date=edit_date_value,
        author_signature="Stellmaria",
        views=120,
        forward_count=4,
        chat=SimpleNamespace(
            id=-1001,
            title="Velvet Anatomy",
            username="velvetAnatomy",
        ),
    )


class ChannelAnalyticsDatetimeCompatTests(unittest.TestCase):
    def test_epoch_dates_are_normalized_before_database_ingest(self) -> None:
        posted_timestamp = 1785345000
        edited_timestamp = 1785345156

        parsed = _parse_channel_post_with_normalized_dates(
            _message(
                date_value=posted_timestamp,
                edit_date_value=edited_timestamp,
            )
        )

        self.assertEqual(
            datetime.fromtimestamp(posted_timestamp, tz=timezone.utc),
            parsed.posted_at,
        )
        self.assertEqual(
            datetime.fromtimestamp(edited_timestamp, tz=timezone.utc),
            parsed.edited_at,
        )

    def test_existing_datetime_values_are_preserved(self) -> None:
        posted_at = datetime(2026, 7, 29, 17, 0, tzinfo=timezone.utc)
        edited_at = datetime(2026, 7, 29, 17, 5, tzinfo=timezone.utc)

        parsed = _parse_channel_post_with_normalized_dates(
            _message(date_value=posted_at, edit_date_value=edited_at)
        )

        self.assertIs(posted_at, parsed.posted_at)
        self.assertIs(edited_at, parsed.edited_at)

    def test_boolean_is_not_accepted_as_timestamp(self) -> None:
        with self.assertRaisesRegex(TypeError, "boolean"):
            _normalize_telegram_datetime(
                True,
                field_name="edit_date",
                required=False,
            )


if __name__ == "__main__":
    unittest.main()
