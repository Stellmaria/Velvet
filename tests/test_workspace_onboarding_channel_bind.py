from __future__ import annotations

import unittest
from pathlib import Path


class WorkspaceOnboardingChannelBindContractTests(unittest.TestCase):
    def test_private_channel_binding_command_is_registered_before_workspace_router(self) -> None:
        bundle = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        channel_bind = bundle.index(
            "router.include_router(workspace_onboarding_channel_bind_router)"
        )
        workspace = bundle.index("router.include_router(workspaces_router)")
        self.assertLess(channel_bind, workspace)

    def test_private_channel_binding_checks_chat_and_bot_membership(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/"
            "workspace_onboarding_channel_bind.py"
        ).read_text(encoding="utf-8")
        self.assertIn('Command("workspace_bind_channel")', source)
        self.assertIn("bot.get_chat", source)
        self.assertIn("bot.get_chat_member", source)
        self.assertIn("can_post_messages", source)
        self.assertIn("workspace_service.configure_channel", source)

    def test_migration_blocks_cross_workspace_chat_reuse(self) -> None:
        migration = Path("migrations/910_workspace_first_run_wizard.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("enforce_workspace_destination_chat_ownership", migration)
        self.assertIn("pg_advisory_xact_lock", migration)
        self.assertIn("destination.workspace_id <> NEW.workspace_id", migration)
        self.assertIn("channel.workspace_id <> NEW.workspace_id", migration)


if __name__ == "__main__":
    unittest.main()
