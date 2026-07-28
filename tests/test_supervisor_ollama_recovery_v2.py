from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from velvet_supervisor import ollama_recovery as core
from velvet_supervisor import ollama_recovery_v2 as runtime


class OllamaRecoveryV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_base_url = core._BASE_URL
        self.original_env_values = dict(core._ENV_VALUES)

    def tearDown(self) -> None:
        core._BASE_URL = self.original_base_url
        core._ENV_VALUES.clear()
        core._ENV_VALUES.update(self.original_env_values)

    def test_merge_default_storage_moves_partial_blob_and_removes_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "c-models"
            target = root / "e-models"
            source_blobs = source / "blobs"
            target_blobs = target / "blobs"
            source_blobs.mkdir(parents=True)
            target_blobs.mkdir(parents=True)

            partial = source_blobs / "sha256-layer-partial"
            partial.write_bytes(b"partial-data")
            duplicate_source = source_blobs / "sha256-existing"
            duplicate_target = target_blobs / "sha256-existing"
            duplicate_source.write_bytes(b"same")
            duplicate_target.write_bytes(b"same")

            source_manifest = (
                source
                / "manifests"
                / "hf.co"
                / "mradermacher"
                / "text-model"
                / "Q4_K_M"
            )
            source_manifest.parent.mkdir(parents=True)
            source_manifest.write_text("{}", encoding="utf-8")

            with patch.object(runtime, "_DEFAULT_STORAGE", source):
                result = runtime.merge_default_storage_into_e(target)

            self.assertFalse(partial.exists())
            self.assertEqual(
                b"partial-data",
                (target_blobs / "sha256-layer-partial").read_bytes(),
            )
            self.assertFalse(duplicate_source.exists())
            self.assertEqual(b"same", duplicate_target.read_bytes())
            self.assertTrue(
                (
                    target
                    / "manifests"
                    / "hf.co"
                    / "mradermacher"
                    / "text-model"
                    / "Q4_K_M"
                ).exists()
            )
            self.assertEqual(1, result["moved_blobs"])
            self.assertEqual(1, result["duplicate_blobs"])
            self.assertEqual(1, result["moved_manifests"])
            self.assertEqual(len(b"partial-data") + len(b"same"), result["freed_bytes"])

    def test_configure_runtime_pins_dedicated_api_and_e_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory) / "project"
            storage = Path(directory) / "e-models"
            project_dir.mkdir()
            (storage / "blobs").mkdir(parents=True)
            (storage / "manifests").mkdir(parents=True)
            env_path = project_dir / ".env"
            env_path.write_text(
                "BOT_TOKEN=keep-secret\n"
                "AI_VISION_BASE_URL=http://127.0.0.1:11434\n",
                encoding="utf-8",
            )

            runtime._configure_core()
            with (
                patch.dict(os.environ, {}, clear=False),
                patch.object(core, "_write_windows_user_environment"),
                patch.object(runtime, "_write_windows_user_value"),
                patch.object(runtime, "_broadcast_environment_change"),
            ):
                result = runtime.configure_runtime(project_dir, storage)
                self.assertEqual(str(storage), os.environ["OLLAMA_MODELS"])
                self.assertEqual("127.0.0.1:11435", os.environ["OLLAMA_HOST"])

            self.assertEqual(env_path, result)
            updated = env_path.read_text(encoding="utf-8")
            self.assertIn("BOT_TOKEN=keep-secret", updated)
            self.assertIn("AI_VISION_BASE_URL=http://127.0.0.1:11435", updated)
            self.assertIn("AI_TEXT_BASE_URL=http://127.0.0.1:11435", updated)
            self.assertIn(f"OLLAMA_MODELS={storage}", updated)
            self.assertIn("OLLAMA_HOST=127.0.0.1:11435", updated)


if __name__ == "__main__":
    unittest.main()
