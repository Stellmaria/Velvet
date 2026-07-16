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
    owner_chat_ids: tuple[int, ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and (self.chat_id or self.owner_chat_ids))

    def _send_to(self, chat_id: int, text: str) -> bool:
        payload = json.dumps(
            {
                "chat_id": chat_id,
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
            logger.warning("Supervisor notification failed for chat %s: %s", chat_id, error)
            return False

    def send(self, title: str, body: str, *, level: str = "INFO") -> bool:
        if not self.enabled:
            return False
        normalized_level = level.upper()
        text = (
            f"<b>{html.escape(title)}</b>\n\n"
            f"<code>{html.escape(body[-3400:])}</code>\n\n"
            f"Уровень: <b>{html.escape(normalized_level)}</b>"
        )
        recipients: list[int] = []
        if self.chat_id is not None:
            recipients.append(self.chat_id)
        if normalized_level in {"ERROR", "CRITICAL"}:
            recipients.extend(self.owner_chat_ids)
        unique_recipients = tuple(dict.fromkeys(recipients))
        results = [self._send_to(chat_id, text) for chat_id in unique_recipients]
        return any(results)


__all__ = ("TelegramNotifier",)
