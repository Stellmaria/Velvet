from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from velvet_bot.app.auf_result_delivery_recovery import (
    deliver_record_with_recovery,
    delivery_callback,
    send_downloaded_result,
    task_delivery_buttons,
)
from velvet_bot.application.media_tasks import task_result_urls
from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieTaskRecord,
    KieTaskState,
)
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback


def _request() -> KieGenerationRequest:
    return KieGenerationRequest(
        model=KieModelAlias.NANO_BANANA_PRO,
        input_mode=KieInputMode.TEXT,
        prompt="portrait",
        resolution="2K",
    )


class AufResultDeliveryRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_provider_result_uses_direct_url_after_download_failure(
        self,
    ) -> None:
        bot = SimpleNamespace(
            send_photo=AsyncMock(),
            send_video=AsyncMock(),
            send_message=AsyncMock(),
        )

        async def retry(_name, operation):
            return await operation()

        worker = SimpleNamespace(
            _bot=bot,
            _download_result=AsyncMock(side_effect=RuntimeError("cdn timeout")),
            _send_telegram_with_retry=retry,
            _send_image_and_document=AsyncMock(),
            _send_video_and_document=AsyncMock(),
        )
        record = KieTaskRecord(
            task_id="grs:provider-task",
            state=KieTaskState.SUCCESS,
            result_urls=("https://cdn.example/result.png",),
        )

        await deliver_record_with_recovery(
            worker,
            chat_id=100,
            request=_request(),
            record=record,
        )

        worker._send_image_and_document.assert_not_awaited()
        bot.send_photo.assert_awaited_once()
        self.assertEqual(
            "https://cdn.example/result.png",
            bot.send_photo.await_args.kwargs["photo"],
        )
        bot.send_message.assert_awaited_once()
        warning = bot.send_message.await_args.args[1]
        self.assertIn("Новая платная генерация не запускалась", warning)
        self.assertIn("cdn timeout", warning)

    async def test_empty_success_result_is_reported_in_chat(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())

        async def retry(_name, operation):
            return await operation()

        worker = SimpleNamespace(
            _bot=bot,
            _send_telegram_with_retry=retry,
        )
        record = KieTaskRecord(
            task_id="grs:empty",
            state=KieTaskState.SUCCESS,
            result_urls=(),
        )

        await deliver_record_with_recovery(
            worker,
            chat_id=100,
            request=_request(),
            record=record,
        )

        bot.send_message.assert_awaited_once()
        self.assertIn("без URL результата", bot.send_message.await_args.args[1])

    async def test_document_failure_does_not_block_downloaded_preview(self) -> None:
        bot = SimpleNamespace(
            send_document=AsyncMock(side_effect=RuntimeError("document failed")),
            send_photo=AsyncMock(),
            send_video=AsyncMock(),
        )
        record = KieTaskRecord(
            task_id="grs:downloaded",
            state=KieTaskState.SUCCESS,
            result_urls=("https://cdn.example/result.png",),
        )

        document_sent, preview_sent = await send_downloaded_result(
            bot=bot,
            chat_id=100,
            request=_request(),
            record=record,
            url=record.result_urls[0],
            index=1,
            payload=b"image-bytes",
            mime_type="image/png",
            caption="Готово",
        )

        self.assertFalse(document_sent)
        self.assertTrue(preview_sent)
        bot.send_photo.assert_awaited_once()
        self.assertEqual("Готово", bot.send_photo.await_args.kwargs["caption"])


class AufResultDeliveryContractTests(unittest.TestCase):
    def test_delivery_callback_fits_telegram_limit_and_roundtrips(self) -> None:
        task_id = uuid4()
        value = delivery_callback(workspace_id=1, task_id=task_id)
        self.assertLessEqual(len(value), 64)
        parsed = AufCallback.unpack(value)
        self.assertEqual("deliver", parsed.action)
        self.assertEqual(str(task_id), parsed.value)

    def test_only_success_tasks_with_saved_urls_get_delivery_buttons(self) -> None:
        ready_id = uuid4()
        empty_id = uuid4()
        portal = SimpleNamespace(MODEL_NAMES={"nano_banana_pro": "Nano Banana Pro"})
        page = [
            {
                "id": ready_id,
                "status": "success",
                "payload": {"request": {"model": "nano_banana_pro"}},
            },
            {
                "id": empty_id,
                "status": "success",
                "payload": {"request": {"model": "nano_banana_pro"}},
            },
        ]
        rows = task_delivery_buttons(
            portal=portal,
            page=page,
            results={
                ready_id: {"result_urls": ["https://cdn.example/result.png"]},
                empty_id: {"result_urls": []},
            },
            workspace_id=1,
        )
        self.assertEqual(1, len(rows))
        self.assertIn("Доставить", rows[0][0].text)

    def test_result_url_parser_ignores_empty_values(self) -> None:
        self.assertEqual(
            ("https://a.example/a.png",),
            task_result_urls(
                {
                    "result_urls": [
                        "https://a.example/a.png",
                        "",
                        None,
                    ]
                }
            ),
        )

    def test_recovery_installs_after_existing_delivery_hotfixes(self) -> None:
        source = Path("velvet_bot/app/__init__.py").read_text(encoding="utf-8")
        portal = source.index("install_auf_user_portal()")
        image = source.index("install_original_image_delivery_hotfix()")
        video = source.index("install_original_video_delivery_hotfix()")
        recovery = source.index("install_auf_result_delivery_recovery()")
        self.assertLess(portal, recovery)
        self.assertLess(image, recovery)
        self.assertLess(video, recovery)


if __name__ == "__main__":
    unittest.main()
