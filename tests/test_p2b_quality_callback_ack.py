from __future__ import annotations

import inspect
import unittest

import velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_ai as quality_ai
import velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_center as quality_center
import velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_operations as quality_operations


class QualityCallbackAcknowledgmentTests(unittest.TestCase):
    def assert_ack_between(self, function, mutation: str, reload_call: str) -> None:
        source = inspect.getsource(function)
        mutation_index = source.index(mutation)
        ack_index = source.index("await callback.answer(", mutation_index)
        reload_index = source.index(reload_call, mutation_index)
        self.assertLess(mutation_index, ack_index)
        self.assertLess(ack_index, reload_index)

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

    def test_queue_plan_callbacks_ack_before_plan_render(self) -> None:
        self.assert_ack_between(
            quality_operations.handle_quality_recent,
            "await QualityOperationsRepository(database).plan_recent(",
            "await safe_edit_message_text(",
        )
        self.assert_ack_between(
            quality_operations.handle_quality_retry_errors,
            "await QualityOperationsRepository(database).plan_errors(",
            "await safe_edit_message_text(",
        )

    def test_plan_start_ack_precedes_menu_reload(self) -> None:
        self.assert_ack_between(
            quality_operations.handle_quality_plan_start,
            "await QualityOperationsRepository(database).start_plan(",
            "await _show_menu(",
        )


if __name__ == "__main__":
    unittest.main()
