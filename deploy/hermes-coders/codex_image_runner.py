#!/usr/bin/env python3
from __future__ import annotations

import base64
import binascii
import json
import re
import shutil
import threading
import uuid
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from codex_runner import Handler as BaseHandler
from codex_runner import RunnerError, parse_jsonl_output, redact_text, utc_now

GPT_IMAGE_MODEL_NAME = "GPT Image 2"
IMAGE_TASK_KIND = "image"
IMAGE_MODELS = frozenset({"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"})
REASONING_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
IMAGE_RESOLUTIONS = frozenset({"1K", "2K", "4K"})
IMAGE_ASPECT_RATIOS = frozenset(
    {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"}
)
IMAGE_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
IMAGE_SUFFIX_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
MAX_IMAGE_REFERENCES = 5
MAX_IMAGE_REFERENCE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_TOTAL_REFERENCE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PROMPT_CHARS = 8_000
MAX_IMAGE_REQUEST_BYTES = 72 * 1024 * 1024
MAX_IMAGE_ARTIFACT_BYTES = 50 * 1024 * 1024
_IMAGE_RUN = re.compile(r"^[a-f0-9]{32}$")
_SAFE_FILE = re.compile(r"[^A-Za-z0-9._-]+")


def _exact_fields(payload: Mapping[str, Any], expected: set[str]) -> None:
    if set(payload) != expected:
        raise RunnerError(
            HTTPStatus.BAD_REQUEST,
            "GPT Image 2 request содержит неверный набор полей",
        )


def _clean_filename(value: object, *, index: int, suffix: str) -> str:
    raw = Path(str(value or f"reference-{index}{suffix}")).name
    stem = _SAFE_FILE.sub("-", Path(raw).stem).strip(".-") or f"reference-{index}"
    return f"{stem[:80]}{suffix}"


def _decode_reference(value: object, *, index: int) -> tuple[str, str, bytes]:
    if not isinstance(value, Mapping):
        raise RunnerError(HTTPStatus.BAD_REQUEST, "Референс должен быть объектом")
    _exact_fields(value, {"file_name", "mime_type", "data_base64"})
    mime_type = str(value.get("mime_type") or "").strip().casefold()
    suffix = IMAGE_MIME_TYPES.get(mime_type)
    if suffix is None:
        raise RunnerError(
            HTTPStatus.BAD_REQUEST,
            "GPT Image 2 принимает референсы только JPG, PNG или WEBP",
        )
    encoded = value.get("data_base64")
    if not isinstance(encoded, str) or not encoded:
        raise RunnerError(HTTPStatus.BAD_REQUEST, "Референс не содержит data_base64")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise RunnerError(
            HTTPStatus.BAD_REQUEST,
            "Референс содержит повреждённый base64",
        ) from error
    if not payload:
        raise RunnerError(HTTPStatus.BAD_REQUEST, "Референс пуст")
    if len(payload) > MAX_IMAGE_REFERENCE_BYTES:
        raise RunnerError(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            "Один референс не должен превышать 10 МБ",
        )
    return (
        _clean_filename(value.get("file_name"), index=index, suffix=suffix),
        mime_type,
        payload,
    )


def _looks_like_image(payload: bytes, suffix: str) -> bool:
    if suffix in {".jpg", ".jpeg"}:
        return payload.startswith(b"\xff\xd8\xff")
    if suffix == ".png":
        return payload.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix == ".webp":
        return len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"
    return False


def build_image_prompt(
    *,
    user_prompt: str,
    reference_names: tuple[str, ...],
    aspect_ratio: str,
    resolution: str,
) -> str:
    reference_block = "\n".join(
        f"- /workspace/.hermes-image-inputs/{name}" for name in reference_names
    )
    if not reference_block:
        reference_block = "- Референсов нет: работай только по текстовому описанию."
    return f"""ЗАДАЧА: создать ровно одно изображение через встроенный инструмент image_gen.

Пользовательский промт:
{user_prompt}

Референсы:
{reference_block}

Обязательный контракт:
1. Проанализируй все приложенные изображения как единый набор референсов персонажа, внешности, одежды, окружения, композиции и других визуальных деталей. Пользователь не назначает им роли: определи их сам.
2. Используй встроенный image_gen ровно один раз. Не делай автоматическую повторную генерацию и не создавай несколько вариантов.
3. Целевая пропорция: {aspect_ratio}. Построй композицию сразу под неё и оставь безопасные поля вокруг важных деталей.
4. Выбранный размер экспорта: {resolution}. Это целевой уровень итогового файла; удели максимум внимания деталям и чистоте исходника.
5. Создай только одно цельное изображение, не коллаж и не лист вариантов.
6. После генерации обязательно скопируй финальный файл в /workspace/.hermes-image-output/result.png либо /workspace/.hermes-image-output/result.jpg.
7. Не изменяй исходный код, Git refs, конфигурацию проекта и любые файлы вне каталогов .hermes-image-inputs и .hermes-image-output.
8. В финальном текстовом ответе кратко укажи только путь сохранённого файла. Сам файл важнее текста.
"""


class CodexImageSupport:
    """One-shot GPT Image 2 runs through the existing Codex subscription sandbox."""

    def _image_inputs_root(self) -> Path:
        root = (self.store.root / "image-inputs").resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        return root

    def _image_artifacts_root(self) -> Path:
        root = (self.store.root / "image-artifacts").resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        return root

    def submit_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        _exact_fields(
            payload,
            {
                "prompt",
                "references",
                "aspect_ratio",
                "resolution",
                "analysis_model",
                "reasoning_effort",
                "session_id",
            },
        )
        prompt = payload.get("prompt")
        references_value = payload.get("references")
        aspect_ratio = str(payload.get("aspect_ratio") or "").strip()
        resolution = str(payload.get("resolution") or "").strip().upper()
        model = str(payload.get("analysis_model") or "").strip()
        effort = str(payload.get("reasoning_effort") or "").strip().casefold()
        session_id = payload.get("session_id")
        if not isinstance(prompt, str) or not prompt.strip():
            raise RunnerError(
                HTTPStatus.BAD_REQUEST,
                "Промт GPT Image 2 не может быть пустым",
            )
        if len(prompt.strip()) > MAX_IMAGE_PROMPT_CHARS:
            raise RunnerError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "Промт GPT Image 2 превышает 8000 символов",
            )
        if not isinstance(references_value, list) or len(references_value) > MAX_IMAGE_REFERENCES:
            raise RunnerError(
                HTTPStatus.BAD_REQUEST,
                "GPT Image 2 принимает от 0 до 5 референсов",
            )
        if aspect_ratio not in IMAGE_ASPECT_RATIOS:
            raise RunnerError(
                HTTPStatus.BAD_REQUEST,
                "Недоступное соотношение сторон GPT Image 2",
            )
        if resolution not in IMAGE_RESOLUTIONS:
            raise RunnerError(HTTPStatus.BAD_REQUEST, "Недоступный размер GPT Image 2")
        if model not in IMAGE_MODELS or model not in self.allowed_models:
            raise RunnerError(
                HTTPStatus.BAD_REQUEST,
                "Недоступная модель анализа GPT Image 2",
            )
        if effort not in REASONING_EFFORTS:
            raise RunnerError(
                HTTPStatus.BAD_REQUEST,
                "Недоступное усилие анализа GPT Image 2",
            )
        if session_id is not None and (
            not isinstance(session_id, str) or len(session_id) > 200
        ):
            raise RunnerError(
                HTTPStatus.BAD_REQUEST,
                "Некорректный session_id GPT Image 2",
            )

        decoded: list[tuple[str, str, bytes]] = []
        total = 0
        for index, item in enumerate(references_value, start=1):
            reference = _decode_reference(item, index=index)
            total += len(reference[2])
            if total > MAX_IMAGE_TOTAL_REFERENCE_BYTES:
                raise RunnerError(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    "Суммарный размер референсов превышает 50 МБ",
                )
            decoded.append(reference)

        run_id = uuid.uuid4().hex
        input_dir = (self._image_inputs_root() / run_id).resolve()
        if input_dir.parent != self._image_inputs_root():
            raise RunnerError(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Некорректный каталог GPT Image 2",
            )
        input_dir.mkdir(mode=0o700)
        reference_meta: list[dict[str, Any]] = []
        try:
            for file_name, mime_type, data in decoded:
                path = input_dir / file_name
                path.write_bytes(data)
                path.chmod(0o600)
                reference_meta.append(
                    {"file_name": file_name, "mime_type": mime_type, "size": len(data)}
                )
        except Exception:
            shutil.rmtree(input_dir, ignore_errors=True)
            raise

        now = utc_now()
        record = {
            "run_id": run_id,
            "session_id": session_id,
            "task_kind": IMAGE_TASK_KIND,
            "status": "queued",
            "model": model,
            "reasoning_effort": effort,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "output_format": "jpeg",
            "reference_count": len(reference_meta),
            "references": reference_meta,
            "mutation_policy": "workspace_write",
            "created_at": now,
            "updated_at": now,
            "last_event": {"type": "image_queued", "model": model},
        }
        self.store.write(record)
        thread = threading.Thread(
            target=self._execute_image,
            args=(run_id, prompt.strip()),
            name=f"codex-image-{run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return self.image_status(run_id)

    def _safe_rate_limits(self) -> dict[str, Any] | None:
        try:
            result = self.rate_limits()
        except Exception:
            return None
        return result if isinstance(result, dict) else None

    def _execute_image(self, run_id: str, prompt: str) -> None:
        with self._isolation_lock:
            record = self.store.read(run_id)
            if record.get("stop_requested"):
                self.store.update(
                    run_id,
                    status="cancelled",
                    finished_at=utc_now(),
                    last_event={"type": "image_cancelled_before_start"},
                )
                self._cleanup_image_inputs(run_id)
                return
            workspace: Path | None = None
            before = self._safe_rate_limits()
            try:
                self.store.update(
                    run_id,
                    status="running",
                    started_at=utc_now(),
                    rate_limits_before=before,
                    last_event={"type": "image_workspace_preparation_started"},
                )
                workspace, source_ref = self._prepare_workspace(run_id)
                self.workspace = workspace
                input_target = workspace / ".hermes-image-inputs"
                output_target = workspace / ".hermes-image-output"
                input_target.mkdir(mode=0o700)
                output_target.mkdir(mode=0o700)
                input_source = self._image_inputs_root() / run_id
                reference_names: list[str] = []
                for source in sorted(input_source.iterdir()):
                    if not source.is_file() or source.is_symlink():
                        raise RuntimeError("Некорректный staged референс GPT Image 2")
                    target = input_target / source.name
                    shutil.copyfile(source, target)
                    target.chmod(0o600)
                    reference_names.append(source.name)
                effort = str(record.get("reasoning_effort") or "high")
                runtime_request = workspace / ".git" / "hermes-image-request.json"
                runtime_request.write_text(
                    json.dumps(
                        {"task_kind": IMAGE_TASK_KIND, "reasoning_effort": effort},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    encoding="utf-8",
                )
                runtime_request.chmod(0o600)
                rendered = build_image_prompt(
                    user_prompt=prompt,
                    reference_names=tuple(reference_names),
                    aspect_ratio=str(record["aspect_ratio"]),
                    resolution=str(record["resolution"]),
                )
                self.store.update(
                    run_id,
                    workspace_source_ref=source_ref,
                    last_event={
                        "type": "image_generation_started",
                        "model": record["model"],
                    },
                )
                result = self._launcher.run(
                    run_id=run_id,
                    project=self.project,
                    workspace=workspace,
                    model=str(record["model"]),
                    route=self.primary_route,
                    mutation_policy="workspace_write",
                    timeout_seconds=self.timeout_seconds,
                    prompt=rendered,
                )
                if result.get("cancelled") or self.store.read(run_id).get("stop_requested"):
                    self.store.update(
                        run_id,
                        status="cancelled",
                        finished_at=utc_now(),
                        last_event={"type": "image_cancelled"},
                    )
                    return
                stdout = str(result.get("stdout") or "")
                stderr = str(result.get("stderr") or "")
                if int(result.get("returncode", 1)) != 0:
                    details = redact_text((stderr or stdout).strip()[-4000:])
                    raise RuntimeError(
                        details or "Codex GPT Image 2 завершился с ошибкой"
                    )
                candidate = self._find_image_artifact(output_target)
                payload = candidate.read_bytes()
                if not payload or len(payload) > MAX_IMAGE_ARTIFACT_BYTES:
                    raise RuntimeError(
                        "GPT Image 2 вернул пустой или слишком большой файл"
                    )
                suffix = candidate.suffix.casefold()
                if not _looks_like_image(payload, suffix):
                    raise RuntimeError("GPT Image 2 вернул файл с неверной сигнатурой")
                artifact = self._image_artifacts_root() / f"{run_id}{suffix}"
                artifact.write_bytes(payload)
                artifact.chmod(0o600)
                _, usage, last_event = parse_jsonl_output(stdout)
                after = self._safe_rate_limits()
                self.store.update(
                    run_id,
                    status="completed",
                    finished_at=utc_now(),
                    artifact_path=str(artifact),
                    artifact_name=f"gpt-image-2-{run_id[:8]}{suffix}",
                    artifact_mime_type=IMAGE_SUFFIX_MIME_TYPES[suffix],
                    artifact_bytes=len(payload),
                    usage=usage,
                    rate_limits_after=after,
                    last_event=last_event
                    or {"type": "image_completed", "model": record["model"]},
                )
            except Exception as error:
                if str(self.store.read(run_id).get("status")) not in {
                    "cancelled",
                    "completed",
                }:
                    self.store.update(
                        run_id,
                        status="failed",
                        finished_at=utc_now(),
                        rate_limits_after=self._safe_rate_limits(),
                        error=redact_text(str(error).strip())[-8000:]
                        or type(error).__name__,
                        last_event={
                            "type": "image_failed",
                            "error_type": type(error).__name__,
                        },
                    )
            finally:
                self.workspace = self._base_workspace
                if workspace is not None:
                    self._cleanup_workspace(workspace)
                self._cleanup_image_inputs(run_id)

    @staticmethod
    def _find_image_artifact(output_dir: Path) -> Path:
        preferred = tuple(
            output_dir / name
            for name in ("result.png", "result.jpg", "result.jpeg", "result.webp")
        )
        for path in preferred:
            if path.is_file() and not path.is_symlink():
                return path
        candidates = [
            path
            for path in sorted(output_dir.iterdir())
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.casefold() in IMAGE_SUFFIX_MIME_TYPES
        ]
        if len(candidates) != 1:
            raise RuntimeError("GPT Image 2 не сохранил ровно один итоговый файл")
        return candidates[0]

    def _cleanup_image_inputs(self, run_id: str) -> None:
        if not _IMAGE_RUN.fullmatch(run_id):
            return
        target = (self._image_inputs_root() / run_id).resolve()
        if target.parent == self._image_inputs_root() and not target.is_symlink():
            shutil.rmtree(target, ignore_errors=True)

    def image_status(self, run_id: str) -> dict[str, Any]:
        if not _IMAGE_RUN.fullmatch(run_id):
            raise RunnerError(HTTPStatus.BAD_REQUEST, "Некорректный GPT Image 2 run_id")
        record = self.store.read(run_id)
        if record.get("task_kind") != IMAGE_TASK_KIND:
            raise RunnerError(HTTPStatus.NOT_FOUND, "GPT Image 2 run не найден")
        return {key: value for key, value in record.items() if key != "artifact_path"}

    def image_content(self, run_id: str) -> tuple[bytes, str, str]:
        record = self.store.read(run_id)
        if (
            record.get("task_kind") != IMAGE_TASK_KIND
            or record.get("status") != "completed"
        ):
            raise RunnerError(
                HTTPStatus.CONFLICT,
                "GPT Image 2 результат ещё не готов",
            )
        path = Path(str(record.get("artifact_path") or ""))
        root = self._image_artifacts_root()
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise RunnerError(
                HTTPStatus.NOT_FOUND,
                "GPT Image 2 artifact потерян",
            ) from error
        if resolved.parent != root or resolved.is_symlink() or not resolved.is_file():
            raise RunnerError(
                HTTPStatus.NOT_FOUND,
                "GPT Image 2 artifact недоступен",
            )
        payload = resolved.read_bytes()
        return (
            payload,
            str(record.get("artifact_mime_type") or "application/octet-stream"),
            str(record.get("artifact_name") or resolved.name),
        )


class ImageHandler(BaseHandler):
    server_version = "VelvetCodexImageRunner/1"

    def _read_image_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise RunnerError(
                HTTPStatus.BAD_REQUEST,
                "Некорректный Content-Length",
            ) from error
        if not 0 <= length <= MAX_IMAGE_REQUEST_BYTES:
            raise RunnerError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "GPT Image 2 request слишком большой",
            )
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RunnerError(
                HTTPStatus.BAD_REQUEST,
                "Некорректный GPT Image 2 JSON",
            ) from error
        if not isinstance(payload, dict):
            raise RunnerError(
                HTTPStatus.BAD_REQUEST,
                "GPT Image 2 JSON должен быть объектом",
            )
        return payload

    def _binary(self, payload: bytes, mime_type: str, file_name: str) -> None:
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Disposition", f'attachment; filename="{file_name}"')
        self.end_headers()
        self.wfile.write(payload)

    def _dispatch(self) -> None:
        path = urlparse(self.path).path
        manager = self.manager
        if path == "/health":
            super()._dispatch()
            return
        if path == "/v1/images" and self.command == "POST":
            manager.authenticate(self.headers.get("Authorization"))
            if not hasattr(manager, "submit_image"):
                raise RunnerError(
                    HTTPStatus.NOT_IMPLEMENTED,
                    "GPT Image 2 runtime не установлен",
                )
            self._json(
                HTTPStatus.ACCEPTED,
                manager.submit_image(self._read_image_json()),
            )
            return
        match = re.fullmatch(r"/v1/images/([a-f0-9]{32})(/content|/stop)?", path)
        if match:
            manager.authenticate(self.headers.get("Authorization"))
            run_id, suffix = match.groups()
            if self.command == "GET" and suffix is None:
                self._json(HTTPStatus.OK, manager.image_status(run_id))
                return
            if self.command == "GET" and suffix == "/content":
                self._binary(*manager.image_content(run_id))
                return
            if self.command == "POST" and suffix == "/stop":
                self._read_image_json()
                self._json(HTTPStatus.OK, manager.stop(run_id))
                return
        super()._dispatch()


__all__ = (
    "CodexImageSupport",
    "GPT_IMAGE_MODEL_NAME",
    "ImageHandler",
    "build_image_prompt",
)
