from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal

from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
)
from velvet_bot.domains.media_generation.friendly_worker import (
    friendly_error,
    friendly_stage,
)
from velvet_bot.infrastructure.ai import KieClient


class GrsAsyncSubmissionTests(unittest.TestCase):
    def test_grs_generation_requests_async_task_id(self) -> None:
        calls: list[tuple[str, str, object]] = []

        def transport(method, url, headers, payload, timeout):
            calls.append((method, url, payload))
            return {"id": "14-task-async", "status": "submitted", "results": []}

        client = KieClient(
            api_key="kie-secret",
            grs_api_key="grs-secret",
            grs_base_url="https://grs.example",
            models=KieModelCatalog(),
            transport=transport,
        )
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="2K",
        )

        task_id = asyncio.run(client.create_task(request))

        self.assertEqual("grs:14-task-async", task_id)
        self.assertEqual("POST", calls[0][0])
        self.assertEqual("https://grs.example/v1/api/generate", calls[0][1])
        payload = calls[0][2]
        self.assertIsInstance(payload, dict)
        self.assertEqual("async", payload["replyType"])
        self.assertEqual("nano-banana-pro", payload["model"])
        self.assertEqual("2K", payload["imageSize"])

    def test_grs_balance_accepts_nested_credit_response(self) -> None:
        def transport(method, url, headers, payload, timeout):
            self.assertEqual("GET", method)
            self.assertIn("/client/common/getCredits?", url)
            return {"code": 200, "data": {"credits": 9876}}

        client = KieClient(
            api_key="kie-secret",
            grs_api_key="grs-secret",
            grs_base_url="https://grs.example",
            models=KieModelCatalog(),
            transport=transport,
        )

        self.assertEqual(Decimal("9876"), asyncio.run(client.get_grs_credits()))


class FriendlyGrsProgressTests(unittest.TestCase):
    @staticmethod
    def _request() -> KieGenerationRequest:
        return KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="2K",
        )

    def test_provider_stage_does_not_claim_banana_runs_in_kie(self) -> None:
        text = friendly_stage(
            self._request(),
            "Платная попытка 1/50: отправка в Kie.ai.",
        )
        self.assertEqual("Платная попытка 1/50: отправка в GRS AI.", text)

    def test_uncertain_submission_message_is_provider_aware(self) -> None:
        text = friendly_error(
            self._request(),
            "Ответ createTask потерян или не подтверждён. Экономный режим остановил автоповтор.",
        )
        self.assertIn("GRS AI", text)
        self.assertIn("двойное списание", text)
        self.assertNotIn("createTask", text)


if __name__ == "__main__":
    unittest.main()
