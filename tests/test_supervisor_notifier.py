import json
import os
import unittest
from unittest.mock import patch

from velvet_supervisor.notifier import TelegramNotifier


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class SupervisorNotifierTests(unittest.TestCase):
    def test_error_is_sent_to_log_chat_and_owner(self) -> None:
        requests = []

        def fake_urlopen(request, timeout):
            requests.append((request, timeout))
            return _Response()

        notifier = TelegramNotifier(
            "123456789:abcdefghijklmnopqrstuvwxyzABCDE",
            -1001234567890,
            owner_chat_ids=(7221553045,),
        )
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self.assertTrue(notifier.send("Ошибка", "traceback", level="ERROR"))

        recipients = {
            json.loads(request.data.decode("utf-8"))["chat_id"]
            for request, _timeout in requests
        }
        self.assertEqual({-1001234567890, 7221553045}, recipients)

    def test_info_is_not_duplicated_to_owner(self) -> None:
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            return _Response()

        notifier = TelegramNotifier(
            "123456789:abcdefghijklmnopqrstuvwxyzABCDE",
            -1001234567890,
            owner_chat_ids=(7221553045,),
        )
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            notifier.send("Запуск", "ok", level="SUCCESS")

        self.assertEqual(1, len(requests))
        payload = json.loads(requests[0].data.decode("utf-8"))
        self.assertEqual(-1001234567890, payload["chat_id"])

    def test_owner_ids_fall_back_to_allowed_user_ids(self) -> None:
        with patch.dict(os.environ, {"ALLOWED_USER_IDS": "7221553045, 42"}, clear=False):
            notifier = TelegramNotifier("token", None)

        self.assertEqual((7221553045, 42), notifier.owner_chat_ids)
        self.assertTrue(notifier.enabled)


if __name__ == "__main__":
    unittest.main()
