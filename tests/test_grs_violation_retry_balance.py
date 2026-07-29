from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal

from velvet_bot.app.grs_resilience import (
    _extract_grs_credits,
    _from_grs_api_with_violation,
    _get_grs_credits_resilient,
    _violation_retry_limit_reached,
)
from velvet_bot.domains.media_generation import (
    KieModelCatalog,
    KieTaskRecord,
    KieTaskState,
)
from velvet_bot.infrastructure.ai import KieClient, KieError, KieTaskFailed


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

    def test_violation_retry_is_limited_to_two_provider_attempts(self) -> None:
        record = _from_grs_api_with_violation(
            KieTaskRecord,
            {"id": "14-moderated", "status": "violation"},
            task_id="grs:14-moderated",
        )
        error = KieTaskFailed(record)

        self.assertFalse(_violation_retry_limit_reached(error, 1))
        self.assertTrue(_violation_retry_limit_reached(error, 2))


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
