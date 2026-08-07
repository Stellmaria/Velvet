from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"
if str(CODERS) not in sys.path:
    sys.path.insert(0, str(CODERS))

import codex_image_high_res_export as highres  # noqa: E402


class CodexImageHighResolutionExportTests(unittest.TestCase):
    def test_target_dimensions_use_real_2k_and_4k_pixels(self) -> None:
        self.assertEqual(highres.target_dimensions("2K", "1:1"), (2048, 2048))
        self.assertEqual(highres.target_dimensions("2K", "16:9"), (2048, 1152))
        self.assertEqual(highres.target_dimensions("4K", "9:16"), (2160, 3840))
        self.assertEqual(highres.target_dimensions("4K", "21:9"), (3840, 1646))

    def test_export_prompt_forbids_second_creative_generation(self) -> None:
        prompt = highres.build_export_prompt(
            source_name="generated.png",
            resolution="4K",
            aspect_ratio="16:9",
            width=3840,
            height=2160,
        )
        self.assertIn("Это не новая генерация", prompt)
        self.assertIn("Не вызывай image_gen", prompt)
        self.assertIn("python .hermes-image-export.py", prompt)
        self.assertIn("ровно 3840x2160", prompt)
        self.assertIn("Не используй сеть", prompt)

    def test_export_uses_local_pillow_lanczos_and_exact_size_verification(self) -> None:
        source = inspect.getsource(highres)
        self.assertIn("ImageOps.fit", source)
        self.assertIn("Image.Resampling.LANCZOS", source)
        self.assertIn("_verify_dimensions", source)
        self.assertIn("high_res_export_completed=True", source)

    def test_only_codex_2k_and_4k_need_post_export(self) -> None:
        self.assertTrue(
            highres._needs_high_res_export(
                {"status": "completed", "resolution": "2K"}
            )
        )
        self.assertTrue(
            highres._needs_high_res_export(
                {"status": "completed", "resolution": "4K"}
            )
        )
        self.assertFalse(
            highres._needs_high_res_export(
                {"status": "completed", "resolution": "1K"}
            )
        )
        self.assertFalse(
            highres._needs_high_res_export(
                {
                    "status": "completed",
                    "resolution": "4K",
                    "actual_route": "byesu_media",
                }
            )
        )

    def test_content_is_guarded_until_high_res_pass_finishes(self) -> None:
        source = inspect.getsource(highres.install_codex_image_high_res_export)
        self.assertIn("image_content", source)
        self.assertIn("high-resolution export ещё не завершён", source)
        self.assertIn("image_status", source)
        self.assertIn('payload["status"] = "running"', source)

    def test_runtime_installs_high_res_after_limit_preflight(self) -> None:
        source = (CODERS / "codex_context_launcher_runner.py").read_text(
            encoding="utf-8"
        )
        preflight = source.index("install_codex_image_limit_preflight()")
        high_res = source.index("install_codex_image_high_res_export()")
        self.assertLess(preflight, high_res)

    def test_coder_image_contains_pillow(self) -> None:
        dockerfile = (CODERS / "Dockerfile.coder").read_text(encoding="utf-8")
        self.assertIn("python3-pil", dockerfile)


if __name__ == "__main__":
    unittest.main()
