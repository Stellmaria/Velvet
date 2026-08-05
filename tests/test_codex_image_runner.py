from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "hermes-coders"))

import codex_image_runner  # noqa: E402


class CodexImageRunnerTests(unittest.TestCase):
    def test_prompt_requires_one_generation_and_unified_reference_analysis(self) -> None:
        prompt = codex_image_runner.build_image_prompt(
            user_prompt="Портрет персонажа",
            reference_names=("one.jpg", "two.png"),
            aspect_ratio="9:16",
            resolution="4K",
        )
        self.assertIn("ровно один раз", prompt)
        self.assertIn("единый набор референсов", prompt)
        self.assertIn("9:16", prompt)
        self.assertIn("4K", prompt)
        self.assertIn(".hermes-image-output/result", prompt)

    def test_reference_validation_accepts_jpeg(self) -> None:
        encoded = base64.b64encode(b"\xff\xd8\xffdata").decode("ascii")
        name, mime, payload = codex_image_runner._decode_reference(
            {
                "file_name": "face.jpg",
                "mime_type": "image/jpeg",
                "data_base64": encoded,
            },
            index=1,
        )
        self.assertEqual(name, "face.jpg")
        self.assertEqual(mime, "image/jpeg")
        self.assertTrue(payload.startswith(b"\xff\xd8\xff"))

    def test_artifact_selector_accepts_one_result(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "result.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            selected = codex_image_runner.CodexImageSupport._find_image_artifact(root)
            self.assertEqual(selected.name, "result.png")


if __name__ == "__main__":
    unittest.main()
