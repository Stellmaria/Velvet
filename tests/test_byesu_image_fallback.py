from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "hermes-coders"))

import byesu_image_fallback as fallback  # noqa: E402


class StubByesuClient(fallback.ByesuImageClient):
    def __init__(self) -> None:
        self.base_url = "https://byesu.invalid/v1"
        self.api_key = "fixture"
        self.image_model = "firefly-gpt-image-2"
        self.timeout_seconds = 60
        self.calls: list[tuple[str, str, Mapping[str, object] | None]] = []
        self.responses: dict[str, dict[str, Any]] = {}

    def _json(
        self,
        path: str,
        *,
        method: str = "GET",
        data: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((path, method, data))
        return self.responses[path]


class ByesuImageFallbackTests(unittest.TestCase):
    def test_size_mapping_uses_real_resolution_and_ratio(self) -> None:
        self.assertEqual(fallback._size_for("1K", "1:1"), "1024x1024")
        self.assertEqual(fallback._size_for("2K", "16:9"), "2048x1152")
        self.assertEqual(fallback._size_for("4K", "9:16"), "2160x3840")

    def test_lifecycle_events_do_not_block_clean_limit_fallback(self) -> None:
        stdout = "\n".join(
            (
                json.dumps({"type": "thread.started", "thread_id": "t"}),
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "error",
                        "message": "You've hit your usage limit.",
                    }
                ),
            )
        )
        record = {
            "status": "failed",
            "error": "You've hit your usage limit.",
        }
        self.assertTrue(
            fallback._eligible(
                record,
                {
                    "stdout": stdout,
                    "stderr": "",
                    "execution_started": False,
                },
            )
        )

    def test_tool_execution_blocks_fallback(self) -> None:
        stdout = json.dumps(
            {
                "type": "item.started",
                "item": {"type": "dynamic_tool_call"},
            }
        )
        record = {
            "status": "failed",
            "error": "You've hit your usage limit.",
        }
        self.assertFalse(
            fallback._eligible(
                record,
                {
                    "stdout": stdout,
                    "stderr": "",
                    "execution_started": False,
                },
            )
        )

    def test_capability_check_requires_analysis_and_media_models(self) -> None:
        client = StubByesuClient()
        client.responses["/models"] = {
            "data": [
                {"id": "gpt-5.6-sol"},
                {"id": "firefly-gpt-image-2"},
            ]
        }
        client.assert_capabilities("gpt-5.6-sol")

        client.responses["/models"] = {"data": [{"id": "gpt-5.6-sol"}]}
        with self.assertRaisesRegex(
            fallback.ByesuImageFallbackError,
            "media / media-gen",
        ):
            client.assert_capabilities("gpt-5.6-sol")

    def test_analysis_sends_all_references_and_selected_effort(self) -> None:
        client = StubByesuClient()
        client.responses["/responses"] = {
            "output_text": "Подробный итоговый prompt",
            "usage": {"input_tokens": 100, "output_tokens": 20},
        }
        refs = (
            fallback.ByesuReference("one.jpg", "image/jpeg", b"one"),
            fallback.ByesuReference("two.png", "image/png", b"two"),
        )
        prompt, usage = client.analyze(
            user_prompt="Сохрани внешность персонажа",
            references=refs,
            analysis_model="gpt-5.6-sol",
            reasoning_effort="max",
            aspect_ratio="9:16",
            resolution="4K",
        )
        self.assertEqual(prompt, "Подробный итоговый prompt")
        self.assertEqual(usage, {"input_tokens": 100, "output_tokens": 20})
        path, method, payload = client.calls[-1]
        self.assertEqual((path, method), ("/responses", "POST"))
        assert payload is not None
        self.assertEqual(payload["model"], "gpt-5.6-sol")
        self.assertEqual(payload["reasoning"], {"effort": "max"})
        content = payload["input"][0]["content"]  # type: ignore[index]
        image_parts = [item for item in content if item["type"] == "input_image"]
        self.assertEqual(len(image_parts), 2)
        self.assertTrue(image_parts[0]["image_url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(image_parts[0]["detail"], "original")

    def test_reference_loader_rejects_files_over_eight_megabytes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "large.jpg").write_bytes(b"x" * (8 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(
                fallback.ByesuImageFallbackError,
                "8 МБ",
            ):
                fallback._load_references(
                    {
                        "references": [
                            {
                                "file_name": "large.jpg",
                                "mime_type": "image/jpeg",
                            }
                        ]
                    },
                    root,
                )


if __name__ == "__main__":
    unittest.main()
