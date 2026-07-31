from __future__ import annotations

import unittest

from velvet_bot.domains.auf_runtime import AufProvider
from velvet_bot.domains.media_generation import KieModelAlias


class AufKieImageDispatchTests(unittest.TestCase):
    def test_qwen_wan_and_flux_are_routed_to_kie_dispatcher(self) -> None:
        kie_aliases = set(AufProvider.KIE.model_aliases)

        self.assertTrue(
            {
                KieModelAlias.QWEN2_IMAGE_EDIT.value,
                KieModelAlias.WAN_27_IMAGE.value,
                KieModelAlias.FLUX_2_PRO_IMAGE.value,
            }.issubset(kie_aliases)
        )

    def test_every_media_catalog_model_has_exactly_one_provider_route(self) -> None:
        kie_aliases = set(AufProvider.KIE.model_aliases)
        grs_aliases = set(AufProvider.GRS.model_aliases)
        catalog_aliases = {model.value for model in KieModelAlias}

        self.assertTrue(kie_aliases.isdisjoint(grs_aliases))
        self.assertEqual(catalog_aliases, kie_aliases | grs_aliases)


if __name__ == "__main__":
    unittest.main()
