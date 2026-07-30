from __future__ import annotations

import asyncio
import unittest

from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
)
from velvet_bot.infrastructure.ai import KieClient


class KieCloudflareHeaderTests(unittest.TestCase):
    def test_client_sends_browser_user_agent_for_every_kie_request(self) -> None:
        headers_seen: list[dict[str, str]] = []
        responses = iter(
            [
                {
                    "success": True,
                    "code": 200,
                    "data": {"downloadUrl": "https://temp.example/ref.jpg"},
                },
                {"code": 200, "data": {"taskId": "task-1"}},
                {
                    "code": 200,
                    "data": {
                        "taskId": "task-1",
                        "state": "success",
                        "resultJson": '{"resultUrls":["https://cdn.example/result.png"]}',
                    },
                },
            ]
        )

        def transport(method, url, headers, payload, timeout):
            headers_seen.append(dict(headers))
            return next(responses)

        client = KieClient(
            api_key="secret",
            models=KieModelCatalog(
                seedream_5_pro_text="seedream/5-pro-text-to-image"
            ),
            transport=transport,
        )
        request = KieGenerationRequest(
            model=KieModelAlias.SEEDREAM_5_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="1K",
        )

        async def scenario() -> None:
            await client.upload_reference(
                b"abc",
                mime_type="image/jpeg",
                file_name="reference.jpg",
            )
            task_id = await client.create_task(request)
            await client.get_task(task_id)

        asyncio.run(scenario())

        self.assertEqual(3, len(headers_seen))
        for headers in headers_seen:
            user_agent = headers.get("User-Agent", "")
            self.assertIn("Mozilla/5.0", user_agent)
            self.assertNotIn("Python-urllib", user_agent)
            self.assertEqual("Bearer secret", headers["Authorization"])

    def test_client_rejects_empty_user_agent(self) -> None:
        with self.assertRaisesRegex(ValueError, "User-Agent"):
            KieClient(
                api_key="secret",
                models=KieModelCatalog(),
                user_agent="   ",
            )


if __name__ == "__main__":
    unittest.main()
