from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from velvet_bot.domains.watermark.models import (
    WatermarkJob,
    WatermarkRevision,
    WatermarkSettings,
    WatermarkWorkItem,
)
from velvet_bot.infrastructure.krita_bridge import KritaBridge
from velvet_bot.watermark_ui import WatermarkCallback


class WatermarkSettingsTests(unittest.TestCase):
    def test_settings_are_bounded_and_normalized(self) -> None:
        settings = WatermarkSettings(
            position="BOTTOM_RIGHT",
            color="#D8C8B8",
            opacity=150,
            size=1,
            margin=99,
        ).normalized()
        self.assertEqual(settings.position, "bottom_right")
        self.assertEqual(settings.color, "#d8c8b8")
        self.assertEqual(settings.opacity, 100)
        self.assertEqual(settings.size, 3.0)
        self.assertEqual(settings.margin, 30.0)

    def test_invalid_color_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            WatermarkSettings(color="white").normalized()


class KritaBridgeTests(unittest.TestCase):
    def test_dispatch_writes_versioned_request_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bridge = KritaBridge(directory)
            source = bridge.paths.sources / "source.png"
            source.write_bytes(b"png")
            now = datetime.now(UTC)
            item = WatermarkWorkItem(
                job=WatermarkJob(
                    id=7,
                    owner_user_id=1,
                    chat_id=2,
                    source_message_id=3,
                    source_file_id="file",
                    source_file_unique_id="unique",
                    source_path=str(source),
                    status="active",
                    current_revision=4,
                    control_message_id=None,
                    preview_message_id=None,
                    final_path=None,
                    created_at=now,
                    updated_at=now,
                ),
                revision=WatermarkRevision(
                    job_id=7,
                    revision=4,
                    settings=WatermarkSettings(color="auto"),
                    status="processing",
                    request_path=None,
                    output_path=None,
                    response_path=None,
                    telegram_preview_file_id=None,
                    error=None,
                    created_at=now,
                    completed_at=None,
                ),
            )
            request, output, response = bridge.dispatch(item)
            payload = json.loads(request.read_text(encoding="utf-8"))
            self.assertEqual(payload["job_id"], 7)
            self.assertEqual(payload["revision"], 4)
            self.assertEqual(payload["settings"]["color"], "auto")
            self.assertEqual(Path(payload["output_path"]), output)
            self.assertEqual(Path(payload["response_path"]), response)

    def test_path_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bridge = KritaBridge(directory)
            with self.assertRaises(ValueError):
                bridge.paths.ensure_inside(Path(directory).parent / "outside.png")


class WatermarkCallbackTests(unittest.TestCase):
    def test_callback_fits_telegram_limit(self) -> None:
        value = WatermarkCallback(
            action="position",
            job_id=123456789,
            value="bottom_right",
        ).pack()
        self.assertLessEqual(len(value.encode("utf-8")), 64)


if __name__ == "__main__":
    unittest.main()
