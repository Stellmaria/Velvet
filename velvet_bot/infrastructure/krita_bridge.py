from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from velvet_bot.domains.watermark.models import WatermarkWorkItem

ProcessingRecovery = Literal[
    "response_ready",
    "queued",
    "processing",
    "requeued",
    "missing",
    "retry_failed",
]


def default_krita_bridge_dir() -> Path:
    configured = os.getenv("KRITA_BRIDGE_DIR", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / "VelvetKritaBridge"


@dataclass(frozen=True, slots=True)
class KritaBridgePaths:
    root: Path
    requests: Path
    responses: Path
    outputs: Path
    sources: Path
    previews: Path

    @classmethod
    def build(cls, root: str | Path) -> "KritaBridgePaths":
        root_path = cls._resolve_path(root)
        paths = cls(
            root=root_path,
            requests=root_path / "requests",
            responses=root_path / "responses",
            outputs=root_path / "outputs",
            sources=root_path / "sources",
            previews=root_path / "previews",
        )
        for path in asdict(paths).values():
            Path(path).mkdir(parents=True, exist_ok=True)
        return paths

    @staticmethod
    def _resolve_path(path: str | Path) -> Path:
        raw = os.fspath(path)
        if not raw or "\x00" in raw:
            raise ValueError("Путь Krita bridge пуст или содержит недопустимые символы.")
        normalized = raw.replace("\\", "/")
        if normalized.startswith("//"):
            raise ValueError("UNC-пути запрещены для Krita bridge.")
        windows_path = PureWindowsPath(raw)
        if os.name != "nt" and windows_path.drive:
            raise ValueError("Windows drive path недопустим в этой среде.")
        return Path(raw).expanduser().resolve(strict=False)

    def ensure_inside(self, path: str | Path) -> Path:
        return self.ensure_in(path, self.root)

    def ensure_in(self, path: str | Path, *allowed_directories: Path) -> Path:
        resolved = self._resolve_path(path)
        for allowed in allowed_directories:
            allowed_resolved = Path(allowed).resolve(strict=False)
            try:
                resolved.relative_to(allowed_resolved)
                return resolved
            except ValueError:
                continue
        raise ValueError("Путь Krita bridge выходит за разрешённый каталог.")


class KritaBridge:
    def __init__(self, root: str | Path) -> None:
        self.paths = KritaBridgePaths.build(root)

    def source_path(self, *, job_id: int, suffix: str) -> Path:
        safe_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        return self.paths.sources / f"job-{job_id}{safe_suffix.lower()}"

    def dispatch(self, item: WatermarkWorkItem) -> tuple[Path, Path, Path]:
        job_id = item.job.id
        revision = item.revision.revision
        request_path = self.paths.requests / f"job-{job_id}-r{revision}.json"
        output_path = self.paths.outputs / f"job-{job_id}-r{revision}.png"
        response_path = self.paths.responses / f"job-{job_id}-r{revision}.json"

        source_path = self.paths.ensure_in(item.job.source_path, self.paths.sources)
        request_path = self.paths.ensure_in(request_path, self.paths.requests)
        output_path = self.paths.ensure_in(output_path, self.paths.outputs)
        response_path = self.paths.ensure_in(response_path, self.paths.responses)

        payload: dict[str, Any] = {
            "schema_version": 1,
            "request_id": f"wm-{job_id}-r{revision}",
            "job_id": job_id,
            "revision": revision,
            "bridge_root": str(self.paths.root),
            "source_path": str(source_path),
            "output_path": str(output_path),
            "response_path": str(response_path),
            "remove_only": not item.revision.settings.enabled,
            "settings": {
                "position": item.revision.settings.position,
                "color": item.revision.settings.color,
                "opacity": item.revision.settings.opacity,
                "size": item.revision.settings.size,
                "margin": item.revision.settings.margin,
                "lock": item.revision.settings.lock,
            },
        }
        temporary = request_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, request_path)
        return request_path, output_path, response_path

    def read_response(self, response_path: str | Path) -> dict[str, Any] | None:
        path = self.paths.ensure_in(response_path, self.paths.responses)
        if not path.exists():
            return None
        if not path.is_file():
            raise ValueError("Krita response не является обычным файлом.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Krita bridge вернул некорректный JSON.")
        return payload

    def validate_response_output(
        self,
        output_path: str | Path,
        *,
        expected_path: str | Path | None,
    ) -> Path:
        resolved = self.paths.ensure_in(
            output_path,
            self.paths.outputs,
            self.paths.previews,
        )
        if expected_path is not None:
            expected = self.paths.ensure_in(
                expected_path,
                self.paths.outputs,
                self.paths.previews,
            )
            if resolved != expected:
                raise ValueError("Krita response ссылается не на ожидаемый output.")
        return resolved

    def recover_processing(
        self,
        *,
        request_path: str | Path,
        response_path: str | Path,
        stale_after_seconds: int,
        now: float | None = None,
    ) -> ProcessingRecovery:
        """Recover one database processing revision without creating duplicate requests."""
        request = self.paths.ensure_in(request_path, self.paths.requests)
        response = self.paths.ensure_in(response_path, self.paths.responses)
        processing = self.paths.ensure_in(
            request.with_suffix(".processing"),
            self.paths.requests,
        )

        if response.exists():
            return "response_ready"
        if request.exists():
            return "queued"
        if not processing.exists():
            return "missing"

        age = (time.time() if now is None else now) - processing.stat().st_mtime
        if age < max(30, stale_after_seconds):
            return "processing"

        try:
            os.replace(processing, request)
        except OSError:
            return "retry_failed"
        return "requeued"


__all__ = (
    "KritaBridge",
    "KritaBridgePaths",
    "ProcessingRecovery",
    "default_krita_bridge_dir",
)
