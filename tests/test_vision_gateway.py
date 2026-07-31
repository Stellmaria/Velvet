from __future__ import annotations

import base64
import io
import unittest

from PIL import Image

from vision_gateway.app import (
    GatewayRequestError,
    GatewaySettings,
    normalize_image_data_uri,
    sanitize_chat_payload,
)


def _settings(**overrides: object) -> GatewaySettings:
    values: dict[str, object] = {
        "host": "0.0.0.0",
        "port": 8080,
        "runtime_base_url": "http://vision-runtime:11434",
        "model": "qwen3-vl:8b-instruct-q4_K_M",
        "expected_digest": None,
        "max_concurrency": 1,
        "max_image_side": 1280,
        "max_images": 8,
        "max_decoded_image_bytes": 20 * 1024 * 1024,
        "request_timeout_seconds": 300,
        "health_timeout_seconds": 5,
        "client_max_size": 32 * 1024 * 1024,
    }
    values.update(overrides)
    return GatewaySettings(**values)  # type: ignore[arg-type]


def _image_data_uri(width: int, height: int, *, alpha: bool = False) -> str:
    mode = "RGBA" if alpha else "RGB"
    color = (20, 40, 60, 128) if alpha else (20, 40, 60)
    image = Image.new(mode, (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


class VisionGatewayImageTests(unittest.TestCase):
    def test_large_image_is_resized_and_metadata_free(self) -> None:
        normalized = normalize_image_data_uri(
            _image_data_uri(2400, 1200),
            max_side=1280,
            max_decoded_bytes=20 * 1024 * 1024,
        )
        header, encoded = normalized.split(",", 1)
        self.assertEqual("data:image/jpeg;base64", header)
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
            self.assertEqual((1280, 640), image.size)
            self.assertEqual({}, image.info)

    def test_alpha_image_stays_png(self) -> None:
        normalized = normalize_image_data_uri(
            _image_data_uri(200, 100, alpha=True),
            max_side=1280,
            max_decoded_bytes=20 * 1024 * 1024,
        )
        self.assertTrue(normalized.startswith("data:image/png;base64,"))

    def test_remote_image_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(GatewayRequestError, "data URI"):
            normalize_image_data_uri(
                "https://example.com/private.png",
                max_side=1280,
                max_decoded_bytes=20 * 1024 * 1024,
            )


class VisionGatewayPayloadTests(unittest.TestCase):
    def test_payload_is_pinned_to_configured_model(self) -> None:
        settings = _settings()
        result = sanitize_chat_payload(
            {
                "model": settings.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Analyze visible facts."},
                            {
                                "type": "image_url",
                                "image_url": {"url": _image_data_uri(100, 50)},
                            },
                        ],
                    }
                ],
            },
            settings=settings,
        )
        self.assertEqual(settings.model, result["model"])
        self.assertFalse(result["stream"])

    def test_model_override_is_rejected(self) -> None:
        with self.assertRaisesRegex(GatewayRequestError, "not available"):
            sanitize_chat_payload(
                {
                    "model": "other-model",
                    "messages": [{"role": "user", "content": "test"}],
                },
                settings=_settings(),
            )

    def test_streaming_is_rejected(self) -> None:
        with self.assertRaisesRegex(GatewayRequestError, "Streaming"):
            sanitize_chat_payload(
                {
                    "stream": True,
                    "messages": [{"role": "user", "content": "test"}],
                },
                settings=_settings(),
            )

    def test_image_count_is_bounded(self) -> None:
        parts = [
            {
                "type": "image_url",
                "image_url": {"url": _image_data_uri(10, 10)},
            }
            for _ in range(2)
        ]
        with self.assertRaisesRegex(GatewayRequestError, "Too many"):
            sanitize_chat_payload(
                {"messages": [{"role": "user", "content": parts}]},
                settings=_settings(max_images=1),
            )


if __name__ == "__main__":
    unittest.main()
