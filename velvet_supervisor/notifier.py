from __future__ import annotations

import html
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TelegramNotifier:
    bot_token: str | None
    chat_id: int | None
    timeout_seconds: int = 15

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, title: str, body: str, *, level: str = "INFO") -> bool:
        if not self.enabled:
            return False
        text = (
            f"<b>{html.escape(title)}</b>\n\n"
            f"<code>{html.escape(body[-3400:])}</code>\n\n"
            f"Уровень: <b>{html.escape(level)}</b>"
        )
        payload = json.dumps(
            {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                return 200 <= int(response.status) < 300
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            logger.warning("Supervisor notification failed: %s", error)
            return False


__all__ = ("TelegramNotifier",)
