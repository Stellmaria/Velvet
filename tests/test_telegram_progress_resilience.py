from __future__ import annotations

import unittest
from unittest.mock import patch

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage

import velvet_bot.app.telegram_progress_resilience as progress
from velvet_bot.domains.media_generation.friendly_worker import (
    FriendlyKieGenerationWorker,
)


class TelegramProgressResilienceTests(unittest.TestCase):
    def test_unsafe_model_chatter_is_not_a_provider_diagnostic(self) -> None:
        self.assertIsNone(
            progress._provider_reason_without_unsafe_chatter(
                "Извините, но я не могу создавать небезопасные изображения."
            )
        )
        self.assertEqual(
            "IMAGE_SAFETY",
            progress._provider_reason_without_unsafe_chatter("IMAGE_SAFETY"),
        )

    def test_transient_disconnect_is_logged_as_warning(self) -> None:
        error = TelegramNetworkError(
            method=SendMessage(chat_id=1, text="progress"),
            message="ServerDisconnectedError: Server disconnected",
        )

        with self.assertLogs(progress.logger, level="WARNING") as captured:
            progress._log_transient_progress_failure("task-1", error)

        output = "\n".join(captured.output)
        self.assertIn("generation continues", output)
        self.assertNotIn("Traceback", output)

    def test_installer_binds_only_canonical_worker_progress(self) -> None:
        previous_installed = progress._INSTALLED
        previous_method = FriendlyKieGenerationWorker._publish_progress
        progress._INSTALLED = False
        try:
            with patch.object(
                FriendlyKieGenerationWorker,
                "_publish_progress",
                previous_method,
            ):
                progress.install_telegram_progress_resilience()
                self.assertIs(
                    FriendlyKieGenerationWorker._publish_progress,
                    progress._publish_progress_resilient,
                )
                progress.install_telegram_progress_resilience()
                self.assertIs(
                    FriendlyKieGenerationWorker._publish_progress,
                    progress._publish_progress_resilient,
                )
        finally:
            progress._INSTALLED = previous_installed


if __name__ == "__main__":
    unittest.main()
