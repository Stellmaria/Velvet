#!/usr/bin/env python3
from __future__ import annotations

import io
import json
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

import codex_image_runner as image_runner
from codex_runner import RunnerError

_HIGH_RESOLUTIONS = frozenset({"2K", "4K"})
_INSTALLED = False


def target_dimensions(resolution: str, aspect_ratio: str) -> tuple[int, int]:
    normalized = resolution.strip().upper()
    if normalized not in {"1K", "2K", "4K"}:
        raise ValueError("Недоступное качество GPT Image 2")
    left, right = (int(value) for value in aspect_ratio.split(":", 1))
    if left <= 0 or right <= 0:
        raise ValueError("Некорректная пропорция GPT Image 2")
    edge = {"1K": 1024, "2K": 2048, "4K": 3840}[normalized]
    if left >= right:
        width = edge
        height = max(2, round(edge * right / left))
    else:
        width = max(2, round(edge * left / right))
        height = edge
    return width - width % 2, height - height % 2


def build_export_prompt(
    *,
    source_name: str,
    resolution: str,
    aspect_ratio: str,
    width: int,
    height: int,
) -> str:
    return f"""ЗАДАЧА: выполнить финальный high-resolution export уже созданного изображения.

Исходник:
- /workspace/.hermes-image-inputs/{source_name}

Цель:
- качество: {resolution}
- пропорция: {aspect_ratio}
- итоговые пиксели: ровно {width}x{height}

Обязательный контракт:
1. Это не новая генерация. Не вызывай image_gen, не меняй персонажа, лицо, одежду, фон, композицию, свет, текст и другие детали исходника.
2. Запусти подготовленный локальный скрипт ровно один раз: python .hermes-image-export.py
3. Скрипт должен создать /workspace/.hermes-image-output/result.jpg.
4. После запуска проверь через Pillow, что result.jpg имеет ровно {width}x{height} пикселей.
5. Не используй сеть, GitHub и внешние API. Не создавай других изображений и не редактируй исходный код репозитория.
6. В финальном ответе выведи только путь /workspace/.hermes-image-output/result.jpg.
"""


def _export_script(
    *,
    source_name: str,
    width: int,
    height: int,
) -> str:
    return f"""from pathlib import Path
from PIL import Image, ImageOps

source = Path(\"/workspace/.hermes-image-inputs/{source_name}\")
target = Path(\"/workspace/.hermes-image-output/result.jpg\")

with Image.open(source) as opened:
    image = ImageOps.exif_transpose(opened).convert(\"RGB\")
    image = ImageOps.fit(
        image,
        ({width}, {height}),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    image.save(
        target,
        format=\"JPEG\",
        quality=95,
        subsampling=0,
        optimize=True,
        progressive=True,
    )

with Image.open(target) as verified:
    if verified.size != ({width}, {height}):
        raise SystemExit(
            f\"unexpected export dimensions: {{verified.size[0]}}x{{verified.size[1]}}\"
        )

print(target)
"""


def _needs_high_res_export(record: Mapping[str, object]) -> bool:
    return bool(
        str(record.get("status") or "") == "completed"
        and str(record.get("resolution") or "").strip().upper()
        in _HIGH_RESOLUTIONS
        and str(record.get("actual_route") or "") != "byesu_media"
        and record.get("high_res_export_completed") is not True
    )


def _read_artifact(manager: Any, record: Mapping[str, object]) -> tuple[Path, bytes]:
    raw = str(record.get("artifact_path") or "").strip()
    if not raw:
        raise RuntimeError("Codex GPT Image 2 не сохранил исходный artifact")
    path = Path(raw)
    root = manager._image_artifacts_root().resolve()
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise RuntimeError("Codex GPT Image 2 artifact недоступен для export") from error
    if resolved.parent != root or resolved.is_symlink() or not resolved.is_file():
        raise RuntimeError("Codex GPT Image 2 artifact вышел за безопасный каталог")
    payload = resolved.read_bytes()
    if not payload or len(payload) > image_runner.MAX_IMAGE_ARTIFACT_BYTES:
        raise RuntimeError("Codex GPT Image 2 artifact пуст или слишком большой")
    return resolved, payload


def _source_suffix(record: Mapping[str, object], artifact: Path) -> str:
    suffix = artifact.suffix.casefold()
    if suffix in image_runner.IMAGE_SUFFIX_MIME_TYPES:
        return suffix
    mime = str(record.get("artifact_mime_type") or "").strip().casefold()
    for candidate, candidate_mime in image_runner.IMAGE_SUFFIX_MIME_TYPES.items():
        if candidate_mime == mime:
            return candidate
    raise RuntimeError("Неизвестный формат Codex GPT Image 2 artifact")


def _verify_dimensions(payload: bytes, expected: tuple[int, int]) -> None:
    try:
        with Image.open(io.BytesIO(payload)) as opened:
            actual = opened.size
    except Exception as error:
        raise RuntimeError("High-resolution export вернул повреждённое изображение") from error
    if actual != expected:
        raise RuntimeError(
            "High-resolution export вернул неверный размер: "
            f"{actual[0]}x{actual[1]} вместо {expected[0]}x{expected[1]}"
        )


def _run_high_res_export(manager: Any, run_id: str) -> None:
    workspace: Path | None = None
    previous_workspace = manager.workspace
    old_artifact: Path | None = None
    with manager._isolation_lock:
        try:
            record = manager.store.read(run_id)
            if not _needs_high_res_export(record):
                return
            if record.get("stop_requested"):
                manager.store.update(
                    run_id,
                    status="cancelled",
                    finished_at=image_runner.utc_now(),
                    high_res_export_completed=False,
                    last_event={"type": "image_high_res_export_cancelled"},
                )
                return

            resolution = str(record.get("resolution") or "").strip().upper()
            aspect_ratio = str(record.get("aspect_ratio") or "").strip()
            width, height = target_dimensions(resolution, aspect_ratio)
            old_artifact, source_payload = _read_artifact(manager, record)
            suffix = _source_suffix(record, old_artifact)
            source_name = f"generated{suffix}"

            manager.store.update(
                run_id,
                status="running",
                high_res_export_required=True,
                high_res_export_completed=False,
                high_res_export_target=resolution,
                high_res_export_size=f"{width}x{height}",
                last_event={
                    "type": "image_high_res_export_started",
                    "resolution": resolution,
                    "size": f"{width}x{height}",
                },
            )

            workspace, source_ref = manager._prepare_workspace(run_id)
            manager.workspace = workspace
            input_target = workspace / ".hermes-image-inputs"
            output_target = workspace / ".hermes-image-output"
            input_target.mkdir(mode=0o700)
            output_target.mkdir(mode=0o700)
            source_path = input_target / source_name
            source_path.write_bytes(source_payload)
            source_path.chmod(0o600)

            helper = workspace / ".hermes-image-export.py"
            helper.write_text(
                _export_script(
                    source_name=source_name,
                    width=width,
                    height=height,
                ),
                encoding="utf-8",
            )
            helper.chmod(0o600)

            effort = str(record.get("reasoning_effort") or "high")
            runtime_request = workspace / ".git" / "hermes-image-request.json"
            runtime_request.write_text(
                json.dumps(
                    {"task_kind": "image", "reasoning_effort": effort},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            runtime_request.chmod(0o600)

            prompt = build_export_prompt(
                source_name=source_name,
                resolution=resolution,
                aspect_ratio=aspect_ratio,
                width=width,
                height=height,
            )
            result = manager._launcher.run(
                run_id=run_id,
                project=manager.project,
                workspace=workspace,
                model=str(record.get("model") or "gpt-5.6-terra"),
                route=manager.primary_route,
                mutation_policy="workspace_write",
                timeout_seconds=manager.timeout_seconds,
                prompt=prompt,
            )
            if result.get("cancelled") or manager.store.read(run_id).get(
                "stop_requested"
            ):
                manager.store.update(
                    run_id,
                    status="cancelled",
                    finished_at=image_runner.utc_now(),
                    high_res_export_completed=False,
                    last_event={"type": "image_high_res_export_cancelled"},
                )
                return
            stdout = str(result.get("stdout") or "")
            stderr = str(result.get("stderr") or "")
            if int(result.get("returncode", 1)) != 0:
                details = image_runner.redact_text((stderr or stdout).strip()[-4000:])
                raise RuntimeError(
                    details or "Codex high-resolution export завершился с ошибкой"
                )

            candidate = manager._find_image_artifact(output_target)
            payload = candidate.read_bytes()
            if not payload or len(payload) > image_runner.MAX_IMAGE_ARTIFACT_BYTES:
                raise RuntimeError(
                    "High-resolution export вернул пустой или слишком большой файл"
                )
            candidate_suffix = candidate.suffix.casefold()
            if not image_runner._looks_like_image(payload, candidate_suffix):
                raise RuntimeError(
                    "High-resolution export вернул файл с неверной сигнатурой"
                )
            _verify_dimensions(payload, (width, height))

            artifact = (
                manager._image_artifacts_root() / f"{run_id}-hires{candidate_suffix}"
            )
            artifact.write_bytes(payload)
            artifact.chmod(0o600)
            if old_artifact != artifact:
                old_artifact.unlink(missing_ok=True)

            _, export_usage, export_last_event = image_runner.parse_jsonl_output(stdout)
            manager.store.update(
                run_id,
                status="completed",
                finished_at=image_runner.utc_now(),
                workspace_source_ref=source_ref,
                artifact_path=str(artifact),
                artifact_name=(
                    f"gpt-image-2-{run_id[:8]}-{resolution.lower()}"
                    f"{candidate_suffix}"
                ),
                artifact_mime_type=image_runner.IMAGE_SUFFIX_MIME_TYPES[
                    candidate_suffix
                ],
                artifact_bytes=len(payload),
                actual_route="codex_subscription",
                requested_route="codex_subscription",
                high_res_export_required=True,
                high_res_export_completed=True,
                high_res_export_target=resolution,
                high_res_export_size=f"{width}x{height}",
                high_res_export_usage=export_usage,
                rate_limits_after=manager._safe_rate_limits(),
                last_event=export_last_event
                or {
                    "type": "image_high_res_export_completed",
                    "resolution": resolution,
                    "size": f"{width}x{height}",
                },
            )
        except Exception as error:
            record = manager.store.read(run_id)
            if str(record.get("status") or "") != "cancelled":
                manager.store.update(
                    run_id,
                    status="failed",
                    finished_at=image_runner.utc_now(),
                    high_res_export_required=True,
                    high_res_export_completed=False,
                    error=image_runner.redact_text(str(error).strip())[-8000:]
                    or type(error).__name__,
                    last_event={
                        "type": "image_high_res_export_failed",
                        "error_type": type(error).__name__,
                    },
                )
        finally:
            manager.workspace = previous_workspace
            if workspace is not None:
                manager._cleanup_workspace(workspace)


def install_codex_image_high_res_export() -> None:
    """Add one deterministic GPT export pass after successful Codex 2K/4K generation."""
    global _INSTALLED
    if _INSTALLED:
        return

    original_execute = image_runner.CodexImageSupport._execute_image
    original_status = image_runner.CodexImageSupport.image_status
    original_content = image_runner.CodexImageSupport.image_content

    def execute_with_high_res_export(
        self: Any,
        run_id: str,
        prompt: str,
    ) -> None:
        original_execute(self, run_id, prompt)
        if _needs_high_res_export(self.store.read(run_id)):
            _run_high_res_export(self, run_id)

    def status_with_high_res_guard(self: Any, run_id: str) -> dict[str, Any]:
        payload = original_status(self, run_id)
        if (
            str(payload.get("status") or "") == "completed"
            and str(payload.get("resolution") or "").strip().upper()
            in _HIGH_RESOLUTIONS
            and str(payload.get("actual_route") or "") != "byesu_media"
            and payload.get("high_res_export_completed") is not True
        ):
            payload = dict(payload)
            payload["status"] = "running"
            payload["last_event"] = {
                "type": "image_high_res_export_pending",
                "resolution": payload.get("resolution"),
            }
        return payload

    def content_with_high_res_guard(
        self: Any,
        run_id: str,
    ) -> tuple[bytes, str, str]:
        record = self.store.read(run_id)
        if (
            str(record.get("resolution") or "").strip().upper()
            in _HIGH_RESOLUTIONS
            and str(record.get("actual_route") or "") != "byesu_media"
            and record.get("high_res_export_completed") is not True
        ):
            raise RunnerError(
                HTTPStatus.CONFLICT,
                "GPT Image 2 high-resolution export ещё не завершён",
            )
        return original_content(self, run_id)

    image_runner.CodexImageSupport._execute_image = execute_with_high_res_export
    image_runner.CodexImageSupport.image_status = status_with_high_res_guard
    image_runner.CodexImageSupport.image_content = content_with_high_res_guard
    _INSTALLED = True


__all__ = (
    "build_export_prompt",
    "install_codex_image_high_res_export",
    "target_dimensions",
)
