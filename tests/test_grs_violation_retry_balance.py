from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal

from velvet_bot.app.grs_campaign_retry import (
    _provider_reason_without_model_chatter,
    _violation_retry_stage,
    _with_image_output_guard,
)
from velvet_bot.app.grs_resilience import (
    _extract_grs_credits,
    _extract_grs_violation_reason,
    _from_grs_api_with_violation,
    _get_grs_credits_resilient,
    _sanitize_meow_text,
)
from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
    KieTaskRecord,
    KieTaskState,
)
from velvet_bot.infrastructure.ai import KieClient, KieError


class GrsViolationStatusTests(unittest.TestCase):
    def test_violation_is_a_typed_terminal_provider_failure(self) -> None:
        record = _from_grs_api_with_violation(
            KieTaskRecord,
            {
                "id": "14-moderated",
                "status": "violation",
                "message": "content policy",
            },
            task_id="grs:14-moderated",
        )

        self.assertEqual(KieTaskState.FAIL, record.state)
        self.assertEqual("violation", record.failure_code)
        self.assertEqual("content policy", record.failure_message)
        self.assertEqual("violation", record.raw["status"])

    def test_nested_provider_reason_is_preserved_for_owner_message(self) -> None:
        payload = {
            "id": "14-safety",
            "status": "violation",
            "error": {
                "code": "SAFETY_FILTER",
                "details": {
                    "blockedReason": "sexual_content",
                    "category": "IMAGE_SAFETY",
                },
            },
        }

        reason = _extract_grs_violation_reason(payload)

        self.assertIsNotNone(reason)
        self.assertIn("SAFETY_FILTER", reason)
        self.assertIn("sexual_content", reason)
        self.assertIn("IMAGE_SAFETY", reason)

    def test_status_only_violation_does_not_invent_a_reason(self) -> None:
        self.assertIsNone(
            _extract_grs_violation_reason(
                {"id": "14-moderated", "status": "violation"}
            )
        )

    def test_language_model_chatter_is_not_a_moderation_diagnostic(self) -> None:
        self.assertIsNone(
            _provider_reason_without_model_chatter(
                "Я просто языковая модель, мои возможности ограничены. Эта задача не для меня."
            )
        )
        self.assertEqual(
            "IMAGE_SAFETY",
            _provider_reason_without_model_chatter("IMAGE_SAFETY"),
        )

    def test_retry_stage_uses_full_campaign_limit(self) -> None:
        stage = _violation_retry_stage(
            provider_attempt=17,
            max_attempts=50,
            delay_seconds=30,
            reason_text="GRS AI не передал конкретную причину блокировки.",
        )

        self.assertIn("попытку 17/50", stage)
        self.assertIn("Следующая последовательная попытка", stage)
        self.assertNotIn("один раз", stage)

    def test_image_output_guard_preserves_owner_prompt(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="Cinematic portrait with exact facial identity",
            resolution="2K",
        )

        guarded = _with_image_output_guard(request)

        self.assertIn(request.prompt, guarded.prompt)
        self.assertIn("return image output only", guarded.prompt)
        self.assertEqual(request.model, guarded.model)
        self.assertEqual(request.resolution, guarded.resolution)


class GrsOwnerTextTests(unittest.TestCase):
    def test_internal_mature_line_is_removed_without_touching_prompt(self) -> None:
        source = (
            "<b>Проверьте запрос</b>\n\n"
            "Контент: <b>Mature</b>\n\n"
            "<b>Текст</b>\nMature portrait with cinematic light"
        )

        cleaned = _sanitize_meow_text(source)

        self.assertNotIn("Контент: <b>Mature</b>", cleaned)
        self.assertIn("Mature portrait with cinematic light", cleaned)

    def test_banana_queue_message_names_grs_without_worker_jargon(self) -> None:
        source = (
            "<b>Мяу · Nano Banana Pro</b>\n\n"
            "Задача поставлена в очередь. Worker скачает выбранные Telegram-фото, "
            "временно загрузит их в Kie и только затем вызовет модель.\n\n"
            "Контент: <b>Mature</b>"
        )

        cleaned = _sanitize_meow_text(source)

        self.assertIn("отправлены в GRS AI", cleaned)
        self.assertNotIn("Worker", cleaned)
        self.assertNotIn("Контент:", cleaned)


class GrsBalanceFallbackTests(unittest.TestCase):
    def test_credit_parser_accepts_current_api_key_balance_shape(self) -> None:
        self.assertEqual(
            Decimal("4321"),
            _extract_grs_credits(
                {"success": True, "data": {"currentCredits": "4,321"}}
            ),
        )

    def test_balance_falls_back_to_openapi_endpoint(self) -> None:
        calls: list[tuple[str, str, object]] = []

        def transport(method, url, headers, payload, timeout):
            calls.append((method, url, payload))
            if "/client/common/getCredits?" in url:
                raise KieError("legacy endpoint unavailable")
            return {"success": True, "data": {"apiKeyCredits": 9876}}

        client = KieClient(
            api_key="kie-secret",
            grs_api_key="grs-secret",
            grs_base_url="https://grs.example",
            models=KieModelCatalog(),
            transport=transport,
        )

        balance = asyncio.run(_get_grs_credits_resilient(client))

        self.assertEqual(Decimal("9876"), balance)
        self.assertEqual("GET", calls[0][0])
        self.assertEqual("POST", calls[1][0])
        self.assertEqual(
            "https://grs.example/client/openapi/getAPIKeyCredits",
            calls[1][1],
        )
        self.assertEqual({"apikey": "grs-secret"}, calls[1][2])


if __name__ == "__main__":
    unittest.main()
