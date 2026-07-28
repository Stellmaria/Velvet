from __future__ import annotations

import asyncio
import io
import json
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from velvet_bot.ai_vision import (
    VisionAnalysisError,
    VisionClient,
    VisionProviderUnavailable,
)
from velvet_bot.infrastructure.image_to_prompt import ImageToPromptClient


class ImageToPromptOllamaErrorTests(unittest.TestCase):
    @staticmethod
    def _client() -> ImageToPromptClient:
        return ImageToPromptClient(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model="test-model",
            api_key=None,
            timeout_seconds=30,
        )

    def test_http_400_includes_ollama_error_body(self) -> None:
        error = urllib.error.HTTPError(
            "http://127.0.0.1:11434/api/chat",
            400,
            "Bad Request",
            None,
            io.BytesIO(json.dumps({"error": "model does not support images"}).encode()),
        )
        request = urllib.request.Request("http://127.0.0.1:11434/api/chat")
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(
                VisionAnalysisError,
                "HTTP 400: model does not support images",
            ):
                VisionClient._read_json(request, timeout=10)

    def test_http_500_is_provider_unavailable(self) -> None:
        error = urllib.error.HTTPError(
            "http://127.0.0.1:11434/api/chat",
            500,
            "Internal Server Error",
            None,
            io.BytesIO(json.dumps({"error": "runner crashed"}).encode()),
        )
        request = urllib.request.Request("http://127.0.0.1:11434/api/chat")
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(
                VisionProviderUnavailable,
                "HTTP 500: runner crashed",
            ):
                VisionClient._read_json(request, timeout=10)

    def test_ollama_model_without_vision_capability_is_rejected(self) -> None:
        client = self._client()
        with patch.object(
            client,
            "_read_json",
            return_value={"capabilities": ["completion"]},
        ):
            with self.assertRaisesRegex(
                VisionAnalysisError,
                "не поддерживает изображения",
            ):
                asyncio.run(client._ensure_vision_capability())

    def test_missing_capabilities_remains_backward_compatible(self) -> None:
        client = self._client()
        with patch.object(client, "_read_json", return_value={}):
            asyncio.run(client._ensure_vision_capability())


if __name__ == "__main__":
    unittest.main()
