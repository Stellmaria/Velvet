from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VLQualityWorkerGateTests(unittest.TestCase):
    def test_background_quality_worker_is_behind_explicit_gate(self) -> None:
        source = (ROOT / "velvet_bot/app/workers.py").read_text(encoding="utf-8")
        gate = 'if _env_enabled("AI_QUALITY_ENABLED"):'
        service = "quality_service = CalibratedAIQualityService("
        registration = 'name="ai-quality"'

        self.assertIn(gate, source)
        self.assertIn(service, source)
        self.assertIn(registration, source)
        self.assertLess(source.index(gate), source.index(service))
        self.assertLess(source.index(service), source.index(registration))
        self.assertIn("if quality_service is not None:", source)

    def test_quality_gate_defaults_to_disabled_in_env_examples(self) -> None:
        for relative_path in (".env.server.example", ".env.vision-local.example"):
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("AI_QUALITY_ENABLED=false", source, relative_path)


if __name__ == "__main__":
    unittest.main()
