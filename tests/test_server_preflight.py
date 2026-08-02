from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.server_preflight import (
    main,
    parse_env_file,
    validate_server_environment,
)


def _valid_values(data_dir: str) -> dict[str, str]:
    password = "test_postgres_password_1234567890"
    return {
        "VELVET_DATA_DIR": data_dir,
        "BOT_TOKEN": "123456:test_bot_token_12345678",
        "DATABASE_URL": (
            "postgresql://velvet:test_postgres_password_1234567890@postgres:5432/velvet"
        ),
        "POSTGRES_DB": "velvet",
        "POSTGRES_USER": "velvet",
        "POSTGRES_PASSWORD": password,
        "ALLOWED_USER_IDS": "123456789",
        "STORAGE_ENCRYPTION_ACTIVE_KEY_ID": "backup-active",
        "STORAGE_ENCRYPTION_SECRET": "test_storage_key_material_12345678901234567890",
        "SUPERVISOR_TOKEN": "test_supervisor_token_1234567890123456",
        "SUPERVISOR_ALLOW_REMOTE": "false",
        "KRITA_WATERMARK_ENABLED": "false",
        "AI_BUDGET_ENABLED": "true",
        "AI_DAILY_BUDGET_RUB": "500",
        "AI_MONTHLY_BUDGET_RUB": "5000",
        "AI_MAX_REQUEST_RUB": "250",
        "AI_HERMES_RESERVE_RUB": "300",
        "AI_TEXT_ENABLED": "false",
        "AI_VISION_ENABLED": "false",
        "AI_VISION_QUEUE_ENABLED": "false",
        "KIE_ENABLED": "false",
        "HERMES_INCIDENT_ENABLED": "false",
        "CODEX_ENABLED": "false",
        "STORAGE_MIGRATE_ON_START": "false",
    }


class ServerPreflightTests(unittest.TestCase):
    def test_valid_first_boot_configuration_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = validate_server_environment(
                _valid_values(directory),
                check_permissions=False,
            )
        self.assertTrue(report.ok, report.errors)

    def test_database_must_use_internal_postgres_host(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _valid_values(directory)
            values["DATABASE_URL"] = values["DATABASE_URL"].replace(
                "@postgres:", "@localhost:"
            )
            report = validate_server_environment(values, check_permissions=False)
        self.assertFalse(report.ok)
        self.assertTrue(any("сервису postgres" in item for item in report.errors))

    def test_queue_mode_requires_vision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _valid_values(directory)
            values["AI_VISION_QUEUE_ENABLED"] = "true"
            report = validate_server_environment(values, check_permissions=False)
        self.assertTrue(any("AI_VISION_ENABLED" in item for item in report.errors))

    def test_cloud_text_model_requires_price_and_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _valid_values(directory)
            values.update(
                {
                    "AI_TEXT_ENABLED": "true",
                    "AI_TEXT_PROVIDER": "openai_compatible",
                    "AI_TEXT_BASE_URL": "https://provider.invalid/v1",
                    "AI_TEXT_MODEL": "rp-model",
                    "AI_TEXT_INPUT_RUB_PER_1M": "",
                    "AI_TEXT_OUTPUT_RUB_PER_1M": "",
                }
            )
            report = validate_server_environment(values, check_permissions=False)
        self.assertTrue(any("API_KEY" in item for item in report.errors))
        self.assertTrue(any("цену" in item for item in report.errors))

    def test_ollama_text_provider_is_rejected_on_server(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _valid_values(directory)
            values.update(
                {
                    "AI_TEXT_ENABLED": "true",
                    "AI_TEXT_PROVIDER": "ollama",
                    "AI_TEXT_BASE_URL": "http://127.0.0.1:11434",
                    "AI_TEXT_MODEL": "legacy-model",
                    "AI_TEXT_INPUT_RUB_PER_1M": "1",
                    "AI_TEXT_OUTPUT_RUB_PER_1M": "1",
                }
            )
            report = validate_server_environment(values, check_permissions=False)
        self.assertTrue(any("legacy/deprecated" in item for item in report.errors))

    def test_ollama_vision_provider_is_rejected_on_server(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _valid_values(directory)
            values.update(
                {
                    "AI_VISION_ENABLED": "true",
                    "AI_VISION_PROVIDER": "ollama",
                    "AI_VISION_BASE_URL": "http://127.0.0.1:11434",
                    "AI_VISION_MODEL": "legacy-vl",
                    "AI_VISION_FLASH_INPUT_RUB_PER_1M": "1",
                    "AI_VISION_FLASH_OUTPUT_RUB_PER_1M": "1",
                }
            )
            report = validate_server_environment(values, check_permissions=False)
        self.assertTrue(any("legacy/deprecated" in item for item in report.errors))

    def test_media_generation_requires_kie_and_grs_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _valid_values(directory)
            values.update(
                {
                    "KIE_ENABLED": "true",
                    "KIE_API_KEY": "kie_secret_123456789",
                    "KIE_BASE_URL": "https://api.kie.ai/api/v1",
                    "KIE_FILE_UPLOAD_BASE_URL": "https://upload.invalid",
                    "GRS_API_KEY": "",
                    "GRS_BASE_URL": "https://grsaiapi.com",
                    "KIE_SEEDREAM_5_PRO_TEXT_MODEL": "seedream/5-pro-text-to-image",
                    "KIE_SEEDREAM_5_PRO_IMAGE_MODEL": "seedream/5-pro-image-to-image",
                    "KIE_QWEN2_IMAGE_EDIT_MODEL": "qwen2/image-edit",
                    "KIE_WAN_27_IMAGE_MODEL": "wan/2-7-image",
                    "KIE_FLUX_2_PRO_IMAGE_MODEL": "flux-2/pro-image-to-image",
                    "GRS_NANO_BANANA_2_MODEL": "nano-banana-2",
                    "GRS_NANO_BANANA_PRO_MODEL": "nano-banana-pro",
                    "KIE_GROK_IMAGINE_IMAGE_TO_VIDEO_MODEL": "grok-imagine/image-to-video",
                    "KIE_GROK_IMAGINE_VIDEO_15_MODEL": "grok-imagine-video-1-5-preview",
                    "KIE_SEEDANCE_15_PRO_MODEL": "bytedance/seedance-1.5-pro",
                    "KIE_WAN_27_IMAGE_TO_VIDEO_MODEL": "wan/2-7-image-to-video",
                    "KIE_USD_TO_RUB": "",
                }
            )
            report = validate_server_environment(values, check_permissions=False)
        self.assertTrue(any("GRS_API_KEY" in item for item in report.errors))
        self.assertTrue(any("KIE_USD_TO_RUB" in item for item in report.errors))

    def test_hermes_requires_different_token_and_matching_internal_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _valid_values(directory)
            values.update(
                {
                    "HERMES_INCIDENT_ENABLED": "true",
                    "HERMES_BASE_URL": "http://hermes:8642",
                    "HERMES_API_KEY": "bot_side_internal_key_123456",
                }
            )
            hermes = {
                "OPENAI_API_KEY": "provider_key_123456",
                "TELEGRAM_BOT_TOKEN": values["BOT_TOKEN"],
                "TELEGRAM_ALLOWED_USERS": "123456789",
                "GH_TOKEN": "github_key_123456",
                "API_SERVER_KEY": "different_internal_key_123456",
            }
            report = validate_server_environment(
                values,
                hermes_values=hermes,
                check_permissions=False,
            )
        self.assertTrue(any("разные Telegram" in item for item in report.errors))
        self.assertTrue(any("не совпадает" in item for item in report.errors))

    def test_parse_env_supports_quotes_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.server"
            path.write_text(
                "export BOT_TOKEN='123:abc'\nPOSTGRES_DB=\"velvet\"\n# ignored\n",
                encoding="utf-8",
            )
            values = parse_env_file(path)
        self.assertEqual("123:abc", values["BOT_TOKEN"])
        self.assertEqual("velvet", values["POSTGRES_DB"])

    def test_cli_does_not_print_secret_values(self) -> None:
        leaked_token = "test_secret_value_that_must_never_appear_123"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.server"
            values = _valid_values(directory)
            values["BOT_TOKEN"] = leaked_token
            values["POSTGRES_PASSWORD"] = "short"
            path.write_text(
                "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
                encoding="utf-8",
            )
            if os.name != "nt":
                path.chmod(0o600)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr), patch(
                "scripts.server_preflight.check_host_tools"
            ):
                code = main(
                    [
                        "--env-file",
                        str(path),
                        "--hermes-env",
                        str(Path(directory) / "missing-hermes"),
                        "--skip-host-tools",
                    ]
                )
        output = stdout.getvalue() + stderr.getvalue()
        self.assertEqual(1, code)
        self.assertNotIn(leaked_token, output)
        self.assertNotIn(values["STORAGE_ENCRYPTION_SECRET"], output)


if __name__ == "__main__":
    unittest.main()
