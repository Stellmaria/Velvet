from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.app import auf_photo_model_modes as photo_modes
from velvet_bot.app import auf_wallet_ui_install as wallet_ui
from velvet_bot.app import workspace_owner_generation_hotfix as generation_hotfix
from velvet_bot.domains.media_generation import KieModelAlias
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback


class AufGenerationCallbackChainTests(unittest.TestCase):
    def test_wallet_wrapper_forwards_complete_dependency_contract(self) -> None:
        received: list[object] = []

        async def downstream(
            callback,
            callback_data,
            state,
            access_policy,
            kie_settings,
            database,
            ai_usage_service,
            ai_task_queue_service,
            auf_runtime_service,
            auf_wallet_service,
            auf_purchase_service,
        ) -> None:
            received.extend(
                (
                    callback,
                    callback_data,
                    state,
                    access_policy,
                    kie_settings,
                    database,
                    ai_usage_service,
                    ai_task_queue_service,
                    auf_runtime_service,
                    auf_wallet_service,
                    auf_purchase_service,
                )
            )

        controller = SimpleNamespace(handle_scoped_auf_action=downstream)
        arguments = [object() for _ in range(11)]
        callback_data = SimpleNamespace(action="create")
        arguments[1] = callback_data

        async def scenario() -> None:
            with (
                patch.object(
                    wallet_ui.importlib,
                    "import_module",
                    return_value=controller,
                ),
                patch.object(wallet_ui, "_INSTALLED", False),
            ):
                wallet_ui.install_auf_wallet_ui()
                await controller.handle_scoped_auf_action(*arguments)

        asyncio.run(scenario())
        self.assertEqual(arguments, received)

    def test_qwen_wan_and_flux_final_buttons_enqueue_instead_of_reopening_models(
        self,
    ) -> None:
        models = (
            KieModelAlias.QWEN2_IMAGE_EDIT,
            KieModelAlias.WAN_27_IMAGE,
            KieModelAlias.FLUX_2_PRO_IMAGE,
        )

        for model in models:
            with self.subTest(model=model):
                markup = photo_modes._final_keyboard(42, model)
                callback_data = AufCallback.unpack(
                    markup.inline_keyboard[0][0].callback_data
                )
                self.assertEqual("photo_generate", callback_data.action)

                callback = object()
                state = object()
                kie_settings = object()
                database = object()
                ai_usage_service = object()
                ai_task_queue_service = object()
                enqueue = AsyncMock()
                fallback = AsyncMock()

                async def scenario() -> None:
                    with (
                        patch.object(
                            generation_hotfix.controller,
                            "require_auf_callback",
                            AsyncMock(return_value=True),
                        ),
                        patch.object(
                            generation_hotfix.photo_ui,
                            "_enqueue_auf_photo",
                            enqueue,
                        ),
                    ):
                        await generation_hotfix._canonical_photo_action(
                            callback,
                            callback_data,
                            state,
                            object(),
                            kie_settings,
                            database,
                            ai_usage_service,
                            ai_task_queue_service,
                            object(),
                            object(),
                            object(),
                            fallback=fallback,
                        )

                asyncio.run(scenario())
                enqueue.assert_awaited_once_with(
                    callback,
                    state,
                    kie_settings=kie_settings,
                    ai_usage_service=ai_usage_service,
                    ai_task_queue_service=ai_task_queue_service,
                    database=database,
                )
                fallback.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
