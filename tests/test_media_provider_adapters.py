from __future__ import annotations

import asyncio
import unittest

from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
    MediaProviderName,
)
from velvet_bot.infrastructure.ai import KieClient


class MediaProviderAdapterTests(unittest.TestCase):
    def test_registry_routes_each_model_without_worker_conditionals(self) -> None:
        client = KieClient(
            api_key="kie-secret",
            grs_api_key="grs-secret",
            models=KieModelCatalog(),
            transport=lambda *args: {},
        )
        grs = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="2K",
        )
        kie = KieGenerationRequest(
            model=KieModelAlias.WAN_27_IMAGE,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="1K",
        )
        self.assertEqual(MediaProviderName.GRS, client.provider_route(grs).provider)
        self.assertEqual(MediaProviderName.KIE, client.provider_route(kie).provider)
        self.assertEqual("nano-banana-pro", client.provider_route(grs).model_id)
        self.assertEqual(
            "wan/2-7-image",
            client.provider_route(kie).model_id,
        )

    def test_unsupported_cancel_is_explicit_and_side_effect_free(self) -> None:
        calls: list[str] = []

        def transport(method, url, headers, payload, timeout):
            calls.append(url)
            return {}

        client = KieClient(
            api_key="kie-secret",
            grs_api_key="grs-secret",
            models=KieModelCatalog(),
            transport=transport,
        )
        self.assertFalse(asyncio.run(client.cancel_task("grs:123")))
        self.assertFalse(asyncio.run(client.cancel_task("kie-123")))
        self.assertEqual([], calls)


if __name__ == "__main__":
    unittest.main()
