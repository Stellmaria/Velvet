from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

from velvet_bot.domains.media_generation import (
    MAX_KIE_REFERENCE_BYTES,
    KieGenerationRequest,
    KieModelCatalog,
    KieTaskRecord,
    KieTaskState,
    KieUploadedFile,
)

JsonTransport = Callable[
    [str, str, Mapping[str, str], Mapping[str, object] | None, float],
    Mapping[str, Any],
]
TaskUpdateCallback = Callable[[KieTaskRecord, int], Awaitable[None]]
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_GRS_TASK_PREFIX = "grs:"
_WAN_27_MODEL_ID = "wan/2-7-image-to-video"


class KieError(RuntimeError):
    pass


class KieTransientError(KieError):
    pass


class KieProtocolError(KieError):
    pass


class KieTaskFailed(KieError):
    def __init__(self, record: KieTaskRecord) -> None:
        self.record = record
        details = record.failure_message or record.failure_code or "неизвестная ошибка"
        provider = "GRS AI" if record.task_id.startswith(_GRS_TASK_PREFIX) else "Kie.ai"
        super().__init__(f"{provider} task {record.task_id} завершилась ошибкой: {details}")


class KieClient:
    """Route Seedream/video to Kie and Nano Banana 2/Pro to GRS AI."""

    def __init__(
        self,
        *,
        api_key: str,
        models: KieModelCatalog,
        base_url: str = "https://api.kie.ai/api/v1",
        file_upload_base_url: str = "https://kieai.redpandaai.co",
        grs_api_key: str | None = None,
        grs_base_url: str | None = None,
        timeout_seconds: float = 60,
        poll_interval_seconds: float = 4,
        task_timeout_seconds: float = 900,
        user_agent: str = _DEFAULT_USER_AGENT,
        transport: JsonTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("KIE_API_KEY не может быть пустым.")
        if not user_agent.strip():
            raise ValueError("Kie User-Agent не может быть пустым.")
        self.api_key = api_key.strip()
        self.grs_api_key = str(grs_api_key or os.getenv("GRS_API_KEY", "")).strip() or None
        self.models = models
        self.base_url = base_url.rstrip("/")
        self.file_upload_base_url = file_upload_base_url.rstrip("/")
        self.grs_base_url = str(
            grs_base_url or os.getenv("GRS_BASE_URL", "https://grsaiapi.com")
        ).strip().rstrip("/")
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.poll_interval_seconds = max(1.0, float(poll_interval_seconds))
        self.task_timeout_seconds = max(10.0, float(task_timeout_seconds))
        self.user_agent = user_agent.strip()
        self._transport = transport or _request_json
        self._grs_initial_responses: dict[str, Mapping[str, Any]] = {}

    async def upload_reference(
        self,
        payload: bytes,
        *,
        mime_type: str,
        file_name: str,
    ) -> KieUploadedFile:
        if not payload:
            raise ValueError("Нельзя загрузить пустой референс.")
        if len(payload) > MAX_KIE_REFERENCE_BYTES:
            raise ValueError("Референс должен быть не больше 10 МБ.")
        normalized_mime = mime_type.strip().casefold()
        if normalized_mime not in {
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/webp",
        }:
            raise ValueError("Провайдер принимает референсы только JPG, PNG или WEBP.")
        safe_name = Path(file_name or "reference.jpg").name or "reference.jpg"
        encoded = base64.b64encode(payload).decode("ascii")
        response = await asyncio.to_thread(
            self._transport,
            "POST",
            f"{self.file_upload_base_url}/api/file-base64-upload",
            self._headers(self.api_key),
            {
                "base64Data": f"data:{normalized_mime};base64,{encoded}",
                "uploadPath": "velvet/references",
                "fileName": safe_name,
            },
            self.timeout_seconds,
        )
        if response.get("success") is not True and response.get("code") != 200:
            self._ensure_kie_success(response, operation="file-base64-upload")
        data = response.get("data")
        if not isinstance(data, Mapping):
            raise KieProtocolError("Kie.ai upload не вернул объект data.")
        file_url = str(data.get("downloadUrl") or data.get("fileUrl") or "").strip()
        if not file_url:
            raise KieProtocolError("Kie.ai upload не вернул URL файла.")
        return KieUploadedFile(
            file_url=file_url,
            file_name=_optional_text(data.get("fileName")),
            mime_type=_optional_text(data.get("mimeType")),
            file_size=_optional_int(data.get("fileSize")),
        )

    async def create_task(
        self,
        request: KieGenerationRequest,
        *,
        callback_url: str | None = None,
    ) -> str:
        if request.model.is_grs:
            return await self._create_grs_task(request)
        provider_model = self.models.provider_model_for_request(request)
        provider_input: Mapping[str, object] = request.to_input()
        if provider_model == _WAN_27_MODEL_ID:
            provider_input = _build_wan_27_input(provider_input)
        payload: dict[str, object] = {
            "model": provider_model,
            "input": dict(provider_input),
        }
        if callback_url and callback_url.strip():
            payload["callBackUrl"] = callback_url.strip()
        response = await asyncio.to_thread(
            self._transport,
            "POST",
            f"{self.base_url}/jobs/createTask",
            self._headers(self.api_key),
            payload,
            self.timeout_seconds,
        )
        self._ensure_kie_success(response, operation="createTask")
        data = response.get("data")
        task_id = data.get("taskId") if isinstance(data, Mapping) else None
        task_id_text = str(task_id or "").strip()
        if not task_id_text:
            raise KieProtocolError("Kie.ai createTask не вернул taskId.")
        return task_id_text

    async def _create_grs_task(self, request: KieGenerationRequest) -> str:
        if self.grs_api_key is None:
            raise KieError("Для Nano Banana 2/Pro не задан GRS_API_KEY.")
        model_id = self.models.provider_model_for_request(request)
        response = await asyncio.to_thread(
            self._transport,
            "POST",
            f"{self.grs_base_url}/v1/api/generate",
            self._headers(self.grs_api_key),
            request.to_grs_input(model_id=model_id),
            self.timeout_seconds,
        )
        raw_task_id = str(response.get("id") or "").strip()
        if not raw_task_id:
            message = str(
                response.get("message")
                or response.get("msg")
                or response.get("error")
                or "GRS AI не вернул id задачи."
            )
            raise KieProtocolError(message)
        task_id = f"{_GRS_TASK_PREFIX}{raw_task_id}"
        self._grs_initial_responses[task_id] = dict(response)
        return task_id

    async def get_task(self, task_id: str) -> KieTaskRecord:
        task_id_text = task_id.strip()
        if not task_id_text:
            raise ValueError("task_id не может быть пустым.")
        if task_id_text.startswith(_GRS_TASK_PREFIX):
            return await self._get_grs_task(task_id_text)
        query = urllib.parse.urlencode({"taskId": task_id_text})
        response = await asyncio.to_thread(
            self._transport,
            "GET",
            f"{self.base_url}/jobs/recordInfo?{query}",
            self._headers(self.api_key),
            None,
            self.timeout_seconds,
        )
        self._ensure_kie_success(response, operation="recordInfo")
        try:
            return KieTaskRecord.from_api(response)
        except ValueError as error:
            raise KieProtocolError(str(error)) from error

    async def _get_grs_task(self, task_id: str) -> KieTaskRecord:
        cached = self._grs_initial_responses.pop(task_id, None)
        if cached is not None:
            try:
                return KieTaskRecord.from_grs_api(cached, task_id=task_id)
            except ValueError as error:
                raise KieProtocolError(str(error)) from error
        if self.grs_api_key is None:
            raise KieError("Для polling Nano Banana 2/Pro не задан GRS_API_KEY.")
        raw_task_id = task_id.removeprefix(_GRS_TASK_PREFIX)
        query = urllib.parse.urlencode({"id": raw_task_id})
        response = await asyncio.to_thread(
            self._transport,
            "GET",
            f"{self.grs_base_url}/v1/api/result?{query}",
            self._headers(self.grs_api_key),
            None,
            self.timeout_seconds,
        )
        try:
            return KieTaskRecord.from_grs_api(response, task_id=task_id)
        except ValueError as error:
            raise KieProtocolError(str(error)) from error

    async def wait_for_task(
        self,
        task_id: str,
        *,
        on_update: TaskUpdateCallback | None = None,
    ) -> KieTaskRecord:
        deadline = time.monotonic() + self.task_timeout_seconds
        transient_attempt = 0
        poll_count = 0
        while True:
            if time.monotonic() >= deadline:
                provider = "GRS AI" if task_id.startswith(_GRS_TASK_PREFIX) else "Kie.ai"
                raise TimeoutError(
                    f"{provider} task {task_id} не завершилась за "
                    f"{int(self.task_timeout_seconds)} сек."
                )
            try:
                record = await self.get_task(task_id)
                transient_attempt = 0
                poll_count += 1
                if on_update is not None:
                    await on_update(record, poll_count)
            except KieTransientError:
                transient_attempt += 1
                await asyncio.sleep(
                    min(self.poll_interval_seconds * (2 ** (transient_attempt - 1)), 30)
                )
                continue
            if record.state is KieTaskState.SUCCESS:
                return record
            if record.state is KieTaskState.FAIL:
                raise KieTaskFailed(record)
            await asyncio.sleep(self.poll_interval_seconds)

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }

    @staticmethod
    def _ensure_kie_success(payload: Mapping[str, Any], *, operation: str) -> None:
        code = payload.get("code")
        if code == 200:
            return
        message = str(payload.get("msg") or payload.get("message") or "неизвестная ошибка")
        try:
            numeric_code = int(code)
        except (TypeError, ValueError):
            numeric_code = 0
        error_type = (
            KieTransientError
            if numeric_code == 429 or numeric_code >= 500
            else KieError
        )
        raise error_type(f"Kie.ai {operation}: code={code}; {message}")


def _build_wan_27_input(payload: Mapping[str, object]) -> dict[str, object]:
    image_urls_value = payload.get("image_urls")
    image_urls = (
        [str(item).strip() for item in image_urls_value if str(item).strip()]
        if isinstance(image_urls_value, (list, tuple))
        else []
    )
    if not image_urls:
        raise KieProtocolError("Wan 2.7 требует URL первого кадра.")
    duration = _optional_int(payload.get("duration"))
    if duration is None or not 2 <= duration <= 15:
        raise KieProtocolError("Wan 2.7 поддерживает длительность от 2 до 15 секунд.")
    mode = str(payload.get("wan_mode") or "first").strip()
    result: dict[str, object] = {
        "prompt": str(payload.get("prompt") or "").strip(),
        "first_frame_url": image_urls[0],
        "resolution": str(payload.get("resolution") or "1080p").strip(),
        "duration": duration,
        "prompt_extend": bool(payload.get("prompt_extend", True)),
        "watermark": False,
        "nsfw_checker": False,
    }
    negative_prompt = str(payload.get("negative_prompt") or "").strip()
    if negative_prompt:
        result["negative_prompt"] = negative_prompt
    if mode == "first_last":
        if len(image_urls) < 2:
            raise KieProtocolError(
                "Wan 2.7 в режиме первого и последнего кадра требует два изображения."
            )
        result["last_frame_url"] = image_urls[1]
    elif mode != "first":
        raise KieProtocolError(f"Неизвестный режим кадров Wan 2.7: {mode}")
    return result


def _request_json(
    method: str,
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, object] | None,
    timeout_seconds: float,
) -> Mapping[str, Any]:
    body = (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if payload is not None
        else None
    )
    request = urllib.request.Request(
        url,
        data=body,
        headers=dict(headers),
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raw = error.read()
        message = raw.decode("utf-8", errors="replace")
        error_type = (
            KieTransientError
            if error.code == 429 or error.code >= 500
            else KieError
        )
        raise error_type(
            f"AI provider HTTP {error.code} для {method} {url}: {message[:500]}"
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise KieTransientError(f"Сетевая ошибка AI provider: {error}") from error
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KieProtocolError("AI provider вернул некорректный JSON.") from error
    if not isinstance(parsed, Mapping):
        raise KieProtocolError("AI provider вернул JSON не в виде объекта.")
    return parsed


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


__all__ = (
    "KieClient",
    "KieError",
    "KieProtocolError",
    "KieTaskFailed",
    "KieTransientError",
)
