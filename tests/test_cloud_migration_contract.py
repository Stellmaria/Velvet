from __future__ import annotations

import unittest
from pathlib import Path


class CloudMigrationContractTests(unittest.TestCase):
    def test_production_compose_does_not_run_local_models_or_mount_docker_socket(self) -> None:
        compose = Path("docker-compose.yml").read_text(encoding="utf-8")
        self.assertNotIn("ollama/ollama", compose)
        self.assertNotIn("velvet_ollama_data", compose)
        self.assertNotIn("/var/run/docker.sock", compose)
        self.assertIn("nousresearch/hermes-agent:latest", compose)
        self.assertIn('command: ["gateway", "run"]', compose)

    def test_roleplay_client_has_no_local_ollama_path(self) -> None:
        source = Path("velvet_bot/domains/roleplay/client.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('"ollama"', source)
        self.assertNotIn("/api/chat", source)
        self.assertNotIn("get_local_ai_lock", source)
        self.assertIn("/chat/completions", source)
        self.assertIn("/responses", source)

    def test_public_environment_example_has_no_local_model_runtime(self) -> None:
        example = Path(".env.example").read_text(encoding="utf-8")
        normalized = example.casefold()
        self.assertNotIn("ollama_", normalized)
        self.assertNotIn("qwen3-vl", normalized)
        self.assertNotIn("hf.co/mradermacher", normalized)
        self.assertIn("byesu_api_key", normalized)
        self.assertIn("ai_text_provider=openai_compatible", normalized)
        self.assertIn("ai_vision_provider=openai_compatible", normalized)
        self.assertIn("kie_wan_27_image_model=wan/2-7-image", normalized)
        self.assertIn(
            "kie_wan_27_image_pro_model=wan/2-7-image-pro",
            normalized,
        )
        self.assertNotIn("kie_qwen2_image_edit_model", normalized)
        self.assertNotIn("kie_flux_2_pro_image_model", normalized)

    def test_secret_files_are_excluded_from_git_and_docker_context(self) -> None:
        gitignore = Path(".gitignore").read_text(encoding="utf-8")
        dockerignore = Path(".dockerignore").read_text(encoding="utf-8")
        self.assertIn(".env*", gitignore)
        self.assertIn(".env.*", dockerignore)
        self.assertIn(".codex/", gitignore)
        self.assertIn(".hermes/", gitignore)
        self.assertIn(".codex", dockerignore)
        self.assertIn(".hermes", dockerignore)

    def test_agent_templates_and_deployment_runbook_exist(self) -> None:
        required = (
            Path(".env.hermes.example"),
            Path("deploy/hermes/config.yaml.example"),
            Path("deploy/hermes/SOUL.md.example"),
            Path("deploy/codex/config.toml.example"),
            Path("deploy/server/deploy.sh"),
            Path("docs/CLOUD_MIGRATION.md"),
            Path("scripts/remove_local_qwen.ps1"),
        )
        self.assertTrue(all(path.is_file() for path in required))


if __name__ == "__main__":
    unittest.main()
