from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import UUID

from velvet_bot.application.media_delivery import (
    MediaDeliveryItem,
    MediaDeliveryJob,
    MediaDeliveryStatus,
    MediaDeliveryStepStatus,
    media_delivery_error_fields,
    media_delivery_error_text,
)
from velvet_bot.application.media_tasks import task_payload_mapping

_VIDEO_MODELS = frozenset(
    {
        "grok_imagine_video",
        "grok_imagine_video_15",
        "seedance_15_pro_video",
        "wan_26_image_to_video",
    }
)
_TERMINAL_STATUSES = frozenset(
    {
        MediaDeliveryStatus.DELIVERED.value,
        MediaDeliveryStatus.PARTIAL.value,
        MediaDeliveryStatus.EXPIRED.value,
        MediaDeliveryStatus.FAILED.value,
    }
)


def _job_from_rows(
    row: Mapping[str, object],
    item_rows: list[Mapping[str, object]] | tuple[Mapping[str, object], ...],
) -> MediaDeliveryJob:
    request = task_payload_mapping(row.get("request_metadata"))
    return MediaDeliveryJob(
        task_id=UUID(str(row["task_id"])),
        provider=str(row["provider"]),
        provider_task_id=str(row["provider_task_id"]),
        chat_id=optional_int(row.get("chat_id")),
        media_kind=media_kind(str(row["media_kind"])),
        request=request,
        status=MediaDeliveryStatus(str(row["status"])),
        attempt_count=int(row["attempt_count"]),
        notification_status=MediaDeliveryStepStatus(str(row["notification_status"])),
        items=tuple(
            MediaDeliveryItem(
                result_index=int(item["result_index"]),
                result_url=str(item["result_url"]),
                url_status=str(item["url_status"]),
                download_status=MediaDeliveryStepStatus(str(item["download_status"])),
                original_status=MediaDeliveryStepStatus(str(item["original_status"])),
                preview_status=MediaDeliveryStepStatus(str(item["preview_status"])),
                content_type=(
                    str(item["content_type"]) if item.get("content_type") else None
                ),
                file_name=str(item["file_name"]) if item.get("file_name") else None,
            )
            for item in item_rows
        ),
    )


def delivery_metadata(request: Mapping[str, object]) -> dict[str, object]:
    references = request.get("references")
    return {
        "model": str(request.get("model") or "").strip(),
        "resolution": str(request.get("resolution") or "").strip(),
        "aspect_ratio": str(request.get("aspect_ratio") or "").strip(),
        "content_mode": str(request.get("content_mode") or "").strip(),
        "reference_count": (
            len(references) if isinstance(references, (list, tuple)) else 0
        ),
    }


def _json(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, default=str)


def _error_fields(
    error: BaseException | None,
    *,
    phase: str,
) -> tuple[str | None, str | None, str | None]:
    return media_delivery_error_fields(error, phase=phase)


def _error_text(error: BaseException | None, *, phase: str = "repository") -> str | None:
    return media_delivery_error_text(error, phase=phase)


def first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _text(value: object, fallback: str) -> str:
    return str(value or "").strip() or fallback


def media_kind(value: str) -> str:
    return "video" if str(value).strip().casefold() == "video" else "image"


def optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


__all__ = (
    "_TERMINAL_STATUSES",
    "_VIDEO_MODELS",
    "_error_fields",
    "_error_text",
    "_job_from_rows",
    "_json",
    "_text",
    "delivery_metadata",
    "first_text",
    "media_kind",
    "optional_int",
)
