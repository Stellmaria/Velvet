import io
import json
import unittest
from unittest.mock import patch

from PIL import Image

from velvet_bot.ollama_vision import (
    ReliableVisionClient,
    _SCHEMA_PROMPT,
    _parse_ollama_payload,
)


def _profile() -> dict:
    return {
        "series_title_ru": "Дикий Запад",
        "summary_ru": "Сцена в эстетике вестерна.",
        "themes": ["western"],
        "genres": ["western"],
        "settings": ["saloon"],
        "eras": ["19th century"],
        "environment": ["wooden interior"],
        "objects": ["cowboy hat"],
        "wardrobe": ["western clothing"],
        "composition": ["medium shot"],
        "lighting": ["warm light"],
        "palette": ["earth tones"],
        "mood": ["tense"],
        "actions": ["standing"],
        "series_keywords": ["western", "saloon"],
        "people_count": 1,
        "confidence": 91,
    }


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(output, format="PNG")
    return output.getvalue()


class OllamaVisionParsingTests(unittest.TestCase):
    def test_schema_is_grounded_in_prompt(self) -> None:
        self.assertIn('"series_title_ru"', _SCHEMA_PROMPT)
        self.assertIn("Не добавляй markdown", _SCHEMA_PROMPT)

    def test_json_can_be_recovered_from_thinking_field(self) -> None:
        result = _parse_ollama_payload(
            {
                "message": {
                    "content": "",
                    "thinking": json.dumps(_profile(), ensure_ascii=False),
                },
                "done_reason": "stop",
            }
        )

        self.assertEqual("Дикий Запад", result["series_title_ru"])
        self.assertEqual(["western"], result["themes"])


class OllamaVisionClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_retries_with_plain_json_mode(self) -> None:
        client = ReliableVisionClient(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model="qwen3-vl:8b",
            api_key=None,
            timeout_seconds=30,
        )
        request_bodies: list[dict] = []
        responses = iter(
            [
                {
                    "message": {"content": "I will describe the image instead."},
                    "done_reason": "stop",
                    "eval_count": 12,
                },
                {
                    "message": {
                        "content": json.dumps(_profile(), ensure_ascii=False)
                    },
                    "done_reason": "stop",
                    "eval_count": 120,
                },
            ]
        )

        def fake_read(request, *, timeout):
            self.assertEqual(30, timeout)
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return next(responses)

        with patch.object(client, "_read_json", side_effect=fake_read):
            result = await client.analyze(_image_bytes())

        self.assertEqual("Дикий Запад", result["series_title_ru"])
        self.assertEqual(2, len(request_bodies))
        self.assertIsInstance(request_bodies[0]["format"], dict)
        self.assertEqual("json", request_bodies[1]["format"])
        self.assertFalse(request_bodies[0]["think"])
        self.assertEqual(1600, request_bodies[0]["options"]["num_predict"])


if __name__ == "__main__":
    unittest.main()
