from __future__ import annotations

import tempfile
import unittest

from scripts.server_preflight import validate_server_environment


def _values(data_dir: str) -> dict[str, str]:
    return {
        "VELVET_DATA_DIR": data_dir,
        "BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz_ABC123",
        "DATABASE_URL": (
            "postgresql://velvet:postgres_password_1234567890@postgres:5432/velvet"
        ),
        "POSTGRES_DB": "velvet",
        "POSTGRES_USER": "velvet",
        "POSTGRES_PASSWORD": "postgres_password_1234567890",
        "ALLOWED_USER_IDS": "123456789",
        "STORAGE_ENCRYPTION_SECRET": "storage_secret_12345678901234567890",
        "SUPERVISOR_TOKEN": "supervisor_secret_1234567890123456",
        "SUPERVISOR_ALLOW_REMOTE": "false",
        "KRITA_WATERMARK_ENABLED": "false",
        "AI_BUDGET_ENABLED": "true",
        "AI_DAILY_BUDGET_RUB": "500",
        "AI_MONTHLY_BUDGET_RUB": "5000",
        "AI_MAX_REQUEST_RUB": "250",
        "AI_HERMES_RESERVE_RUB": "300",
        "AI_TEXT_ENABLED": "false",
        "AI_VISION_ENABLED": "true",
        "AI_VISION_QUEUE_ENABLED": "false",
        "AI_VISION_PROVIDER": "local_openai_compatible",
        "AI_VISION_BASE_URL": "http://vision-gateway:8080/v1",
        "AI_VISION_MODEL": "qwen3-vl:8b-instruct-q4_K_M",
        "AI_VISION_FLASH_MODEL": "qwen3-vl:8b-instruct-q4_K_M",
        "AI_VISION_FLASH_INPUT_RUB_PER_1M": "0",
        "AI_VISION_FLASH_OUTPUT_RUB_PER_1M": "0",
        "KIE_ENABLED": "false",
        "HERMES_INCIDENT_ENABLED": "false",
        "CODEX_ENABLED": "false",
        "STORAGE_MIGRATE_ON_START": "false",
    }


class ServerLocalVisionContractTests(unittest.TestCase):
    def test_internal_local_route_passes_without_key_or_positive_pricing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = validate_server_environment(
                _values(directory),
                check_permissions=False,
            )
        self.assertTrue(report.ok, report.errors)

    def test_internal_provider_rejects_public_host(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _values(directory)
            values["AI_VISION_BASE_URL"] = "https://provider.example/v1"
            report = validate_server_environment(values, check_permissions=False)
        self.assertTrue(any("Compose host" in item for item in report.errors))

    def test_internal_provider_rejects_loopback_host(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _values(directory)
            values["AI_VISION_BASE_URL"] = "http://127.0.0.1:8080/v1"
            report = validate_server_environment(values, check_permissions=False)
        self.assertTrue(any("Compose host" in item for item in report.errors))

    def test_internal_route_rejects_positive_monetary_pricing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _values(directory)
            values["AI_VISION_FLASH_INPUT_RUB_PER_1M"] = "1"
            report = validate_server_environment(values, check_permissions=False)
        self.assertTrue(any("нулевую monetary" in item for item in report.errors))

    def test_provider_override_requires_its_own_base_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _values(directory)
            values.update(
                {
                    "AI_VISION_PRO_MODEL": "cloud-pro",
                    "AI_VISION_PRO_PROVIDER": "openai_compatible",
                    "AI_VISION_PRO_API_KEY": "cloud-key",
                    "AI_VISION_PRO_INPUT_RUB_PER_1M": "1",
                    "AI_VISION_PRO_OUTPUT_RUB_PER_1M": "1",
                }
            )
            report = validate_server_environment(values, check_permissions=False)
        self.assertTrue(any("отдельный AI_VISION_PRO_BASE_URL" in item for item in report.errors))


if __name__ == "__main__":
    unittest.main()
