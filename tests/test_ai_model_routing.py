from __future__ import annotations

import json
import unittest
import urllib.request
from unittest.mock import patch

from velvet_bot.ai_vision import VisionClient
from velvet_bot.infrastructure.ai_model_routing import clear_ai_model_cache


class DummyVisionClient(VisionClient):
    pass


class DummyTextClient(VisionClient):
    ai_task_profile = "text"


class DummyCascadeClient(VisionClient):
    ai_task_profile = "cascade"


def _request(base_url: str, model: str) -> urllib.request.Request:
    return urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps({"model": model, "messages": []}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )


class AIModelRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_ai_model_cache()

    def tearDown(self) -> None:
        clear_ai_model_cache()

    def test_vision_route_skips_models_missing_from_ollama_api(self) -> None:
        environment = {
            "AI_VISION_MODEL": "vision-standard",
            "AI_VISION_COMPARE_MODEL": "vision-uncensored",
            "AI_VISION_FALLBACK_MODEL": "vision-fallback",
        }
        with patch.dict("os.environ", environment, clear=False):
            client = DummyVisionClient(
                provider="ollama",
                base_url="http://127.0.0.1:11435",
                model="vision-standard",
                api_key=None,
                timeout_seconds=120,
            )

        requested: list[str] = []

        def fake_read(request: urllib.request.Request, *, timeout: int):
            self.assertGreaterEqual(timeout, 1)
            if request.full_url.endswith("/api/tags"):
                return {"models": [{"name": "vision-uncensored"}]}
            payload = json.loads((request.data or b"{}").decode("utf-8"))
            requested.append(str(payload["model"]))
            return {"message": {"content": "{}"}}

        with patch.object(VisionClient, "_read_json", side_effect=fake_read):
            from velvet_bot.infrastructure.ai_model_routing import routed_read_json
            result = routed_read_json(
                client,
                _request(client.base_url, client.model),
                timeout=120,
            )

        self.assertEqual({"message": {"content": "{}"}}, result)
        self.assertEqual(["vision-uncensored"], requested)
        self.assertEqual("vision-uncensored", client.model)

    def test_text_client_uses_text_provider_model_and_timeout(self) -> None:
        environment = {
            "AI_VISION_MODEL": "vision-standard",
            "AI_VISION_COMPARE_MODEL": "vision-uncensored",
            "AI_VISION_FALLBACK_MODEL": "vision-fallback",
            "AI_TEXT_PROVIDER": "ollama",
            "AI_TEXT_BASE_URL": "http://127.0.0.1:11435",
            "AI_TEXT_MODEL": "text-uncensored",
            "AI_TEXT_TIMEOUT_SECONDS": "420",
        }
        with patch.dict("os.environ", environment, clear=False):
            client = DummyTextClient(
                provider="ollama",
                base_url="http://127.0.0.1:11434",
                model="vision-standard",
                api_key=None,
                timeout_seconds=120,
            )
        self.assertEqual("text-uncensored", client.model)
        self.assertEqual("http://127.0.0.1:11435", client.base_url)
        self.assertEqual(420, client.timeout_seconds)
        self.assertEqual(
            (
                "text-uncensored",
                "vision-uncensored",
                "vision-standard",
                "vision-fallback",
            ),
            client._velvet_model_candidates,
        )

    def test_cascade_client_is_locked_to_explicit_route_model(self) -> None:
        environment = {
            "AI_VISION_MODEL": "vision-standard",
            "AI_VISION_COMPARE_MODEL": "vision-pro",
            "AI_VISION_FALLBACK_MODEL": "vision-sensitive",
        }
        with patch.dict("os.environ", environment, clear=False):
            client = DummyCascadeClient(
                provider="ollama",
                base_url="http://127.0.0.1:11435",
                model="flash-explicit",
                api_key=None,
                timeout_seconds=120,
            )
        self.assertEqual("flash-explicit", client.model)
        self.assertEqual(("flash-explicit",), client._velvet_model_candidates)

    def test_local_openai_compatible_provider_is_preserved_without_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            client = DummyCascadeClient(
                provider="local_openai_compatible",
                base_url="http://vision-gateway:8080/v1",
                model="qwen3.5:9b",
                api_key=None,
                timeout_seconds=300,
            )

        self.assertEqual("local_openai_compatible", client.provider)
        self.assertEqual("http://vision-gateway:8080/v1", client.base_url)
        self.assertEqual("qwen3.5:9b", client.model)
        self.assertIsNone(client.api_key)
        self.assertEqual(300, client.timeout_seconds)
        self.assertEqual(("qwen3.5:9b",), client._velvet_model_candidates)

    def test_unknown_vision_provider_error_lists_local_provider(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "local_openai_compatible"):
                DummyCascadeClient(
                    provider="unsupported",
                    base_url="http://vision-gateway:8080/v1",
                    model="qwen3.5:9b",
                    api_key=None,
                    timeout_seconds=300,
                )


if __name__ == "__main__":
    unittest.main()
