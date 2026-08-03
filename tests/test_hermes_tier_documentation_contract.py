from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TierDocumentationContractTests(unittest.TestCase):
    def test_direct_codex_skill_requires_explicit_routing_metadata(self) -> None:
        source = (ROOT / "brain-vault/skills/codex-first/SKILL.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "--task-type <task_type>",
            "--complexity <complexity>",
            "--risk <risk>",
            "--mutation-policy <mutation_policy>",
            "--tier <requested_tier>",
            "selected_provider_route",
            "attempted_routes",
            "mutation_started",
        ):
            self.assertIn(marker, source)
        self.assertIn("не понижай", source)

    def test_canonical_kael_soul_contains_tier_policy(self) -> None:
        source = (ROOT / "deploy/hermes-operator/SOUL.kael.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "Tier-aware делегирование",
            "requested_tier",
            "small` → Codex Luna",
            "standard` → Codex Terra",
            "complex` и `high_risk` → Codex Sol",
            "degraded route",
            "production `.env`",
        ):
            self.assertIn(marker, source)

    def test_kael_runbook_has_no_legacy_unclassified_submit(self) -> None:
        source = (ROOT / "deploy/hermes-operator/AGENTS.kael.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(
            'coderctl.py submit velvet --source owner-request --task "<задача>"',
            source,
        )
        for marker in (
            "task_type",
            "complexity",
            "risk",
            "mutation_policy",
            "requested_tier",
            "--task-type read_only",
            "--task-type code",
            "--tier small",
            "--tier standard",
            "degraded Terra",
        ):
            self.assertIn(marker, source)

    def test_pr_gate_requires_route_evidence(self) -> None:
        source = (ROOT / "brain-vault/skills/coder-pr-gate/SKILL.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "selected_primary_model",
            "selected_provider_route",
            "attempted_models",
            "attempted_routes",
            "actual_route",
            "fallback_reason",
            "mutation_started",
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
