from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLISH = ROOT / ".github" / "workflows" / "publish-vision-gateway-image.yml"
DEPLOY = ROOT / ".github" / "workflows" / "deploy-production-vision-gateway.yml"
SCRIPT = ROOT / "deploy" / "server" / "deploy-vision-gateway.sh"


class VisionGatewayDeliveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.publish = PUBLISH.read_text(encoding="utf-8")
        cls.deploy = DEPLOY.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_publish_workflow_tracks_only_gateway_delivery_surface(self) -> None:
        self.assertIn('      - "vision_gateway/**"', self.publish)
        self.assertIn('      - "Dockerfile.vision-gateway"', self.publish)
        self.assertIn('      - "requirements.vision-gateway.txt"', self.publish)
        self.assertIn(
            '      - ".github/workflows/publish-vision-gateway-image.yml"',
            self.publish,
        )
        self.assertIn("workflow_dispatch:", self.publish)
        self.assertIn(
            "IMAGE_REPOSITORY: ghcr.io/stellmaria/velvet-vision-gateway",
            self.publish,
        )
        self.assertNotIn("IMAGE_REPOSITORY: ghcr.io/stellmaria/velvet\n", self.publish)

    def test_publish_workflow_records_verified_provenance(self) -> None:
        required = (
            "--file Dockerfile.vision-gateway",
            "org.opencontainers.image.revision=${GITHUB_SHA}",
            "org.opencontainers.image.component=vision-gateway",
            "CRITICAL,HIGH",
            "published-vision-gateway-sbom.cdx.json",
            "published-vision-gateway-metadata.json",
            "requirements.vision-gateway.txt",
            "ghcr\\.io/stellmaria/velvet-vision-gateway@sha256:[0-9a-f]{64}",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.publish)

    def test_deploy_workflow_is_manual_serialized_and_exact_main_only(self) -> None:
        self.assertIn("workflow_dispatch:", self.deploy)
        self.assertNotIn("\n  push:", self.deploy)
        self.assertNotIn("\n  pull_request:", self.deploy)
        self.assertIn("group: velvet-production", self.deploy)
        self.assertIn("environment: production", self.deploy)
        self.assertIn("inputs.confirmation == 'DEPLOY_VISION_GATEWAY'", self.deploy)
        self.assertIn("github.ref == 'refs/heads/main'", self.deploy)
        self.assertIn('"$source_commit" != "${GITHUB_SHA,,}"', self.deploy)
        self.assertIn(
            "ghcr\\.io/stellmaria/velvet-vision-gateway@sha256:[0-9a-f]{64}",
            self.deploy,
        )

    def test_deploy_workflow_streams_checked_in_gateway_script(self) -> None:
        self.assertIn("< deploy/server/deploy-vision-gateway.sh", self.deploy)
        self.assertIn("VELVET_GATEWAY_SOURCE_COMMIT=%q", self.deploy)
        self.assertIn("VELVET_GATEWAY_IMAGE=%q", self.deploy)
        self.assertNotIn("deploy/server/deploy.sh", self.deploy)

    def test_deploy_script_is_valid_bash(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_deploy_script_uses_exact_source_snapshot_and_image_provenance(self) -> None:
        required = (
            'git archive "$SOURCE_COMMIT"',
            'git merge-base --is-ancestor "$SOURCE_COMMIT" "$remote_head"',
            'org.opencontainers.image.revision',
            'org.opencontainers.image.component',
            '"$image_component" != "vision-gateway"',
            '"${image_revision,,}" != "${SOURCE_COMMIT,,}"',
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.script)

    def test_deploy_script_is_gateway_only_and_rollback_safe(self) -> None:
        required = (
            "velvet-vision-gateway:rollback-",
            "restore_env",
            "VISION_GATEWAY_IMAGE=",
            "--no-deps --no-build --pull never vision-gateway",
            'bot_cid_before=',
            'runtime_cid_before=',
            '"$bot_cid_after" != "$bot_cid_before"',
            '"$runtime_cid_after" != "$runtime_cid_before"',
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.script)
        self.assertNotIn(" up -d vision-runtime", self.script)
        self.assertNotIn(" up -d bot", self.script)


if __name__ == "__main__":
    unittest.main()
