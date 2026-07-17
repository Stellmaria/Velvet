from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from velvet_bot.domains.watermark.models import WatermarkWorkItem


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
        root_path = Path(root).expanduser().resolve()
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

    def ensure_inside(self, path: str | Path) -> Path:
        resolved = Path(path).expanduser().resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise ValueError("Путь Krita bridge выходит за рабочий каталог.") from error
        return resolved


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

        source_path = self.paths.ensure_inside(item.job.source_path)
        self.paths.ensure_inside(output_path)
        self.paths.ensure_inside(response_path)

        payload: dict[str, Any] = {
            "schema_version": 1,
            "request_id": f"wm-{job_id}",
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
        path = self.paths.ensure_inside(response_path)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Krita bridge вернул некорректный JSON.")
        return payload


__all__ = ("KritaBridge", "KritaBridgePaths", "default_krita_bridge_dir")
