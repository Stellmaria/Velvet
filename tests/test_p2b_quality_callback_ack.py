from __future__ import annotations

import inspect
import unittest

import velvet_bot.handlers.quality_ai as quality_ai
import velvet_bot.handlers.quality_center as quality_center
import velvet_bot.handlers.quality_operations as quality_operations


class QualityCallbackAcknowledgmentTests(unittest.TestCase):
    def assert_ack_between(self, function, mutation: str, reload_call: str) -> None:
        source = inspect.getsource(function)
        self.assertLess(source.index(mutation), source.index("await callback.answer("))
        self.assertLess(source.index("await callback.answer("), source.index(reload_call))

    def test_retry_ack_precedes_list_reload(self) -> None:
        self.assert_ack_between(
            quality_ai.handle_quality_ai_retry,
            "await AIQualityRepository(database).retry(",
            "await _show_list(",
        )

    def test_reset_callbacks_ack_before_section_reload(self) -> None:
        self.assert_ack_between(
            quality_center.handle_retry_scans,
            "await reset_failed_scans(",
            "await _show_section(",
        )
        self.assert_ack_between(
            quality_center.handle_retry_broken,
            "await reset_broken_file_checks(",
            "await _show_section(",
        )

    def test_queue_callbacks_ack_before_menu_reload(self) -> None:
        self.assert_ack_between(
            quality_operations.handle_quality_recent,
            "await QualityOperationsRepository(database).enqueue_recent(",
            "await _show_menu(",
        )
        self.assert_ack_between(
            quality_operations.handle_quality_retry_errors,
            "await QualityOperationsRepository(database).retry_errors(",
            "await _show_menu(",
        )


if __name__ == "__main__":
    unittest.main()
