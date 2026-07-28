from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from velvet_supervisor.ollama_recovery import (
    OllamaRecoveryError,
    configure_vision_env,
    verify_model,
)
from velvet_supervisor.remote_console import RemoteCommandRegistry


class OllamaRecoveryEnvironmentTests(unittest.TestCase):
    def test_configure_updates_only_ai_vision_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            env_path = project_dir / ".env"
            env_path.write_text(
                "BOT_TOKEN=keep-this-secret\r\n"
                "AI_VISION_MODEL=hf.co/old/model\r\n"
                "CUSTOM_FLAG=preserve-me\r\n"
                "AI_VISION_COMPARE_MODEL=qwen3-vl:8b\r\n"
                "AI_VISION_MODEL=duplicate-old-model\r\n",
                encoding="utf-8",
                newline="",
            )

            result = configure_vision_env(project_dir)

            self.assertEqual(env_path, result)
            updated = env_path.read_text(encoding="utf-8")
            self.assertIn("BOT_TOKEN=keep-this-secret", updated)
            self.assertIn("CUSTOM_FLAG=preserve-me", updated)
            self.assertNotIn("hf.co/old/model", updated)
            self.assertNotIn("qwen3-vl:8b", updated)
            self.assertNotIn("duplicate-old-model", updated)
            self.assertEqual(1, updated.count("AI_VISION_MODEL=qwen3-vl:4b"))
            self.assertEqual(1, updated.count("AI_VISION_COMPARE_MODEL="))
            self.assertIn("AI_VISION_ENABLED=true", updated)
            self.assertIn("AI_VISION_PROVIDER=ollama", updated)
            self.assertIn(
                "AI_VISION_BASE_URL=http://127.0.0.1:11434",
                updated,
            )
            self.assertIn("AI_VISION_TIMEOUT_SECONDS=600", updated)

    def test_configure_creates_missing_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)

            env_path = configure_vision_env(project_dir)

            self.assertTrue(env_path.exists())
            updated = env_path.read_text(encoding="utf-8")
            self.assertIn("AI_VISION_MODEL=qwen3-vl:4b", updated)
            self.assertIn("AI_VISION_COMPARE_MODEL=", updated)


class OllamaRecoveryCapabilityTests(unittest.TestCase):
    def test_verify_model_requires_vision_capability(self) -> None:
        with patch(
            "velvet_supervisor.ollama_recovery._request_json",
            return_value={"capabilities": ["completion"]},
        ):
            with self.assertRaisesRegex(OllamaRecoveryError, "vision отсутствует"):
                verify_model()

    def test_verify_model_accepts_vision_capability(self) -> None:
        with patch(
            "velvet_supervisor.ollama_recovery._request_json",
            return_value={"capabilities": ["completion", "vision"]},
        ):
            capabilities = verify_model()

        self.assertEqual(("completion", "vision"), capabilities)


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

    def test_repair_command_is_fixed_and_shell_free(self) -> None:
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

    def test_registry_exposes_only_fixed_recovery_actions(self) -> None:
        expected = {
            "ollama-recovery-status": "status",
            "ollama-start": "start",
            "ollama-configure-qwen3-vl-4b": "configure",
            "ollama-pull-qwen3-vl-4b": "pull",
            "ollama-show-qwen3-vl-4b": "show",
            "ollama-repair-qwen3-vl-4b": "repair",
        }
        for key, action in expected.items():
            with self.subTest(key=key):
                spec = self.registry.resolve(key, by_key=True)
                self.assertEqual(action, spec.command[-1])
                self.assertNotIn("powershell", " ".join(spec.command).casefold())
                self.assertNotIn("cmd.exe", " ".join(spec.command).casefold())


if __name__ == "__main__":
    unittest.main()
