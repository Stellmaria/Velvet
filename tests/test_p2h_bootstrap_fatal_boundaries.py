from __future__ import annotations

import asyncio
import inspect
import unittest

from velvet_bot.app import bootstrap


class RecordingCenter:
    def __init__(self, failure: BaseException | None = None) -> None:
        self.failure = failure
        self.calls = []

    async def report_exception(self, title: str, error: BaseException, **kwargs) -> None:
        self.calls.append((title, error))
        if self.failure is not None:
            raise self.failure


class BootstrapFatalBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_error_is_reported(self) -> None:
        center = RecordingCenter()
        error = RuntimeError("fatal")
        await bootstrap._report_fatal_application_error(center, error)
        self.assertEqual(center.calls[0][1], error)

    async def test_reporting_failure_is_absorbed(self) -> None:
        center = RecordingCenter(RuntimeError("report failed"))
        await bootstrap._report_fatal_application_error(center, ValueError("original"))
        self.assertEqual(len(center.calls), 1)

    async def test_cancellation_is_not_swallowed(self) -> None:
        center = RecordingCenter(asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await bootstrap._report_fatal_application_error(center, RuntimeError("fatal"))

    def test_run_application_reports_before_reraising(self) -> None:
        source = inspect.getsource(bootstrap.run_application)
        marker = "p2-approved-boundary: report-fatal-application-error"
        self.assertIn(marker, source)
        catch = source.index("except Exception as error")
        self.assertLess(
            source.index("await _report_fatal_application_error", catch),
            source.index("        raise\n", catch),
        )


if __name__ == "__main__":
    unittest.main()
