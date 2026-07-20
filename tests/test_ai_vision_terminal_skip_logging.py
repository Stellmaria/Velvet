from __future__ import annotations

import logging
import unittest

from velvet_bot.app.ai_vision_logging import (
    run_ai_vision_once_with_terminal_skip_info,
)


class AIVisionTerminalSkipLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_oversized_skip_is_downgraded_to_info(self) -> None:
        logger = logging.getLogger("velvet_bot.ai_vision")

        async def runner() -> int:
            logger.warning(
                "AI semantic analysis failed media_id=3366: "
                "Крупное изображение недоступно для AI-анализа media_key=m3366: "
                "file is too big, а Telegram не предоставил доступную миниатюру. "
                "Повтор автоматически не требуется."
            )
            return 0

        with self.assertLogs(logger.name, level="INFO") as captured:
            result = await run_ai_vision_once_with_terminal_skip_info(runner)

        self.assertEqual(result, 0)
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.INFO)

    async def test_unrelated_ai_warning_remains_warning(self) -> None:
        logger = logging.getLogger("velvet_bot.ai_vision")

        async def runner() -> int:
            logger.warning("AI vision service is unavailable")
            return 0

        with self.assertLogs(logger.name, level="INFO") as captured:
            await run_ai_vision_once_with_terminal_skip_info(runner)

        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.WARNING)

    async def test_filter_is_removed_after_iteration(self) -> None:
        logger = logging.getLogger("velvet_bot.ai_vision")

        async def runner() -> int:
            return 0

        await run_ai_vision_once_with_terminal_skip_info(runner)

        with self.assertLogs(logger.name, level="WARNING") as captured:
            logger.warning(
                "AI semantic analysis failed media_id=1: file is too big. "
                "Повтор автоматически не требуется."
            )

        self.assertEqual(captured.records[0].levelno, logging.WARNING)


if __name__ == "__main__":
    unittest.main()
