#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from codex_first_runner import provider_fallback_reason, redact_text, utc_now
from codex_first_safe_runner import primary_execution_started

_ANALYSIS_MODELS = frozenset(
    {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
)
_REASONING_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
_RESOLUTIONS = frozenset({"1K", "2K", "4K"})
_IMAGE_MODEL_DEFAULT = "firefly-gpt-image-2"
_MAX_REFERENCE_BYTES = 8 * 1024 * 1024
_MAX_REFERENCES = 6
_MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
_MAX_GENERATION_PROMPT = 8_000
_INSTALLED = False


class ByesuImageFallbackError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ByesuReference:
    file_name: str
    mime_type: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class ByesuImageResult:
    payload: bytes
    mime_type: str
    suffix: str
    enhanced_prompt: str
    analysis_usage: Mapping[str, object] | None
    size: str
    image_model: str


def _enabled() -> bool:
    return os.environ.get(
        "CODEX_IMAGE_BYESU_FALLBACK_ENABLED", "false"
    ).strip().casefold() in {"1", "true", "yes", "on", "да"}


def _bounded_timeout() -> int:
    raw = os.environ.get("CODEX_IMAGE_BYESU_TIMEOUT_SECONDS", "600")
    try:
        value = int(raw)
    except ValueError:
        value = 600
    return max(60, min(value, 1_800))


def _size_for(resolution: str, aspect_ratio: str) -> str:
    normalized = resolution.strip().upper()
    if normalized not in _RESOLUTIONS:
        raise ByesuImageFallbackError("Недоступное качество Byesu image fallback")
    try:
        left, right = (int(value) for value in aspect_ratio.split(":", 1))
    except (TypeError, ValueError) as error:
        raise ByesuImageFallbackError(
            "Некорректная пропорция Byesu image fallback"
        ) from error
    if left <= 0 or right <= 0:
        raise ByesuImageFallbackError(
            "Некорректная пропорция Byesu image fallback"
        )
    edge = {"1K": 1024, "2K": 2048, "4K": 3840}[normalized]
    if left >= right:
        width = edge
        height = max(2, round(edge * right / left))
    else:
        width = max(2, round(edge * left / right))
        height = edge
    width -= width % 2
    height -= height % 2
    return f"{width}x{height}"


def _image_signature(payload: bytes) -> tuple[str, str]:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp", ".webp"
    raise ByesuImageFallbackError(
        "Byesu image fallback вернул файл с неизвестной сигнатурой"
    )


def _error_message(payload: bytes, fallback: str) -> str:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return fallback
    if not isinstance(data, Mapping):
        return fallback
    error = data.get("error")
    if isinstance(error, Mapping):
        value = error.get("message") or error.get("code")
        if value:
            return str(value)
    if error:
        return str(error)
    return str(data.get("message") or fallback)


class ByesuImageClient:
    def __init__(self) -> None:
        self.base_url = os.environ.get(
            "CODEX_IMAGE_BYESU_BASE_URL", "https://byesu.com/v1"
        ).strip().rstrip("/")
        self.api_key = os.environ.get("BYESU_HERMES_CODEX_API_KEY", "").strip()
        self.image_model = os.environ.get(
            "CODEX_IMAGE_BYESU_MODEL", _IMAGE_MODEL_DEFAULT
        ).strip()
        self.timeout_seconds = _bounded_timeout()
        if not self.base_url.startswith("https://"):
            raise ByesuImageFallbackError(
                "CODEX_IMAGE_BYESU_BASE_URL должен использовать HTTPS"
            )
        if len(self.api_key) < 20:
            raise ByesuImageFallbackError(
                "BYESU_HERMES_CODEX_API_KEY не настроен для image fallback"
            )
        if not self.image_model:
            raise ByesuImageFallbackError(
                "CODEX_IMAGE_BYESU_MODEL не настроен"
            )

    @property
    def _authorization(self) -> str:
        return f"Bearer {self.api_key}"

    def _open(self, request: Request) -> bytes:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read(_MAX_ARTIFACT_BYTES + 1)
        except HTTPError as error:
            details = error.read(16_384)
            raise ByesuImageFallbackError(
                _error_message(details, f"Byesu HTTP {error.code}")
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ByesuImageFallbackError(
                "Byesu image fallback недоступен"
            ) from error
        if len(payload) > _MAX_ARTIFACT_BYTES:
            raise ByesuImageFallbackError(
                "Byesu image fallback вернул слишком большой ответ"
            )
        return payload

    def _json(
        self,
        path: str,
        *,
        method: str = "GET",
        data: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = {"Authorization": self._authorization}
        if data is not None:
            body = json.dumps(
                data,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        payload = self._open(
            Request(
                f"{self.base_url}{path}",
                data=body,
                headers=headers,
                method=method,
            )
        )
        try:
            result = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ByesuImageFallbackError(
                "Byesu вернул повреждённый JSON"
            ) from error
        if not isinstance(result, dict):
            raise ByesuImageFallbackError(
                "Byesu вернул неожиданный JSON"
            )
        return result

    def assert_capabilities(self, analysis_model: str) -> None:
        if analysis_model not in _ANALYSIS_MODELS:
            raise ByesuImageFallbackError(
                "Недоступная GPT-5.6 модель анализа для Byesu fallback"
            )
        response = self._json("/models")
        raw_models = response.get("data")
        available = {
            str(item.get("id") or "").strip()
            for item in raw_models
            if isinstance(item, Mapping)
        } if isinstance(raw_models, Sequence) else set()
        required = {analysis_model, self.image_model}
        missing = sorted(required - available)
        if missing:
            raise ByesuImageFallbackError(
                "Byesu token group не видит обязательные модели: "
                + ", ".join(missing)
                + ". Для image fallback нужен media / media-gen token."
            )

    @staticmethod
    def _analysis_text(response: Mapping[str, object]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        output = response.get("output")
        if not isinstance(output, Sequence):
            return ""
        parts: list[str] = []
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, Sequence):
                continue
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                if str(part.get("type") or "") not in {
                    "output_text",
                    "text",
                }:
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()

    def analyze(
        self,
        *,
        user_prompt: str,
        references: Sequence[ByesuReference],
        analysis_model: str,
        reasoning_effort: str,
        aspect_ratio: str,
        resolution: str,
    ) -> tuple[str, Mapping[str, object] | None]:
        if reasoning_effort not in _REASONING_EFFORTS:
            raise ByesuImageFallbackError(
                "Недоступное reasoning effort для Byesu fallback"
            )
        instruction = (
            "Ты являешься visual-reference analyst перед единственной генерацией "
            "изображения. Изучи пользовательский запрос и все приложенные "
            "референсы как единый набор. Определи устойчивые признаки внешности, "
            "лица, волос, телосложения, одежды, аксессуаров, позы, композиции, "
            "сцены, света и стиля. Разрешай противоречия в пользу наиболее чётких "
            "и согласованных референсов. Сформируй один самодостаточный итоговый "
            "prompt для image-модели. Не описывай ход анализа, не используй "
            "Markdown и не проси дополнительных данных. Не утверждай личность "
            "реального человека; описывай только видимые признаки. Обязательно "
            "сохрани пользовательский замысел и укажи, что приложенные изображения "
            "являются визуальными референсами.\n\n"
            f"Целевая пропорция: {aspect_ratio}.\n"
            f"Качество резервного экспорта: {resolution}.\n\n"
            f"Пользовательский запрос:\n{user_prompt.strip()}"
        )
        content: list[dict[str, object]] = [
            {"type": "input_text", "text": instruction}
        ]
        for reference in references:
            encoded = base64.b64encode(reference.payload).decode("ascii")
            content.append(
                {
                    "type": "input_image",
                    "image_url": (
                        f"data:{reference.mime_type};base64,{encoded}"
                    ),
                    "detail": "original",
                }
            )
        response = self._json(
            "/responses",
            method="POST",
            data={
                "model": analysis_model,
                "reasoning": {"effort": reasoning_effort},
                "input": [{"role": "user", "content": content}],
                "max_output_tokens": 4_000,
            },
        )
        text = self._analysis_text(response)
        if not text:
            raise ByesuImageFallbackError(
                "GPT-5.6 анализатор Byesu не вернул итоговый prompt"
            )
        if len(text) > _MAX_GENERATION_PROMPT:
            text = text[:_MAX_GENERATION_PROMPT].rstrip()
        usage = response.get("usage")
        return text, usage if isinstance(usage, Mapping) else None

    @staticmethod
    def _multipart(
        fields: Mapping[str, str],
        references: Sequence[ByesuReference],
    ) -> tuple[str, bytes]:
        boundary = f"----velvet-byesu-{uuid.uuid4().hex}"
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend(
                (
                    f"--{boundary}\r\n".encode("ascii"),
                    (
                        f'Content-Disposition: form-data; name="{name}"'
                        "\r\n\r\n"
                    ).encode("utf-8"),
                    value.encode("utf-8"),
                    b"\r\n",
                )
            )
        for reference in references:
            safe_name = Path(reference.file_name).name.replace('"', "-")
            chunks.extend(
                (
                    f"--{boundary}\r\n".encode("ascii"),
                    (
                        "Content-Disposition: form-data; name=\"image\"; "
                        f'filename="{safe_name}"\r\n'
                    ).encode("utf-8"),
                    f"Content-Type: {reference.mime_type}\r\n\r\n".encode(
                        "ascii"
                    ),
                    reference.payload,
                    b"\r\n",
                )
            )
        chunks.append(f"--{boundary}--\r\n".encode("ascii"))
        return boundary, b"".join(chunks)

    def generate(
        self,
        *,
        prompt: str,
        references: Sequence[ByesuReference],
        size: str,
    ) -> tuple[bytes, str, str]:
        headers = {"Authorization": self._authorization}
        if references:
            boundary, body = self._multipart(
                {
                    "model": self.image_model,
                    "prompt": prompt,
                    "size": size,
                },
                references,
            )
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            request = Request(
                f"{self.base_url}/images/edits",
                data=body,
                headers=headers,
                method="POST",
            )
        else:
            body = json.dumps(
                {
                    "model": self.image_model,
                    "prompt": prompt,
                    "size": size,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
            request = Request(
                f"{self.base_url}/images/generations",
                data=body,
                headers=headers,
                method="POST",
            )
        payload = self._open(request)
        try:
            response = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ByesuImageFallbackError(
                "Byesu image endpoint вернул повреждённый JSON"
            ) from error
        data = response.get("data") if isinstance(response, Mapping) else None
        first = data[0] if isinstance(data, Sequence) and data else None
        encoded = first.get("b64_json") if isinstance(first, Mapping) else None
        if not isinstance(encoded, str) or not encoded:
            raise ByesuImageFallbackError(
                "Byesu image endpoint не вернул b64_json"
            )
        try:
            image = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as error:
            raise ByesuImageFallbackError(
                "Byesu image endpoint вернул повреждённый base64"
            ) from error
        if not image or len(image) > _MAX_ARTIFACT_BYTES:
            raise ByesuImageFallbackError(
                "Byesu image endpoint вернул пустой или слишком большой файл"
            )
        mime_type, suffix = _image_signature(image)
        return image, mime_type, suffix

    def run(
        self,
        *,
        user_prompt: str,
        references: Sequence[ByesuReference],
        analysis_model: str,
        reasoning_effort: str,
        aspect_ratio: str,
        resolution: str,
    ) -> ByesuImageResult:
        if len(references) > _MAX_REFERENCES:
            raise ByesuImageFallbackError(
                "Byesu firefly-gpt-image-2 принимает не больше шести референсов"
            )
        self.assert_capabilities(analysis_model)
        enhanced_prompt, usage = self.analyze(
            user_prompt=user_prompt,
            references=references,
            analysis_model=analysis_model,
            reasoning_effort=reasoning_effort,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
        size = _size_for(resolution, aspect_ratio)
        payload, mime_type, suffix = self.generate(
            prompt=enhanced_prompt,
            references=references,
            size=size,
        )
        return ByesuImageResult(
            payload=payload,
            mime_type=mime_type,
            suffix=suffix,
            enhanced_prompt=enhanced_prompt,
            analysis_usage=usage,
            size=size,
            image_model=self.image_model,
        )


def _stage_references(manager: Any, run_id: str) -> Path:
    root = (manager.store.root / "byesu-image-fallback-inputs").resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = (root / run_id).resolve()
    if target.parent != root:
        raise ByesuImageFallbackError(
            "Некорректный каталог Byesu image fallback"
        )
    source = (manager._image_inputs_root() / run_id).resolve()
    target.mkdir(mode=0o700)
    if source.is_dir():
        for item in sorted(source.iterdir()):
            if not item.is_file() or item.is_symlink():
                raise ByesuImageFallbackError(
                    "Некорректный staged reference для Byesu fallback"
                )
            destination = target / item.name
            shutil.copyfile(item, destination)
            destination.chmod(0o600)
    return target


def _load_references(record: Mapping[str, object], staged: Path) -> tuple[ByesuReference, ...]:
    metadata = record.get("references")
    by_name: dict[str, Mapping[str, object]] = {}
    if isinstance(metadata, Sequence):
        for item in metadata:
            if isinstance(item, Mapping):
                by_name[str(item.get("file_name") or "")] = item
    values: list[ByesuReference] = []
    for path in sorted(staged.iterdir()):
        if not path.is_file() or path.is_symlink():
            raise ByesuImageFallbackError(
                "Некорректный reference для Byesu fallback"
            )
        payload = path.read_bytes()
        if not payload or len(payload) > _MAX_REFERENCE_BYTES:
            raise ByesuImageFallbackError(
                "Для Byesu fallback каждый референс должен быть не больше 8 МБ"
            )
        item = by_name.get(path.name, {})
        mime_type = str(item.get("mime_type") or "image/jpeg").strip().casefold()
        if mime_type not in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
            raise ByesuImageFallbackError(
                "Byesu fallback принимает только JPG, PNG или WEBP"
            )
        values.append(
            ByesuReference(
                file_name=path.name,
                mime_type="image/jpeg" if mime_type == "image/jpg" else mime_type,
                payload=payload,
            )
        )
    return tuple(values)


def _eligible(record: Mapping[str, object], launch_result: Mapping[str, object]) -> bool:
    if str(record.get("status") or "") != "failed":
        return False
    if record.get("artifact_path"):
        return False
    if any(
        record.get(key) is True
        for key in (
            "execution_started",
            "primary_output_started",
            "provider_output_started",
            "mutation_started",
        )
    ):
        return False
    stdout = str(launch_result.get("stdout") or "")
    if bool(launch_result.get("execution_started")) or primary_execution_started(stdout):
        return False
    combined = f"{stdout}\n{launch_result.get('stderr') or ''}\n{record.get('error') or ''}"
    return provider_fallback_reason(combined) == "subscription_limit"


def _run_fallback(manager: Any, run_id: str, prompt: str, staged: Path) -> None:
    record = manager.store.read(run_id)
    references = _load_references(record, staged)
    attempted = list(record.get("attempted_routes") or [])
    if not attempted:
        attempted.append(f"codex_subscription:{record.get('model') or 'unknown'}")
    attempted.append("byesu_media:firefly-gpt-image-2")
    manager.store.update(
        run_id,
        status="running",
        actual_route="byesu_media",
        requested_route="codex_subscription",
        attempted_routes=attempted,
        fallback_reason="subscription_limit",
        last_event={
            "type": "byesu_image_fallback_started",
            "analysis_model": record.get("model"),
            "automatic_retry": False,
        },
    )
    try:
        client = ByesuImageClient()
        result = client.run(
            user_prompt=prompt,
            references=references,
            analysis_model=str(record.get("model") or "gpt-5.6-terra"),
            reasoning_effort=str(record.get("reasoning_effort") or "high"),
            aspect_ratio=str(record.get("aspect_ratio") or "9:16"),
            resolution=str(record.get("resolution") or "2K").upper(),
        )
        artifact = manager._image_artifacts_root() / f"{run_id}{result.suffix}"
        artifact.write_bytes(result.payload)
        artifact.chmod(0o600)
        manager.store.update(
            run_id,
            status="completed",
            finished_at=utc_now(),
            artifact_path=str(artifact),
            artifact_name=f"gpt-image-2-byesu-{run_id[:8]}{result.suffix}",
            artifact_mime_type=result.mime_type,
            artifact_bytes=len(result.payload),
            actual_route="byesu_media",
            requested_route="codex_subscription",
            attempted_routes=attempted,
            fallback_reason="subscription_limit",
            provider_model=result.image_model,
            provider_size=result.size,
            analysis_usage=dict(result.analysis_usage or {}),
            generation_attempts=1,
            last_event={
                "type": "byesu_image_fallback_completed",
                "analysis_model": record.get("model"),
                "image_model": result.image_model,
                "size": result.size,
                "automatic_retry": False,
            },
        )
    except Exception as error:
        manager.store.update(
            run_id,
            status="failed",
            finished_at=utc_now(),
            actual_route="byesu_media",
            requested_route="codex_subscription",
            attempted_routes=attempted,
            fallback_reason="subscription_limit",
            error=redact_text(str(error).strip())[-8_000:] or type(error).__name__,
            last_event={
                "type": "byesu_image_fallback_failed",
                "error_type": type(error).__name__,
                "automatic_retry": False,
            },
        )


def install_byesu_image_fallback() -> None:
    """Install a one-shot Byesu media fallback around CodexImageSupport."""
    global _INSTALLED
    if _INSTALLED:
        return
    from codex_image_runner import CodexImageSupport

    original = CodexImageSupport._execute_image

    def execute_with_byesu_fallback(self: Any, run_id: str, prompt: str) -> None:
        if not _enabled():
            original(self, run_id, prompt)
            return
        staged: Path | None = None
        launch_result: dict[str, object] = {}
        launcher = self._launcher
        original_run = launcher.run

        def capture_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = original_run(*args, **kwargs)
            launch_result.clear()
            launch_result.update(result)
            return result

        try:
            staged = _stage_references(self, run_id)
            launcher.run = capture_run
            original(self, run_id, prompt)
            record = self.store.read(run_id)
            if _eligible(record, launch_result):
                _run_fallback(self, run_id, prompt, staged)
        finally:
            launcher.run = original_run
            if staged is not None:
                shutil.rmtree(staged, ignore_errors=True)

    CodexImageSupport._execute_image = execute_with_byesu_fallback
    _INSTALLED = True


__all__ = (
    "ByesuImageClient",
    "ByesuImageFallbackError",
    "ByesuImageResult",
    "ByesuReference",
    "install_byesu_image_fallback",
)
