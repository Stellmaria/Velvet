from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.domains.workspaces.onboarding import (
    DESTINATION_SPECS,
    WORKSPACE_DESTINATION_KEYS,
    onboarding_readiness,
    required_destination_keys,
)


class WorkspaceOnboardingRulesTests(unittest.TestCase):
    def test_archive_modules_require_only_main_archive_destination(self) -> None:
        self.assertEqual(
            ("characters",),
            required_destination_keys({"characters", "archive"}),
        )

    def test_optional_modules_do_not_add_required_destinations(self) -> None:
        self.assertEqual(
            ("characters",),
            required_destination_keys(
                {
                    "characters",
                    "archive",
                    "references",
                    "public_archive",
                    "publications",
                    "analytics",
                }
            ),
        )
        self.assertEqual((), required_destination_keys({"taxonomy", "team"}))

    def test_readiness_requires_guide_modules_and_main_archive(self) -> None:
        result = onboarding_readiness(
            modules_confirmed=False,
            guide_viewed=False,
            enabled_modules={"characters", "archive", "references"},
            configured_destinations={"characters"},
        )
        self.assertFalse(result.ready)
        self.assertEqual(
            (
                "Откройте краткий гид по работе пространства.",
                "Подтвердите выбранные модули.",
            ),
            result.missing_steps,
        )

    def test_readiness_accepts_main_archive_without_optional_chats(self) -> None:
        result = onboarding_readiness(
            modules_confirmed=True,
            guide_viewed=True,
            enabled_modules={"characters", "archive", "references"},
            configured_destinations={"characters"},
        )
        self.assertTrue(result.ready)
        self.assertEqual((), result.missing_steps)

    def test_every_destination_has_command_and_description(self) -> None:
        self.assertEqual(set(WORKSPACE_DESTINATION_KEYS), set(DESTINATION_SPECS))
        for key, spec in DESTINATION_SPECS.items():
            self.assertIn(key, spec.command_hint)
            self.assertTrue(spec.description)
            self.assertTrue(spec.label)

    def test_character_destination_requires_forum_topic_management(self) -> None:
        spec = DESTINATION_SPECS["characters"]
        self.assertTrue(spec.requires_forum_admin)
        self.assertIn("персональную тему", spec.description)


class WorkspaceOnboardingSourceContractTests(unittest.TestCase):
    def test_migration_persists_progress_and_forum_threads(self) -> None:
        migration = Path("migrations/910_workspace_first_run_wizard.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_onboarding", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_destinations", migration)
        self.assertIn("message_thread_id BIGINT", migration)
        self.assertIn("modules_confirmed BOOLEAN", migration)
        self.assertIn("guide_viewed BOOLEAN", migration)
        self.assertIn("can_manage_topics BOOLEAN", migration)

    def test_onboarding_router_precedes_legacy_workspace_form(self) -> None:
        bundle = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        onboarding = bundle.index("router.include_router(workspace_onboarding_router)")
        legacy = bundle.index("router.include_router(workspaces_router)")
        self.assertLess(onboarding, legacy)

    def test_router_exposes_setup_bind_status_and_guide(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/workspace_onboarding.py"
        ).read_text(encoding="utf-8")
        for command in (
            'Command("workspace_setup")',
            'Command("workspace_guide")',
            'Command("workspace_setup_status")',
            'Command("workspace_bind")',
            'Command("workspace_unbind")',
        ):
            self.assertIn(command, source)
        self.assertIn("WorkspaceForm.waiting_workspace_name", source)
        self.assertIn("get_chat_member", source)
        self.assertIn("message.message_thread_id", source)
        self.assertIn("должно быть форумной супергруппой", source)
        self.assertIn("can_manage_topics", source)


if __name__ == "__main__":
    unittest.main()
