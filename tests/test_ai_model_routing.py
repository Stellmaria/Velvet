from __future__ import annotations

import json
import unittest
import urllib.request
from unittest.mock import patch

from velvet_bot.ai_model_routing import (
    _configure_client,
    _routed_read_json,
    clear_ai_model_cache,
)
from velvet_bot.ai_vision import VisionClient


class DummyVisionClient(VisionClient):
    pass


class DummyTextClient(VisionClient):
    ai_task_profile = "text"


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
        client = DummyVisionClient.__new__(DummyVisionClient)
        environment = {
            "AI_VISION_MODEL": "vision-standard",
            "AI_VISION_COMPARE_MODEL": "vision-uncensored",
            "AI_VISION_FALLBACK_MODEL": "vision-fallback",
        }
        with patch.dict("os.environ", environment, clear=False):
            _configure_client(
                client,
                provider="ollama",
                base_url="http://127.0.0.1:11435",
                model="vision-standard",
                api_key=None,
                timeout_seconds=120,
            )

        requested: list[str] = []

        def fake_read(request: urllib.request.Request, *, timeout: int) -> dict[str, object]:
            self.assertGreaterEqual(timeout, 1)
            if request.full_url.endswith("/api/tags"):
                return {"models": [{"name": "vision-uncensored"}]}
            payload = json.loads((request.data or b"{}").decode("utf-8"))
            requested.append(str(payload["model"]))
            return {"message": {"content": "{}"}}

        with patch("velvet_bot.ai_model_routing._ORIGINAL_READ_JSON", side_effect=fake_read):
            result = _routed_read_json(
                client,
                _request(client.base_url, client.model),
                timeout=120,
            )

        self.assertEqual({"message": {"content": "{}"}}, result)
        self.assertEqual(["vision-uncensored"], requested)
        self.assertEqual("vision-uncensored", client.model)

    def test_text_client_uses_text_provider_model_and_timeout(self) -> None:
        client = DummyTextClient.__new__(DummyTextClient)
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
            _configure_client(
                client,
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

    def test_text_route_falls_back_when_text_model_is_not_installed(self) -> None:
        client = DummyTextClient.__new__(DummyTextClient)
        environment = {
            "AI_VISION_MODEL": "vision-standard",
            "AI_VISION_COMPARE_MODEL": "vision-uncensored",
            "AI_VISION_FALLBACK_MODEL": "vision-fallback",
            "AI_TEXT_MODEL": "text-uncensored",
        }
        with patch.dict("os.environ", environment, clear=False):
            _configure_client(
                client,
                provider="ollama",
                base_url="http://127.0.0.1:11435",
                model="vision-standard",
                api_key=None,
                timeout_seconds=120,
            )

        requested: list[str] = []

        def fake_read(request: urllib.request.Request, *, timeout: int) -> dict[str, object]:
            if request.full_url.endswith("/api/tags"):
                return {"models": [{"name": "vision-uncensored"}]}
            payload = json.loads((request.data or b"{}").decode("utf-8"))
            requested.append(str(payload["model"]))
            return {"message": {"content": "{}"}}

        with patch("velvet_bot.ai_model_routing._ORIGINAL_READ_JSON", side_effect=fake_read):
            _routed_read_json(
                client,
                _request(client.base_url, client.model),
                timeout=120,
            )

        self.assertEqual(["vision-uncensored"], requested)
        self.assertEqual("vision-uncensored", client.model)


if __name__ == "__main__":
    unittest.main()
