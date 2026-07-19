from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, SendMessage

from velvet_bot import analytics_review
from velvet_bot.domains.characters.service import CharacterDirectoryService
from velvet_bot.presentation.telegram.routers.analytics_controllers import review_query_runtime
from velvet_bot.protected_bot import is_expired_callback_answer


class RuntimeErrorHotfixTests(unittest.IsolatedAsyncioTestCase):
    async def test_directory_normalizes_human_category_from_callback(self) -> None:
        expected = SimpleNamespace(category="male")
        repository = SimpleNamespace(list_directory=AsyncMock(return_value=expected))
        service = CharacterDirectoryService(repository)

        result = await service.list_directory(
            category="Мужской",
            page=2,
            public_only=False,
        )

        self.assertIs(result, expected)
        self.assertEqual(
            repository.list_directory.await_args.kwargs["category"],
            "male",
        )

    def test_only_expired_callback_answers_are_suppressed(self) -> None:
        callback_method = AnswerCallbackQuery(callback_query_id="expired")
        expired = TelegramBadRequest(
            method=callback_method,
            message=(
                "Bad Request: query is too old and response timeout expired "
                "or query ID is invalid"
            ),
        )
        self.assertTrue(is_expired_callback_answer(callback_method, expired))

        other_callback_error = TelegramBadRequest(
            method=callback_method,
            message="Bad Request: button text is invalid",
        )
        self.assertFalse(
            is_expired_callback_answer(callback_method, other_callback_error)
        )

        send_method = SendMessage(chat_id=1, text="test")
        send_error = TelegramBadRequest(
            method=send_method,
            message="Bad Request: query is too old",
        )
        self.assertFalse(is_expired_callback_answer(send_method, send_error))

    def test_corrected_publication_query_is_installed(self) -> None:
        self.assertIs(
            analytics_review.list_publication_reviews,
            review_query_runtime.list_publication_reviews,
        )
        source = inspect.getsource(review_query_runtime.list_publication_reviews)
        representative_select = source.split(
            "SELECT DISTINCT ON (publication_key)",
            1,
        )[1].split("FROM channel_posts", 1)[0]
        self.assertIn("text_length", representative_select)
        self.assertIn("id", representative_select)
        self.assertIn(
            "ORDER BY publication_key, text_length DESC, id",
            source,
        )


if __name__ == "__main__":
    unittest.main()
