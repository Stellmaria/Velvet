from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal

from velvet_bot.app.auf_branding import _redact_public_technical_text
from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
    KieTaskRecord,
    KieTaskState,
)
from velvet_bot.domains.media_generation.provider_contract import (
    extract_grs_violation_reason,
    extract_provider_credits,
    grs_retry_stage,
    provider_reason_text,
    with_image_output_guard,
)
from velvet_bot.infrastructure.ai import KieClient, KieError


class GrsViolationStatusTests(unittest.TestCase):
    def test_violation_is_a_typed_terminal_provider_failure(self) -> None:
        record = KieTaskRecord.from_grs_api(
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

    def test_nested_provider_reason_is_preserved(self) -> None:
        reason = extract_grs_violation_reason(
            {
                "status": "violation",
                "error": {
                    "code": "SAFETY_FILTER",
                    "details": {
                        "blockedReason": "sexual_content",
                        "category": "IMAGE_SAFETY",
                    },
                },
            }
        )
        self.assertIsNotNone(reason)
        self.assertIn("SAFETY_FILTER", reason)
        self.assertIn("sexual_content", reason)
        self.assertIn("IMAGE_SAFETY", reason)

    def test_language_model_chatter_is_not_a_diagnostic(self) -> None:
        self.assertIsNone(
            provider_reason_text(
                "Я просто языковая модель, мои возможности ограничены. Эта задача не для меня."
            )
        )
        self.assertEqual("IMAGE_SAFETY", provider_reason_text("IMAGE_SAFETY"))

    def test_retry_stage_uses_full_campaign_limit(self) -> None:
        stage = grs_retry_stage(
            provider_attempt=17,
            max_attempts=50,
            reason_text="Сервис не передал конкретную причину блокировки.",
        )
        self.assertIn("попытку 17/50", stage)
        self.assertIn("Следующая последовательная попытка", stage)

    def test_image_output_guard_preserves_owner_prompt(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="Cinematic portrait with exact facial identity",
            resolution="2K",
        )
        guarded = with_image_output_guard(request)
        self.assertIn(request.prompt, guarded.prompt)
        self.assertIn("return image output only", guarded.prompt)


class GrsOwnerTextTests(unittest.TestCase):
    def test_public_redaction_removes_internal_provider_lines(self) -> None:
        cleaned = _redact_public_technical_text(
            "<b>Проверьте запрос</b>\n\n"
            "Провайдер: <b>GRS AI</b>\n"
            "Задача провайдера: <code>grs:14</code>\n"
            "Обычный пользовательский текст"
        )
        self.assertNotIn("Провайдер:", cleaned)
        self.assertNotIn("Задача провайдера:", cleaned)
        self.assertIn("Обычный пользовательский текст", cleaned)


class GrsBalanceFallbackTests(unittest.TestCase):
    def test_credit_parser_accepts_current_shape(self) -> None:
        self.assertEqual(
            Decimal("4321"),
            extract_provider_credits(
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
        balance = asyncio.run(client.get_grs_credits())
        self.assertEqual(Decimal("9876"), balance)
        self.assertEqual("GET", calls[0][0])
        self.assertEqual("POST", calls[1][0])


if __name__ == "__main__":
    unittest.main()
