from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.presentation.telegram.routers.analytics_controllers import channel


class ChannelAnalyticsTimestampBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_unix_timestamp_is_converted_to_aware_utc_datetime(self) -> None:
        result = channel._coerce_telegram_datetime(
            1784921606,
            field_name="date",
        )

        self.assertEqual(
            datetime.fromtimestamp(1784921606, tz=UTC),
            result,
        )
        self.assertIs(UTC, result.tzinfo)

    def test_naive_datetime_is_normalized_to_utc(self) -> None:
        source = datetime(2026, 7, 24, 22, 33, 26)

        result = channel._coerce_telegram_datetime(
            source,
            field_name="date",
        )

        self.assertEqual(source.replace(tzinfo=UTC), result)
        self.assertIs(UTC, result.tzinfo)

    async def test_capture_passes_normalized_dates_to_ingest(self) -> None:
        message = SimpleNamespace(
            chat=SimpleNamespace(id=-1003802812639),
            message_id=608,
            date=1784921606,
            edit_date=1784921614,
        )
        parsed = SimpleNamespace(
            channel_id=message.chat.id,
            message_id=message.message_id,
            prompt=SimpleNamespace(is_prompt=False),
            hashtags=(),
        )

        with patch.object(
            channel,
            "ingest_channel_post",
            new=AsyncMock(return_value=parsed),
        ) as ingest:
            await channel._capture_channel_post(
                message,  # type: ignore[arg-type]
                SimpleNamespace(),  # type: ignore[arg-type]
                frozenset({message.chat.id}),
                None,
            )

        ingest.assert_awaited_once()
        normalized = ingest.await_args.args[1]
        self.assertEqual(
            datetime.fromtimestamp(1784921606, tz=UTC),
            normalized.date,
        )
        self.assertEqual(
            datetime.fromtimestamp(1784921614, tz=UTC),
            normalized.edit_date,
        )
        self.assertEqual(1784921606, message.date)
        self.assertEqual(1784921614, message.edit_date)


if __name__ == "__main__":
    unittest.main()
