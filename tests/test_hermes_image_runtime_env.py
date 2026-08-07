from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"
if str(CODERS) not in sys.path:
    sys.path.insert(0, str(CODERS))

import compose_image_runtime_env as image_env  # noqa: E402


class HermesImageRuntimeEnvTests(unittest.TestCase):
    def _source(self, body: str) -> Path:
        root = Path(tempfile.mkdtemp())
        path = root / ".env.hermes"
        path.write_text(body, encoding="utf-8")
        return path

    def test_projection_exposes_media_key_and_nonsecret_image_settings_only(self) -> None:
        media = "m" * 32
        source = self._source(
            "\n".join(
                (
                    "BYESU_HERMES_CODEX_API_KEY=do-not-project",
                    "OPENAI_API_KEY=also-do-not-project",
                    "BYESU_MEDIA_GEN_API_KEY=" + media,
                    "CODEX_IMAGE_BYESU_FALLBACK_ENABLED=yes",
                    "CODEX_IMAGE_LIMIT_PREFLIGHT_ENABLED=0",
                    "CODEX_IMAGE_LIMIT_PREFLIGHT_TIMEOUT_SECONDS=4",
                    "CODEX_IMAGE_BYESU_BASE_URL=https://byesu.com/v1/",
                    "CODEX_IMAGE_BYESU_TIMEOUT_SECONDS=900",
                )
            )
            + "\n"
        )
        projected = image_env.build_environment(source, {"KEEP_ME": "1"})

        self.assertEqual(projected["KEEP_ME"], "1")
        self.assertEqual(projected["BYESU_MEDIA_GEN_API_KEY"], media)
        self.assertEqual(projected["CODEX_IMAGE_BYESU_FALLBACK_ENABLED"], "true")
        self.assertEqual(projected["CODEX_IMAGE_LIMIT_PREFLIGHT_ENABLED"], "false")
        self.assertEqual(
            projected["CODEX_IMAGE_LIMIT_PREFLIGHT_TIMEOUT_SECONDS"], "4"
        )
        self.assertEqual(projected["CODEX_IMAGE_BYESU_BASE_URL"], "https://byesu.com/v1")
        self.assertEqual(projected["CODEX_IMAGE_BYESU_TIMEOUT_SECONDS"], "900")
        self.assertNotIn("BYESU_HERMES_CODEX_API_KEY", projected)
        self.assertNotIn("OPENAI_API_KEY", projected)

    def test_enabled_fallback_requires_media_key(self) -> None:
        source = self._source("CODEX_IMAGE_BYESU_FALLBACK_ENABLED=true\n")
        with self.assertRaisesRegex(
            image_env.ImageRuntimeEnvError,
            "BYESU_MEDIA_GEN_API_KEY",
        ):
            image_env.build_environment(source, {})

    def test_missing_image_settings_leave_compose_defaults_in_control(self) -> None:
        source = self._source("BYESU_HERMES_CODEX_API_KEY=secret\n")
        projected = image_env.build_environment(source, {"KEEP_ME": "1"})
        self.assertEqual(projected, {"KEEP_ME": "1"})

    def test_invalid_image_settings_fail_closed(self) -> None:
        invalid = {
            "BYESU_MEDIA_GEN_API_KEY": "short",
            "CODEX_IMAGE_BYESU_FALLBACK_ENABLED": "maybe",
            "CODEX_IMAGE_LIMIT_PREFLIGHT_TIMEOUT_SECONDS": "2",
            "CODEX_IMAGE_BYESU_TIMEOUT_SECONDS": "1801",
            "CODEX_IMAGE_BYESU_BASE_URL": "http://byesu.com/v1",
        }
        for name, value in invalid.items():
            with self.subTest(name=name):
                source = self._source(f"{name}={value}\n")
                with self.assertRaises(image_env.ImageRuntimeEnvError):
                    image_env.build_environment(source, {})

    def test_symlinked_operator_env_is_rejected(self) -> None:
        root = Path(tempfile.mkdtemp())
        actual = root / "actual.env"
        actual.write_text("CODEX_IMAGE_BYESU_FALLBACK_ENABLED=true\n", encoding="utf-8")
        linked = root / ".env.hermes"
        linked.symlink_to(actual)
        with self.assertRaises(image_env.ImageRuntimeEnvError):
            image_env.build_environment(linked, {})

    def test_media_key_is_declared_only_on_velvet_coder(self) -> None:
        compose = (CODERS / "compose.runtime.yaml").read_text(encoding="utf-8")
        chat_prefix, coder_tail = compose.split("  hermes-coder-velvet:", 1)
        velvet_coder, maximum = coder_tail.split("  hermes-coder-max:", 1)
        self.assertNotIn("BYESU_MEDIA_GEN_API_KEY", chat_prefix)
        self.assertIn("BYESU_MEDIA_GEN_API_KEY", velvet_coder)
        self.assertNotIn("BYESU_MEDIA_GEN_API_KEY", maximum)
        self.assertNotIn("velvet-media.env", compose)

    def test_systemd_wraps_every_compose_lifecycle_command(self) -> None:
        unit = (ROOT / "deploy" / "systemd" / "hermes-coders.service").read_text(
            encoding="utf-8"
        )
        wrapper = "compose_image_runtime_env.py /usr/bin/docker compose"
        self.assertGreaterEqual(unit.count(wrapper), 4)
        self.assertNotIn("ExecStart=/usr/bin/docker compose", unit)
        self.assertNotIn("ExecStop=/usr/bin/docker compose", unit)
        self.assertNotIn("ExecReload=/usr/bin/docker compose", unit)


if __name__ == "__main__":
    unittest.main()
