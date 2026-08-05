from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.methods import SendMessage, SendPhoto

from velvet_bot.app import workspace_owner_generation_hotfix as hotfix
from velvet_bot.domains.media_generation import KieModelAlias


class WorkspaceOwnerGenerationHotfixTests(unittest.IsolatedAsyncioTestCase):
    def test_attempt_line_remains_visible_after_public_sanitizing(self) -> None:
        text = (
            "<b>Ауф создаёт · Nano Banana Pro</b>\n"
            "Провайдер: <b>GRS AI</b>\n"
            "Попытка: <b>5/50</b>\n"
            "Задача провайдера: <code>01234567-89ab-cdef-0123-456789abcdef</code>"
        )

        cleaned = hotfix._sanitize_auf_text_with_attempt(text)

        self.assertIn("Текущая попытка: <b>5/50</b>", cleaned)
        self.assertNotIn("Провайдер:", cleaned)
        self.assertNotIn("01234567-89ab", cleaned)

    def test_private_media_is_detected_but_text_and_groups_are_not(self) -> None:
        self.assertEqual(
            100,
            hotfix._private_media_chat_id(
                SendPhoto(chat_id=100, photo="telegram-file-id")
            ),
        )
        self.assertIsNone(
            hotfix._private_media_chat_id(
                SendPhoto(chat_id=-1001234567890, photo="telegram-file-id")
            )
        )
        self.assertIsNone(
            hotfix._private_media_chat_id(SendMessage(chat_id=100, text="menu"))
        )

    async def test_owner_role_enables_unprotected_private_media(self) -> None:
        repository = SimpleNamespace(
            list_for_user=AsyncMock(return_value=(SimpleNamespace(id=77),)),
            get_membership=AsyncMock(
                return_value=SimpleNamespace(role="owner")
            ),
        )
        previous_database = hotfix._ACTIVE_DATABASE
        hotfix._ACTIVE_DATABASE = SimpleNamespace()
        try:
            with patch.object(hotfix, "WorkspaceRepository", return_value=repository):
                self.assertTrue(await hotfix._user_owns_workspace(100))
        finally:
            hotfix._ACTIVE_DATABASE = previous_database

    async def test_qwen_wan_and_flux_use_canonical_photo_handler(self) -> None:
        for model in (
            KieModelAlias.QWEN2_IMAGE_EDIT,
            KieModelAlias.WAN_27_IMAGE,
            KieModelAlias.FLUX_2_PRO_IMAGE,
        ):
            with self.subTest(model=model):
                callback = SimpleNamespace(answer=AsyncMock())
                callback_data = SimpleNamespace(
                    action="photo_model",
                    workspace_id=91,
                    value=model.value,
                )
                state = SimpleNamespace()
                fallback = AsyncMock()
                direct_handler = AsyncMock()
                with (
                    patch.object(
                        hotfix.controller,
                        "require_auf_callback",
                        new=AsyncMock(return_value=True),
                    ),
                    patch.object(
                        hotfix.photo_modes,
                        "_handle_action",
                        new=direct_handler,
                    ),
                ):
                    await hotfix._canonical_photo_action(
                        callback,
                        callback_data,
                        state,
                        SimpleNamespace(),
                        SimpleNamespace(),
                        SimpleNamespace(),
                        SimpleNamespace(),
                        SimpleNamespace(),
                        SimpleNamespace(),
                        SimpleNamespace(),
                        SimpleNamespace(),
                        fallback=fallback,
                    )

                direct_handler.assert_awaited_once()
                fallback.assert_not_awaited()

    async def test_photo_generate_uses_current_model_first_enqueue(self) -> None:
        callback = SimpleNamespace(answer=AsyncMock())
        callback_data = SimpleNamespace(
            action="photo_generate",
            workspace_id=91,
            value="",
        )
        enqueue = AsyncMock()
        with (
            patch.object(
                hotfix.controller,
                "require_auf_callback",
                new=AsyncMock(return_value=True),
            ),
            patch.object(hotfix.photo_ui, "_enqueue_auf_photo", new=enqueue),
        ):
            await hotfix._canonical_photo_action(
                callback,
                callback_data,
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                fallback=AsyncMock(),
            )

        enqueue.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
