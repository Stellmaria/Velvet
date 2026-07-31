from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from velvet_bot.app import media_delivery_ui_install as delivery_ui


class MediaDeliveryCallbackDependencyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.previous_installed = delivery_ui._INSTALLED
        delivery_ui._INSTALLED = False

    def tearDown(self) -> None:
        delivery_ui._INSTALLED = self.previous_installed

    def _install_handler(self):
        portal = SimpleNamespace(install_user_tasks_renderer=Mock())
        original_action = AsyncMock()
        require_auf_callback = AsyncMock(return_value=True)
        installed: dict[str, object] = {}

        def install_scoped_auf_handlers(*, action_handler=None, video_handler=None):
            del video_handler
            installed["handler"] = action_handler

        controller = SimpleNamespace(
            handle_scoped_auf_action=original_action,
            install_scoped_auf_handlers=install_scoped_auf_handlers,
            require_auf_callback=require_auf_callback,
        )

        def import_module(name: str):
            if name == "velvet_bot.app.auf_user_portal_install":
                return portal
            if name == "velvet_bot.presentation.telegram.workspace_home_controller":
                return controller
            raise AssertionError(f"Unexpected import: {name}")

        with patch.object(delivery_ui.importlib, "import_module", side_effect=import_module):
            delivery_ui.install_media_delivery_ui()

        return (
            installed["handler"],
            original_action,
            require_auf_callback,
        )

    async def test_legacy_nine_argument_fallback_remains_compatible(self) -> None:
        handler, original_action, _require = self._install_handler()
        callback = object()
        callback_data = SimpleNamespace(action="wallet", workspace_id=17, value=None)
        dependencies = tuple(object() for _ in range(7))

        await handler(callback, callback_data, *dependencies)

        original_action.assert_awaited_once_with(
            callback,
            callback_data,
            *dependencies,
        )

    async def test_delivery_action_accepts_nine_argument_callback_chain(self) -> None:
        handler, original_action, require_auf_callback = self._install_handler()
        callback = object()
        callback_data = SimpleNamespace(
            action="deliver",
            workspace_id=19,
            value="f95bd326-64e0-4689-873e-bc6e854542c8",
        )
        state = object()
        access_policy = object()
        kie_settings = object()
        database = object()
        ai_usage_service = object()
        ai_task_queue_service = object()
        auf_runtime_service = object()
        redeliver = AsyncMock()

        with patch.object(delivery_ui, "redeliver_owned_task", redeliver):
            await handler(
                callback,
                callback_data,
                state,
                access_policy,
                kie_settings,
                database,
                ai_usage_service,
                ai_task_queue_service,
                auf_runtime_service,
            )

        original_action.assert_not_awaited()
        require_auf_callback.assert_awaited_once_with(
            callback,
            workspace_id=19,
            service=auf_runtime_service,
        )
        redeliver.assert_awaited_once_with(
            callback,
            database=database,
            workspace_id=19,
            task_id_text="f95bd326-64e0-4689-873e-bc6e854542c8",
        )


if __name__ == "__main__":
    unittest.main()
