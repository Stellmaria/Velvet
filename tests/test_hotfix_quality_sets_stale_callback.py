from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery

from velvet_bot.handlers import quality_sets


class QualitySetsStaleCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_answer_ignores_only_expired_callback(self) -> None:
        method = AnswerCallbackQuery(callback_query_id="expired")
        callback = SimpleNamespace(
            answer=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=method,
                    message=(
                        "Bad Request: query is too old and response timeout expired "
                        "or query ID is invalid"
                    ),
                )
            )
        )

        answered = await quality_sets._safe_callback_answer(callback)

        self.assertFalse(answered)
        callback.answer.assert_awaited_once_with(text=None, show_alert=False)

    async def test_safe_answer_reraises_unrelated_bad_request(self) -> None:
        method = AnswerCallbackQuery(callback_query_id="active")
        callback = SimpleNamespace(
            answer=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=method,
                    message="Bad Request: BUTTON_DATA_INVALID",
                )
            )
        )

        with self.assertRaises(TelegramBadRequest):
            await quality_sets._safe_callback_answer(callback)

    def test_list_acknowledges_before_expensive_refresh(self) -> None:
        source = inspect.getsource(quality_sets.handle_media_set_list)
        answer_position = source.index("await _safe_callback_answer(callback)")
        refresh_position = source.index("await show_media_set_candidates(")
        self.assertLess(answer_position, refresh_position)

    def test_open_acknowledges_before_sending_previews(self) -> None:
        source = inspect.getsource(quality_sets.handle_media_set_open)
        answer_position = source.index(
            'await _safe_callback_answer(callback, "Открываю материалы…")'
        )
        preview_position = source.index("await _send_candidate_previews(")
        self.assertLess(answer_position, preview_position)


if __name__ == "__main__":
    unittest.main()
