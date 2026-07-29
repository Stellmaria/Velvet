from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from velvet_bot.app.bootstrap import _build_bot
from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AITaskStatus, build_ai_task_queue_service
from velvet_bot.domains.media_generation import (
    KIE_GENERATION_TASK_TYPE,
    KieGenerationRequest,
    KiePricing,
    KieTaskRecord,
    KieTaskState,
)
from velvet_bot.domains.media_generation.friendly_worker import (
    FriendlyKieGenerationWorker,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Повторно отправить сохранённый результат генерации без нового платного запуска."
    )
    parser.add_argument("task_id", type=UUID, help="UUID завершённой AI-задачи")
    parser.add_argument(
        "--chat-id",
        type=int,
        default=None,
        help="Telegram chat_id. По умолчанию используется chat_id из задачи.",
    )
    return parser.parse_args()


def _request_from_task_payload(payload: Mapping[str, object]) -> KieGenerationRequest:
    raw_request = payload.get("request")
    if not isinstance(raw_request, Mapping):
        raise RuntimeError("В задаче нет сохранённого запроса генерации.")
    return KieGenerationRequest.from_task_payload(raw_request)


def _record_from_result(result: Mapping[str, object]) -> KieTaskRecord:
    provider_task_id = str(result.get("provider_task_id") or "").strip()
    raw_urls = result.get("result_urls")
    result_urls = (
        tuple(str(url).strip() for url in raw_urls if str(url).strip())
        if isinstance(raw_urls, (list, tuple))
        else ()
    )
    if not provider_task_id:
        raise RuntimeError("В результате задачи нет provider_task_id.")
    if not result_urls:
        raise RuntimeError("В результате задачи нет URL готового файла.")
    try:
        consumed_credits = max(0, int(result.get("consumed_credits") or 0))
    except (TypeError, ValueError):
        consumed_credits = 0
    return KieTaskRecord(
        task_id=provider_task_id,
        state=KieTaskState.SUCCESS,
        result_urls=result_urls,
        consumed_credits=consumed_credits,
    )


async def redeliver(task_id: UUID, *, chat_id: int | None = None) -> None:
    settings = load_settings()
    database = Database(settings.database_url)
    bot = _build_bot(settings)
    try:
        await database.initialize()
        queue = build_ai_task_queue_service(database=database)
        task = await queue.get(task_id=task_id)
        if task is None:
            raise RuntimeError(f"AI-задача {task_id} не найдена.")
        if task.task_type != KIE_GENERATION_TASK_TYPE:
            raise RuntimeError("Это не задача генерации фото или видео.")
        if task.status is not AITaskStatus.SUCCESS:
            raise RuntimeError(
                f"Задача имеет статус {task.status.value}, нужен статус success."
            )

        target_chat_id = chat_id
        if target_chat_id is None:
            try:
                target_chat_id = int(task.payload.get("chat_id") or 0)
            except (TypeError, ValueError):
                target_chat_id = 0
        if not target_chat_id:
            raise RuntimeError("Не удалось определить Telegram chat_id для доставки.")

        request = _request_from_task_payload(task.payload)
        record = _record_from_result(task.result)
        worker = FriendlyKieGenerationWorker(
            bot=bot,
            queue=SimpleNamespace(),
            client=SimpleNamespace(user_agent="Velvet-Result-Redelivery/1.0"),
            executor=SimpleNamespace(),
            pricing=KiePricing(),
            usd_to_rub=Decimal("1"),
            worker_id="manual-result-redelivery",
        )
        await worker._deliver_best_effort(
            chat_id=target_chat_id,
            request=request,
            record=record,
        )
        print(
            f"Повторная доставка запущена: task={task_id} "
            f"provider_task={record.task_id} chat_id={target_chat_id}. "
            "Новая генерация и новое списание не выполнялись."
        )
    finally:
        await bot.session.close()
        await database.close()


def main() -> None:
    args = _arguments()
    asyncio.run(redeliver(args.task_id, chat_id=args.chat_id))


if __name__ == "__main__":
    main()
