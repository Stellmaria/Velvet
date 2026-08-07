from __future__ import annotations

import base64
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"
if str(CODERS) not in sys.path:
    sys.path.insert(0, str(CODERS))

import byesu_image_credentials as credentials  # noqa: E402
import byesu_image_fallback as fallback  # noqa: E402


class ByesuImageCredentialTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_init = fallback.ByesuImageClient.__init__
        self._original_assert = fallback.ByesuImageClient.assert_capabilities
        self._original_generate = fallback.ByesuImageClient.generate
        self._installed = credentials._INSTALLED
        credentials._INSTALLED = False

    def tearDown(self) -> None:
        fallback.ByesuImageClient.__init__ = self._original_init
        fallback.ByesuImageClient.assert_capabilities = self._original_assert
        fallback.ByesuImageClient.generate = self._original_generate
        credentials._INSTALLED = self._installed

    def test_init_requires_explicit_media_credential(self) -> None:
        credentials.install_byesu_dual_credentials()
        with patch.dict(
            os.environ,
            {
                "BYESU_HERMES_CODEX_API_KEY": "c" * 24,
                "BYESU_HERMES_MEDIA_API_KEY": "m" * 24,
            },
            clear=False,
        ):
            client = fallback.ByesuImageClient()
        self.assertEqual("c" * 24, client.analysis_api_key)
        self.assertEqual("m" * 24, client.media_api_key)
        self.assertEqual("c" * 24, client.api_key)

        with patch.dict(
            os.environ,
            {
                "BYESU_HERMES_CODEX_API_KEY": "c" * 24,
                "BYESU_HERMES_MEDIA_API_KEY": "",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(
                fallback.ByesuImageFallbackError,
                "BYESU_HERMES_MEDIA_API_KEY",
            ):
                fallback.ByesuImageClient()

    def test_capability_check_uses_separate_token_groups(self) -> None:
        credentials.install_byesu_dual_credentials()
        client = object.__new__(fallback.ByesuImageClient)
        client.base_url = "https://byesu.invalid/v1"
        client.api_key = "codex-key"
        client.analysis_api_key = "codex-key"
        client.media_api_key = "media-key"
        client.image_model = "firefly-gpt-image-2"
        client.timeout_seconds = 60
        calls: list[str] = []

        def fake_json(self, path: str, *, method: str = "GET", data=None):
            self.assert_path = path
            calls.append(self.api_key)
            if self.api_key == "codex-key":
                return {"data": [{"id": "gpt-5.6-sol"}]}
            return {"data": [{"id": "firefly-gpt-image-2"}]}

        client._json = types.MethodType(fake_json, client)
        client.assert_capabilities("gpt-5.6-sol")
        self.assertEqual(["codex-key", "media-key"], calls)
        self.assertEqual("codex-key", client.api_key)

        def missing_media(self, path: str, *, method: str = "GET", data=None):
            if self.api_key == "codex-key":
                return {"data": [{"id": "gpt-5.6-sol"}]}
            return {"data": []}

        client._json = types.MethodType(missing_media, client)
        with self.assertRaisesRegex(
            fallback.ByesuImageFallbackError,
            "media token group",
        ):
            client.assert_capabilities("gpt-5.6-sol")

    def test_generation_uses_media_key_and_restores_analysis_key(self) -> None:
        credentials.install_byesu_dual_credentials()
        client = object.__new__(fallback.ByesuImageClient)
        client.base_url = "https://byesu.invalid/v1"
        client.api_key = "codex-key"
        client.analysis_api_key = "codex-key"
        client.media_api_key = "media-key"
        client.image_model = "gpt-image-2"
        client.timeout_seconds = 60
        observed: dict[str, str] = {}

        def fake_open(self, request):
            observed["authorization"] = request.get_header("Authorization") or ""
            image = b"\x89PNG\r\n\x1a\nfixture"
            return json.dumps(
                {"data": [{"b64_json": base64.b64encode(image).decode("ascii")}]}
            ).encode("utf-8")

        client._open = types.MethodType(fake_open, client)
        payload, mime_type, suffix = client.generate(
            prompt="fixture",
            references=(),
            size="1024x1024",
        )
        self.assertTrue(payload.startswith(b"\x89PNG"))
        self.assertEqual("image/png", mime_type)
        self.assertEqual(".png", suffix)
        self.assertEqual("Bearer media-key", observed["authorization"])
        self.assertEqual("codex-key", client.api_key)


if __name__ == "__main__":
    unittest.main()
