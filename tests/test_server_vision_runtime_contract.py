from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.server.yml").read_text(encoding="utf-8")
RUNTIME_DOCKERFILE = (ROOT / "Dockerfile.vision-runtime").read_text(encoding="utf-8")
GATEWAY_DOCKERFILE = (ROOT / "Dockerfile.vision-gateway").read_text(encoding="utf-8")
ENTRYPOINT = (ROOT / "scripts" / "vision_runtime_entrypoint.sh").read_text(
    encoding="utf-8"
)


def _service_block(name: str, next_name: str) -> str:
    pattern = rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  {re.escape(next_name)}:|^networks:)"
    match = re.search(pattern, COMPOSE, flags=re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"Missing service block: {name}")
    return match.group("body")


class ServerVisionRuntimeContractTests(unittest.TestCase):
    def test_runtime_and_gateway_are_profile_gated_without_public_ports(self) -> None:
        runtime = _service_block("vision-runtime", "vision-gateway")
        gateway = _service_block("vision-gateway", "krita")
        for block in (runtime, gateway):
            self.assertIn('profiles: ["vision"]', block)
            self.assertNotIn("ports:", block)
            self.assertIn("cap_drop:\n      - ALL", block)
            self.assertIn("no-new-privileges:true", block)
            self.assertIn("read_only: true", block)

    def test_networks_prevent_bot_from_reaching_vendor_runtime(self) -> None:
        bot = _service_block("bot", "vision-runtime")
        runtime = _service_block("vision-runtime", "vision-gateway")
        gateway = _service_block("vision-gateway", "krita")
        self.assertIn("- vision-front", bot)
        self.assertNotIn("- vision-back", bot)
        self.assertIn("- vision-back", runtime)
        self.assertNotIn("- vision-front", runtime)
        self.assertIn("- vision-front", gateway)
        self.assertIn("- vision-back", gateway)
        self.assertIn("vision-front:\n    driver: bridge\n    internal: true", COMPOSE)
        self.assertIn("vision-back:\n    driver: bridge\n    internal: true", COMPOSE)

    def test_runtime_image_and_model_are_version_pinned(self) -> None:
        self.assertIn("ollama/ollama:0.32.3", RUNTIME_DOCKERFILE)
        self.assertNotIn("ollama/ollama:latest", RUNTIME_DOCKERFILE)
        self.assertIn("VISION_MODEL_EXPECTED_DIGEST", ENTRYPOINT)
        self.assertIn("ollama pull", ENTRYPOINT)
        self.assertIn("ollama list", ENTRYPOINT)

    def test_gateway_has_no_runtime_volume_or_production_env_file(self) -> None:
        gateway = _service_block("vision-gateway", "krita")
        self.assertNotIn("env_file:", gateway)
        self.assertNotIn("volumes:", gateway)
        self.assertIn("VISION_RUNTIME_BASE_URL: http://vision-runtime:11434", gateway)

    def test_gateway_runs_as_unprivileged_user(self) -> None:
        self.assertIn("USER 10001:10001", GATEWAY_DOCKERFILE)
        self.assertIn("requirements.vision-gateway.txt", GATEWAY_DOCKERFILE)


if __name__ == "__main__":
    unittest.main()
