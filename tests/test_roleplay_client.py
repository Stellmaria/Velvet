from __future__ import annotations

import unittest
from datetime import datetime, timezone

from velvet_bot.domains.roleplay.client import (
    FailoverRoleplayClient,
    GeneratedRoleplayText,
    RoleplayClientError,
    TextRoleplayClient,
    _extract_chat_completion_text,
    _extract_openai_response_text,
)
from velvet_bot.domains.roleplay.models import RoleplayMessage


def _message(role: str, content: str) -> RoleplayMessage:
    return RoleplayMessage(
        id=1,
        chat_id=10,
        user_id=20,
        role=role,
        content=content,
        created_at=datetime.now(timezone.utc),
    )


class RoleplayResponseParsingTests(unittest.TestCase):
    def test_extracts_openai_output_text_property(self) -> None:
        self.assertEqual(
            _extract_openai_response_text({"output_text": "Ответ GPT"}),
            "Ответ GPT",
        )

    def test_extracts_openai_output_items(self) -> None:
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Первая часть"},
                        {"type": "output_text", "text": "Вторая часть"},
                    ],
                }
            ]
        }
        self.assertEqual(
            _extract_openai_response_text(payload),
            "Первая часть\nВторая часть",
        )

    def test_extracts_chat_completion(self) -> None:
        self.assertEqual(
            _extract_chat_completion_text(
                {"choices": [{"message": {"content": "Ответ"}}]}
            ),
            "Ответ",
        )

    def test_openai_payload_disables_provider_storage(self) -> None:
        client = TextRoleplayClient(
            provider="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-5-mini",
            api_key="test",
            timeout_seconds=30,
            max_output_tokens=900,
        )
        payload = client._openai_responses_body(
            "Инструкция",
            (_message("user", "Реплика"),),
        )
        self.assertFalse(payload["store"])
        self.assertEqual(payload["model"], "gpt-5-mini")
        self.assertEqual(payload["max_output_tokens"], 900)
        self.assertEqual(
            payload["input"],
            [{"role": "user", "content": "Реплика"}],
        )

    def test_rejects_local_ollama_provider(self) -> None:
        with self.assertRaises(ValueError):
            TextRoleplayClient(
                provider="ollama",
                base_url="http://127.0.0.1:11434",
                model="local-model",
                api_key="unused",
                timeout_seconds=30,
                max_output_tokens=900,
            )

    def test_cloud_provider_requires_api_key(self) -> None:
        with self.assertRaises(ValueError):
            TextRoleplayClient(
                provider="openai_compatible",
                base_url="https://byesu.com/v1",
                model="roleplay-model",
                api_key=None,
                timeout_seconds=30,
                max_output_tokens=900,
            )


class _FailingClient:
    async def generate(self, *, instructions: str, messages: object) -> object:
        raise RoleplayClientError("primary failed")


class _WorkingClient:
    async def generate(
        self,
        *,
        instructions: str,
        messages: object,
    ) -> GeneratedRoleplayText:
        return GeneratedRoleplayText(
            text="fallback answer",
            provider="openai_compatible",
            model="cloud-fallback",
        )


class RoleplayFailoverTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_fallback_after_primary_error(self) -> None:
        client = FailoverRoleplayClient(_FailingClient(), _WorkingClient())
        generated = await client.generate(
            instructions="test",
            messages=(_message("user", "hello"),),
        )
        self.assertEqual(generated.text, "fallback answer")
        self.assertEqual(generated.provider, "openai_compatible")
        self.assertEqual(generated.model, "cloud-fallback")


if __name__ == "__main__":
    unittest.main()
