from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "deploy/hermes-operator/gateway.py"
SPEC = importlib.util.spec_from_file_location("hermes_operator_gateway_redaction", PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load Hermes operator gateway")
GATEWAY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATEWAY
SPEC.loader.exec_module(GATEWAY)


class HermesOperatorRedactionTests(unittest.TestCase):
    def test_recursive_redaction_covers_keys_and_log_strings(self) -> None:
        secret_a = "secret-value-123456"
        secret_b = "bearer-value-123456"
        payload = {
            "token": secret_a,
            "logs": [
                f"API_KEY={secret_a}",
                f"Authorization: Bearer {secret_b}",
                {"message": f"password: {secret_a}"},
            ],
        }

        result = GATEWAY._redact(payload)
        rendered = repr(result)

        self.assertEqual(result["token"], "[redacted]")
        self.assertNotIn(secret_a, rendered)
        self.assertNotIn(secret_b, rendered)
        self.assertIn("[redacted]", rendered)

    def test_start_client_timeout_includes_command_and_health_budget(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "HERMES_OPS_HOST_TOKEN": "x" * 24,
                "HERMES_OPS_HOST_SOCKET": "/tmp/hermes-start.sock",
                "HERMES_OPS_START_TIMEOUT_SECONDS": "300",
                "HERMES_OPS_START_HEALTH_ATTEMPTS": "60",
                "HERMES_OPS_START_HEALTH_INTERVAL": "2",
            },
            clear=False,
        ):
            client = GATEWAY.HostStartClient()

        self.assertEqual(client.timeout, 450)


if __name__ == "__main__":
    unittest.main()
