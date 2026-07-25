from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.presentation.telegram import workspace_archive_delivery_controller as delivery
from velvet_bot.presentation.telegram import workspace_archive_mutation_controller as mutation
from velvet_bot.presentation.telegram import workspace_archive_navigation_controller as navigation
from velvet_bot.presentation.telegram import workspace_archive_social_controller as social
from velvet_bot.presentation.telegram import workspace_media_policy_controller as policy
from velvet_bot.presentation.telegram.workspace_archive_access import (
    load_workspace_archive_action_page,
    resolve_workspace_archive_access,
)
from velvet_bot.presentation.telegram.workspace_archive_delivery_controller import (
    build_workspace_archive_delete_keyboard,
)
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    WorkspacePersonalArchiveAction,
)

ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "velvet_bot/presentation/telegram"


class WorkspaceArchiveActionCoverageTests(unittest.TestCase):
    def test_canonical_controllers_cover_every_legacy_wpa_action_once(self) -> None:
        groups = (
            navigation._NAVIGATION_ACTIONS,
            policy._MEDIA_POLICY_ACTIONS,
            social._SOCIAL_ACTIONS,
            mutation._MUTATION_ACTIONS,
            delivery._DELIVERY_ACTIONS,
        )
        expected = {
            "open",
            "show",
            "close",
            "empty",
            "help",
            "noop",
            "settings",
            "mediahelp",
            "dlaudnone",
            "dlaudall",
            "dlaudsub",
            "dlvarwm",
            "dlvarorig",
            "like",
            "sub",
            "watermark",
            "rework",
            "public",
            "adult",
            "blur",
            "download",
            "delete",
            "deleteconfirm",
        }
        union = set().union(*groups)

        self.assertEqual(expected, union)
        self.assertEqual(sum(len(group) for group in groups), len(union))

    def test_archive_registrar_installs_all_controllers_before_owner_router(self) -> None:
        controller = (
            PRESENTATION / "workspace_archive_dashboard_controller.py"
        ).read_text(encoding="utf-8")
        bundle = (
            PRESENTATION / "routers/archive_and_public.py"
        ).read_text(encoding="utf-8")

        for registration in (
            "register_workspace_archive_navigation(router)",
            "register_workspace_media_policy(router)",
            "register_workspace_archive_social_actions(router)",
            "register_workspace_archive_mutations(router)",
            "register_workspace_archive_delivery(router)",
        ):
            self.assertIn(registration, controller)
        archive_registration = bundle.index("register_workspace_archive_dashboard(router)")
        owner_router = bundle.index("router.include_router(workspace_owner_controls_router)")
        self.assertLess(archive_registration, owner_router)

    def test_new_archive_controllers_do_not_import_owner_controls(self) -> None:
        for name in (
            "workspace_archive_access.py",
            "workspace_archive_social_controller.py",
            "workspace_archive_mutation_controller.py",
            "workspace_archive_delivery_controller.py",
        ):
            source = (PRESENTATION / name).read_text(encoding="utf-8")
            self.assertNotIn("workspace_owner_controls", source, name)

    def test_navigation_uses_shared_access_boundary(self) -> None:
        source = (
            PRESENTATION / "workspace_archive_navigation_controller.py"
        ).read_text(encoding="utf-8")

        self.assertIn("resolve_workspace_archive_access", source)
        self.assertIn("load_workspace_archive_action_page", source)
        self.assertNotIn("def _resolve_workspace_archive_access", source)


class WorkspaceArchiveDeliveryPresentationTests(unittest.TestCase):
    def test_delete_keyboard_preserves_confirm_and_cancel_payloads(self) -> None:
        keyboard = build_workspace_archive_delete_keyboard(
            workspace_id=9,
            character_id=17,
            offset=4,
            media_id=31,
        )
        row = keyboard.inline_keyboard[0]

        self.assertEqual(["✅ Да, удалить", "↩️ Отмена"], [item.text for item in row])
        self.assertEqual("wpa:deleteconfirm:9:17:4:31", row[0].callback_data)
        self.assertEqual("wpa:show:9:17:4:31", row[1].callback_data)


class WorkspaceArchiveAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolver_returns_owner_access_for_workspace_owner(self) -> None:
        workspace = SimpleNamespace(id=9, is_system=False)
        workspace_service = SimpleNamespace(
            set_active_workspace=AsyncMock(return_value=workspace),
            resolve_active_workspace=AsyncMock(),
            require_role=AsyncMock(return_value=SimpleNamespace(role="owner")),
        )
        product_service = SimpleNamespace(
            is_module_enabled=AsyncMock(return_value=True),
        )

        resolved, owner_access = await resolve_workspace_archive_access(
            workspace_service=workspace_service,  # type: ignore[arg-type]
            workspace_product_service=product_service,  # type: ignore[arg-type]
            user_id=42,
            workspace_id=9,
        )

        self.assertIs(workspace, resolved)
        self.assertTrue(owner_access)
        workspace_service.set_active_workspace.assert_awaited_once()
        product_service.is_module_enabled.assert_awaited_once_with(
            workspace_id=9,
            module_key="archive",
        )

    async def test_page_loader_rejects_stale_media_id(self) -> None:
        callback = SimpleNamespace(answer=AsyncMock())
        action = WorkspacePersonalArchiveAction(
            action="blur",
            workspace_id=9,
            character_id=17,
            offset=4,
            media_id=31,
        )
        page = SimpleNamespace(media=SimpleNamespace(id=32))

        with patch(
            "velvet_bot.presentation.telegram.workspace_archive_access.get_archive_page",
            new=AsyncMock(return_value=page),
        ):
            result = await load_workspace_archive_action_page(
                callback,  # type: ignore[arg-type]
                action,
                SimpleNamespace(),  # type: ignore[arg-type]
                workspace=SimpleNamespace(id=9),  # type: ignore[arg-type]
            )

        self.assertIsNone(result)
        callback.answer.assert_awaited_once_with(
            "Архив изменился. Откройте материал заново.",
            show_alert=True,
        )


if __name__ == "__main__":
    unittest.main()
