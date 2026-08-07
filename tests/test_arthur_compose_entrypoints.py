from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "hermes-librarian" / "compose.yaml"


class ArthurComposeEntrypointTests(unittest.TestCase):
    def test_arthur_services_use_module_execution_from_image_workdir(self) -> None:
        payload = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        services = payload["services"]
        self.assertEqual(
            ["python", "-m", "scripts.run_arthur_storage_gateway"],
            services["arthur-storage-gateway"]["command"],
        )
        self.assertEqual(
            ["python", "-m", "scripts.run_arthur_librarian"],
            services["arthur"]["command"],
        )

    def test_arthur_modules_and_velvet_package_are_resolvable_from_repo_root(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("scripts.run_arthur_storage_gateway"))
        self.assertIsNotNone(importlib.util.find_spec("scripts.run_arthur_librarian"))
        self.assertIsNotNone(importlib.util.find_spec("velvet_bot"))


if __name__ == "__main__":
    unittest.main()
