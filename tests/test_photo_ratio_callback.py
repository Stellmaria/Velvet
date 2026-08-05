from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from velvet_bot.app import auf_gpt_image_2_install as gpt_image
from velvet_bot.app.auf_photo_ratio_callback_fix import (
    build_safe_photo_ratio_keyboard,
    decode_photo_ratio_callback_value,
    encode_photo_ratio_callback_value,
    install_auf_photo_ratio_callback_fix,
)
from velvet_bot.domains.codex_image import CODEX_IMAGE_RATIOS
from velvet_bot.domains.media_generation import KieModelAlias
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback


class _RatioState:
    async def get_data(self) -> dict[str, int]:
        return {"auf_workspace_id": 17}

    async def set_state(self, _state) -> None:
        return None


class PhotoRatioCallbackTests(unittest.TestCase):
    def test_colon_ratios_round_trip_through_callback_safe_value(self) -> None:
        for ratio in ("1:1", "9:16", "21:9", "auto"):
            encoded = encode_photo_ratio_callback_value(ratio)
            self.assertNotIn(":", encoded)
            self.assertEqual(ratio, decode_photo_ratio_callback_value(encoded))

    def test_every_photo_ratio_keyboard_packs_without_aiogram_separator_error(self) -> None:
        models = (
            KieModelAlias.NANO_BANANA_2,
            KieModelAlias.NANO_BANANA_PRO,
            KieModelAlias.SEEDREAM_5_PRO,
            KieModelAlias.QWEN2_IMAGE_EDIT,
            KieModelAlias.WAN_27_IMAGE,
            KieModelAlias.FLUX_2_PRO_IMAGE,
        )
        for model in models:
            with self.subTest(model=model.value):
                keyboard = build_safe_photo_ratio_keyboard(17, model)
                decoded_ratios = []
                for row in keyboard.inline_keyboard:
                    for button in row:
                        if not button.callback_data:
                            continue
                        callback = AufCallback.unpack(button.callback_data)
                        if callback.action != "photo_ratio":
                            continue
                        self.assertNotIn(":", callback.value)
                        decoded_ratios.append(
                            decode_photo_ratio_callback_value(callback.value)
                        )
                self.assertEqual(
                    list(model.supported_aspect_ratios),
                    decoded_ratios,
                )


class GptImageRatioCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_gpt_image_ratio_keyboard_packs_and_decodes(self) -> None:
        install_auf_photo_ratio_callback_fix()
        with patch.object(
            gpt_image,
            "edit_or_answer_auf_callback",
            new_callable=AsyncMock,
        ) as edit:
            await gpt_image._show_ratios(object(), _RatioState())

        markup = edit.await_args.kwargs["reply_markup"]
        decoded_ratios = []
        for row in markup.inline_keyboard:
            for button in row:
                if not button.callback_data:
                    continue
                callback = AufCallback.unpack(button.callback_data)
                if callback.action != "gpt2_ratio":
                    continue
                self.assertNotIn(callback.value, button.callback_data)
                decoded_ratios.append(callback.value)

        self.assertEqual(list(CODEX_IMAGE_RATIOS), decoded_ratios)


if __name__ == "__main__":
    unittest.main()
