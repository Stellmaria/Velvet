from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "reconcile-production-librarian.yml"


class ProductionLibrarianReconcileWorkflowContractTests(unittest.TestCase):
    def test_workflow_is_manual_main_only_and_uses_production_environment(
        self,
    ) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", source)
        self.assertIn("confirmation:", source)
        self.assertIn("RECONCILE_LIBRARIAN", source)
        self.assertIn("source_commit:", source)
        self.assertIn("image_digest:", source)
        self.assertIn("github.ref == 'refs/heads/main'", source)
        self.assertIn("environment: production", source)
        self.assertIn("group: velvet-production", source)
        self.assertIn("contents: read", source)
        self.assertNotIn("pull_request:", source)
        self.assertNotIn("push:\n", source)

    def test_workflow_separates_application_source_from_current_checkout(
        self,
    ) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        digest_pattern = "ghcr\\.io/stellmaria/velvet@sha256:[0-9a-f]{64}"

        self.assertIn("Exact deployed application source commit", source)
        self.assertIn(digest_pattern, source)
        self.assertIn("CHECKOUT_COMMIT: ${{ github.sha }}", source)
        self.assertIn(
            'git merge-base --is-ancestor "$SOURCE_COMMIT" "$CHECKOUT_COMMIT"',
            source,
        )
        self.assertIn("org.opencontainers.image.revision", source)
        self.assertIn('test "${image_revision,,}" = "${SOURCE_COMMIT,,}"', source)
        self.assertNotIn("source_commit must equal the current main commit", source)

    def test_workflow_allows_only_control_plane_checkout_drift(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        safe_diff_index = source.index(".github/*|docs/*|tests/*")
        reset_index = source.index('git reset --hard "$CHECKOUT_COMMIT"')
        self.assertLess(safe_diff_index, reset_index)
        self.assertIn("runtime/deploy change after the verified application source", source)
        self.assertIn("Run the normal verified production deploy", source)
        self.assertIn('"$SOURCE_COMMIT"|"$CHECKOUT_COMMIT"', source)
        self.assertIn("--untracked-files=all", source)
        self.assertIn('git rev-parse refs/remotes/origin/main)" = "$CHECKOUT_COMMIT"', source)

    def test_workflow_requires_the_core_bot_to_prove_image_provenance(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn(
            'docker inspect --format \'{{.Config.Image}}\' "$bot_cid"',
            source,
        )
        self.assertIn('docker image inspect "$IMAGE_DIGEST"', source)
        self.assertIn("expected_image_id", source)
        self.assertIn("Verified healthy production bot", source)

    def test_workflow_pins_image_before_librarian_only_reconcile(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        pin_index = source.index('result.append(f"VELVET_IMAGE={expected_image}")')
        submit_index = source.index("reconcilectl.py submit librarian")
        self.assertLess(pin_index, submit_index)
        self.assertIn("os.replace(temporary, path)", source)
        self.assertIn("STORAGE_LIBRARIAN_AUTO_ENQUEUE must remain false", source)
        self.assertIn('payload.get("status") != "completed"', source)
        self.assertNotIn("reconcilectl.py submit all", source)
        self.assertNotIn("STORAGE_LIBRARIAN_AUTO_ENQUEUE=true", source)

    def test_workflow_verifies_arthur_runtime_and_text_budget(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("arthur-storage-gateway|arthur", source)
        self.assertIn("unexpected published port", source)
        self.assertIn("Arthur automatic enqueue is not disabled", source)
        self.assertIn("Arthur heartbeat is missing", source)
        self.assertIn("StorageLibrarianSettings.from_env()", source)
        self.assertIn("settings.max_text_chars != 11_520", source)
        self.assertIn("effective_max_text_chars={settings.max_text_chars}", source)
        self.assertIn("ollama show velvet-librarian-text:v1", source)

    def test_workflow_repairs_git_index_without_force_or_mass_enqueue(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("repair_git_index", source)
        self.assertIn("--cap-add CHOWN", source)
        self.assertNotIn("git push --force", source)
        self.assertNotIn("enqueue-all", source)
        self.assertNotIn("mass enqueue", source.lower())


if __name__ == "__main__":
    unittest.main()
