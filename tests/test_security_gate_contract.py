from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "security_gate.py"
SECURITY_WORKFLOW = ROOT / ".github" / "workflows" / "security.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish-image.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-production.yml"
DEPLOY_SCRIPT = ROOT / "deploy" / "server" / "deploy.sh"
FAKE_SECRET = ROOT / "tests" / "fixtures" / "security" / "fake-secret.txt"
VULNERABLE_REQUIREMENTS = (
    ROOT / "tests" / "fixtures" / "security" / "vulnerable-requirements.txt"
)


def _load_gate():
    spec = importlib.util.spec_from_file_location("security_gate", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load security gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = _load_gate()


class SecurityGateContractTests(unittest.TestCase):
    def test_repository_actions_are_immutable_and_permissions_are_explicit(self) -> None:
        self.assertEqual([], GATE.check_action_pins())

    def test_repository_dependency_graph_is_hash_locked(self) -> None:
        self.assertEqual([], GATE.check_dependency_locks())

    def test_repository_security_exceptions_are_valid_and_unexpired(self) -> None:
        self.assertEqual([], GATE.check_security_exceptions())

    def test_floating_action_tag_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "floating.yml"
            workflow.write_text(
                "name: bad\non:\n  pull_request:\npermissions:\n  contents: read\n"
                "jobs:\n  bad:\n    runs-on: ubuntu-latest\n    steps:\n"
                "      - uses: actions/checkout@v7\n",
                encoding="utf-8",
            )
            errors = GATE.check_action_pins((workflow,))
        self.assertTrue(any("40-character commit SHA" in error for error in errors))

    def test_dependency_without_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "requirements.lock"
            lock.write_text("urllib3==2.6.3\n", encoding="utf-8")
            errors = GATE.check_lock_file(lock)
        self.assertTrue(any("has no sha256 hash" in error for error in errors))

    def test_fake_secret_fixture_is_detected(self) -> None:
        errors = GATE.detect_secrets(FAKE_SECRET)
        self.assertTrue(any("AWS access key" in error for error in errors))

    def test_expired_exception_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".github" / "security-exceptions.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "exceptions": [
                            {
                                "id": "CVE-test",
                                "owner": "security@example.invalid",
                                "reason": "contract fixture",
                                "expires": "2025-01-01",
                                "test_reference": "tests/test_security_gate_contract.py",
                                "source": "pip-audit",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            errors = GATE.check_security_exceptions(root=root, today=date(2026, 8, 2))
        self.assertTrue(any("expired" in error for error in errors))

    def test_vulnerable_fixture_is_isolated_and_audited(self) -> None:
        fixture = VULNERABLE_REQUIREMENTS.read_text(encoding="utf-8")
        workflow = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        production_inputs = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("urllib3==1.25.2", fixture)
        self.assertNotIn("urllib3==1.25.2", production_inputs)
        self.assertIn("pip-audit", workflow)
        self.assertIn("tests/fixtures/security/vulnerable-requirements.txt", workflow)
        self.assertIn("Expected the intentionally vulnerable fixture to be rejected", workflow)

    def test_security_workflow_uses_no_production_secrets_on_pr(self) -> None:
        source = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", source)
        self.assertIn("push:\n    branches:\n      - main", source)
        self.assertNotIn("${{ secrets.", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("security-events: write", source)

    def test_security_evidence_has_bounded_retention(self) -> None:
        source = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("retention-days:"), 3)
        self.assertNotIn("runtime/", source)
        self.assertNotIn("backups/", source)

    def test_publish_scans_before_pushing_and_records_provenance(self) -> None:
        source = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
        scan_index = source.index("Block high and critical findings before publish")
        push_index = source.index('docker push "$tag"')
        self.assertLess(scan_index, push_index)
        self.assertIn("severity: CRITICAL,HIGH", source)
        self.assertIn("org.opencontainers.image.revision=${GITHUB_SHA}", source)
        self.assertIn("published-image-sbom.cdx.json", source)
        self.assertIn("requirements_lock_sha256", source)
        self.assertIn("packages: write", source)
        self.assertNotIn("pull_request:", source)

    def test_production_deploy_requires_digest_and_matching_revision(self) -> None:
        workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
        digest_pattern = "ghcr\\.io/stellmaria/velvet@sha256:[0-9a-f]{64}"
        self.assertIn("source_commit:", workflow)
        self.assertIn("image_digest:", workflow)
        self.assertIn("source_commit must equal the main commit", workflow)
        self.assertIn(digest_pattern, workflow)
        self.assertIn("VELVET_DEPLOY_IMAGE", workflow)
        self.assertIn(digest_pattern, script)
        self.assertIn("org.opencontainers.image.revision", script)
        self.assertIn("Running image mismatch", script)
        self.assertIn('docker pull "$IMAGE_OVERRIDE"', script)


if __name__ == "__main__":
    unittest.main()
