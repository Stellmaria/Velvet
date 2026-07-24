# Channel analytics timestamp normalization

Date: 2026-07-24
Status: completed

## Incident

Channel analytics failed while inserting a channel post because Telegram supplied
`message.date` / `message.edit_date` as Unix timestamp integers. The analytics SQL
passes those values to `TIMESTAMPTZ` parameters, and asyncpg correctly rejected an
`int` instead of pretending the type mismatch was charming.

Observed values included:

- `1784921606`;
- `1784921614`.

## Root cause

`_capture_channel_post` forwarded the Telegram `Message` directly to
`ingest_channel_post`. The normal aiogram model contract exposes aware `datetime`
objects, but the production update path can contain raw Unix timestamps. There was
no normalization at the Telegram-to-analytics boundary.

## Change

`analytics_controllers/channel.py` now:

- converts integer or float Unix timestamps with `datetime.fromtimestamp(..., tz=UTC)`;
- assigns UTC to naive `datetime` values;
- preserves already timezone-aware values;
- creates a copied message before passing normalized dates to analytics ingest;
- rejects unsupported timestamp types with an explicit `TypeError` that is handled by
  the existing audit boundary.

Both original and edited channel posts use the same `_capture_channel_post` path, so
the correction covers `date` and `edit_date` consistently.

## Regression coverage

`tests/test_channel_analytics_timestamp_boundary.py` verifies:

- the exact production Unix timestamp converts to aware UTC;
- naive datetimes receive UTC;
- ingest receives normalized `date` and `edit_date` values;
- the original Telegram message object is not mutated.

## Compatibility

No migration is required. SQL, channel analytics data shape, commands, router order and
audit reporting are unchanged.
