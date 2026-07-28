from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from velvet_bot.presentation.telegram.supervisor.remote_views import console_keyboard
from velvet_supervisor.ollama_recovery import (
    _FALLBACK_VISION_MODEL,
    _MODEL_BUNDLE,
    _STANDARD_VISION_MODEL,
    _UNCENSORED_TEXT_MODEL,
    _UNCENSORED_VISION_MODEL,
    OllamaRecoveryError,
    choose_e_storage,
    configure_ollama_storage_env,
    configure_vision_env,
    ensure_model_bundle,
    inspect_storage,
    scan_manifest_models,
    verify_model,
)
from velvet_supervisor.remote_console import RemoteCommandRegistry


class OllamaRecoveryEnvironmentTests(unittest.TestCase):
    def test_configure_updates_bundle_keys_without_touching_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            env_path = project_dir / ".env"
            env_path.write_text(
                "BOT_TOKEN=keep-this-secret\r\n"
                "AI_VISION_MODEL=hf.co/old/model\r\n"
                "CUSTOM_FLAG=preserve-me\r\n"
                "AI_VISION_COMPARE_MODEL=qwen3-vl:8b\r\n"
                "AI_VISION_MODEL=duplicate-old-model\r\n"
                "AI_TEXT_MODEL=old-text\r\n",
                encoding="utf-8",
                newline="",
            )

            result = configure_vision_env(project_dir)

            self.assertEqual(env_path, result)
            updated = env_path.read_text(encoding="utf-8")
            self.assertIn("BOT_TOKEN=keep-this-secret", updated)
            self.assertIn("CUSTOM_FLAG=preserve-me", updated)
            self.assertNotIn("hf.co/old/model", updated)
            self.assertNotIn("duplicate-old-model", updated)
            self.assertNotIn("AI_TEXT_MODEL=old-text", updated)
            self.assertEqual(
                1,
                updated.count(f"AI_VISION_MODEL={_STANDARD_VISION_MODEL}"),
            )
            self.assertEqual(
                1,
                updated.count(f"AI_VISION_COMPARE_MODEL={_UNCENSORED_VISION_MODEL}"),
            )
            self.assertEqual(
                1,
                updated.count(f"AI_VISION_FALLBACK_MODEL={_FALLBACK_VISION_MODEL}"),
            )
            self.assertEqual(
                1,
                updated.count(f"AI_TEXT_MODEL={_UNCENSORED_TEXT_MODEL}"),
            )
            self.assertIn("OLLAMA_MAX_LOADED_MODELS=1", updated)
            self.assertIn("OLLAMA_NUM_PARALLEL=1", updated)
            self.assertIn("OLLAMA_KV_CACHE_TYPE=q8_0", updated)

    def test_configure_creates_missing_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)

            env_path = configure_vision_env(project_dir)

            self.assertTrue(env_path.exists())
            updated = env_path.read_text(encoding="utf-8")
            self.assertIn(f"AI_VISION_MODEL={_STANDARD_VISION_MODEL}", updated)
            self.assertIn(
                f"AI_VISION_COMPARE_MODEL={_UNCENSORED_VISION_MODEL}",
                updated,
            )
            self.assertIn(f"AI_TEXT_MODEL={_UNCENSORED_TEXT_MODEL}", updated)

    def test_storage_config_preserves_secrets_and_removes_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            env_path = project_dir / ".env"
            env_path.write_text(
                "BOT_TOKEN=keep-this-secret\n"
                "OLLAMA_MODELS=C:\\old\n"
                "CUSTOM_FLAG=preserve-me\n"
                "OLLAMA_MODELS=C:\\duplicate\n",
                encoding="utf-8",
            )

            configure_ollama_storage_env(project_dir, Path(r"E:\OllamaModels"))

            updated = env_path.read_text(encoding="utf-8")
            self.assertIn("BOT_TOKEN=keep-this-secret", updated)
            self.assertIn("CUSTOM_FLAG=preserve-me", updated)
            self.assertNotIn(r"C:\old", updated)
            self.assertNotIn(r"C:\duplicate", updated)
            self.assertEqual(1, updated.count(r"OLLAMA_MODELS=E:\OllamaModels"))


class OllamaStorageLayoutTests(unittest.TestCase):
    def test_inspect_storage_requires_blobs_and_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "blobs").mkdir()
            (root / "blobs" / "sha256-model").write_bytes(b"model")

            layout = inspect_storage(root)

            self.assertFalse(layout.valid)
            self.assertTrue(layout.has_blobs)
            self.assertFalse(layout.has_manifests)
            self.assertEqual(1, layout.blob_count)

    def test_choose_storage_prefers_layout_with_more_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct = root / "OllamaModels"
            nested = direct / "models"
            for candidate in (direct, nested):
                (candidate / "blobs").mkdir(parents=True)
                (candidate / "manifests").mkdir(parents=True)
                (candidate / "blobs" / "sha256-model").write_bytes(b"model")
            (direct / "manifests" / "one").write_text("one", encoding="utf-8")
            (nested / "manifests" / "one").write_text("one", encoding="utf-8")
            (nested / "manifests" / "two").write_text("two", encoding="utf-8")

            selected = choose_e_storage((direct, nested))

            self.assertIsNotNone(selected)
            assert selected is not None
            self.assertEqual(nested, selected.path)
            self.assertEqual(2, selected.manifest_count)

    def test_choose_storage_returns_none_for_invalid_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            (second / "blobs").mkdir(parents=True)

            self.assertIsNone(choose_e_storage((first, second)))

    def test_scan_manifest_models_recovers_ollama_and_huggingface_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ollama_manifest = (
                root
                / "manifests"
                / "registry.ollama.ai"
                / "library"
                / "qwen3-vl"
                / "8b"
            )
            hf_manifest = (
                root
                / "manifests"
                / "hf.co"
                / "mradermacher"
                / "Qwen3-VL-4B-Instruct-abliterated-GGUF"
                / "Q4_K_M"
            )
            ollama_manifest.parent.mkdir(parents=True)
            hf_manifest.parent.mkdir(parents=True)
            ollama_manifest.write_text("{}", encoding="utf-8")
            hf_manifest.write_text("{}", encoding="utf-8")

            names = scan_manifest_models(root)

            self.assertIn("qwen3-vl:8b", names)
            self.assertIn(_FALLBACK_VISION_MODEL, names)


class OllamaRecoveryCapabilityTests(unittest.TestCase):
    def test_verify_model_requires_requested_capability(self) -> None:
        with patch(
            "velvet_supervisor.ollama_recovery._request_json",
            return_value={"capabilities": ["completion"]},
        ):
            with self.assertRaisesRegex(OllamaRecoveryError, "vision отсутствует"):
                verify_model(_STANDARD_VISION_MODEL, required_capability="vision")

    def test_verify_model_accepts_text_completion_capability(self) -> None:
        with patch(
            "velvet_supervisor.ollama_recovery._request_json",
            return_value={"capabilities": ["completion"]},
        ):
            capabilities = verify_model(
                _UNCENSORED_TEXT_MODEL,
                required_capability="completion",
            )

        self.assertEqual(("completion",), capabilities)

    def test_ensure_bundle_skips_api_models_and_registers_disk_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            storage = project_dir / "models"
            manifest = (
                storage
                / "manifests"
                / "hf.co"
                / "mradermacher"
                / "Qwen3-VL-4B-Instruct-abliterated-GGUF"
                / "Q4_K_M"
            )
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}", encoding="utf-8")

            api_snapshots = [
                (_STANDARD_VISION_MODEL,),
                (_STANDARD_VISION_MODEL, _UNCENSORED_VISION_MODEL),
                (
                    _STANDARD_VISION_MODEL,
                    _UNCENSORED_VISION_MODEL,
                    _FALLBACK_VISION_MODEL,
                ),
                tuple(spec.name for spec in _MODEL_BUNDLE),
            ]
            pulls: list[str] = []

            with (
                patch("velvet_supervisor.ollama_recovery.start_ollama"),
                patch(
                    "velvet_supervisor.ollama_recovery._api_model_names",
                    side_effect=api_snapshots,
                ),
                patch(
                    "velvet_supervisor.ollama_recovery.pull_model",
                    side_effect=lambda _project, model: pulls.append(model),
                ),
            ):
                pulled = ensure_model_bundle(project_dir, storage)

            self.assertEqual(tuple(pulls), pulled)
            self.assertNotIn(_STANDARD_VISION_MODEL, pulls)
            self.assertIn(_UNCENSORED_VISION_MODEL, pulls)
            self.assertIn(_FALLBACK_VISION_MODEL, pulls)
            self.assertIn(_UNCENSORED_TEXT_MODEL, pulls)


class OllamaRecoveryRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = SimpleNamespace(
            project_dir=Path("."),
            python_executable="python.exe",
            test_command=("python.exe", "-m", "unittest"),
            command_timeout_seconds=900,
            api_token="t" * 32,
            notification_bot_token=None,
        )
        self.registry = RemoteCommandRegistry(self.settings)  # type: ignore[arg-type]

    def test_repair_command_remains_fixed_and_shell_free(self) -> None:
        spec = self.registry.resolve("ollama-repair-qwen3-vl-4b", by_key=True)

        self.assertEqual(
            (
                "python.exe",
                "-m",
                "velvet_supervisor.ollama_recovery",
                "repair",
            ),
            spec.command,
        )
        self.assertEqual("AI: Ollama", spec.category)
        self.assertEqual(900, spec.timeout_seconds)
        self.assertNotIn("powershell", " ".join(spec.command).casefold())
        self.assertNotIn("cmd.exe", " ".join(spec.command).casefold())

    def test_console_keeps_status_and_repair_buttons(self) -> None:
        commands = [spec.to_dict() for spec in self.registry.catalog()]

        keyboard = console_keyboard(commands)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertIn("▶️ Ollama: состояние vision", labels)
        self.assertIn("▶️ Ollama: восстановить vision qwen3-vl:4b", labels)


if __name__ == "__main__":
    unittest.main()
