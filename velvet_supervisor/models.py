from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass(slots=True)
class OperationState:
    id: str
    kind: str
    status: str = "queued"
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str = ""
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, kind: str, message: str = "") -> "OperationState":
        return cls(id=uuid4().hex[:12], kind=kind, message=message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "created_at": iso_or_none(self.created_at),
            "started_at": iso_or_none(self.started_at),
            "finished_at": iso_or_none(self.finished_at),
            "message": self.message,
            "error": self.error,
            "result": self.result,
        }


@dataclass(slots=True)
class CodexTask:
    id: str
    prompt: str
    requested_by: str
    status: str = "queued"
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    base_sha: str | None = None
    branch: str | None = None
    worktree: str | None = None
    commit_sha: str | None = None
    changed_files: list[str] = field(default_factory=list)
    test_output: str = ""
    codex_output: str = ""
    diff: str = ""
    error: str | None = None
    applied_at: datetime | None = None
    pushed_at: datetime | None = None

    @classmethod
    def create(cls, prompt: str, requested_by: str) -> "CodexTask":
        return cls(
            id=uuid4().hex[:12],
            prompt=prompt.strip(),
            requested_by=requested_by.strip() or "telegram",
        )

    def to_dict(self, *, include_large_fields: bool = False) -> dict[str, Any]:
        result = {
            "id": self.id,
            "prompt": self.prompt,
            "requested_by": self.requested_by,
            "status": self.status,
            "created_at": iso_or_none(self.created_at),
            "started_at": iso_or_none(self.started_at),
            "finished_at": iso_or_none(self.finished_at),
            "base_sha": self.base_sha,
            "branch": self.branch,
            "worktree": self.worktree,
            "commit_sha": self.commit_sha,
            "changed_files": list(self.changed_files),
            "error": self.error,
            "applied_at": iso_or_none(self.applied_at),
            "pushed_at": iso_or_none(self.pushed_at),
        }
        if include_large_fields:
            result.update(
                {
                    "test_output": self.test_output,
                    "codex_output": self.codex_output,
                    "diff": self.diff,
                }
            )
        else:
            result.update(
                {
                    "test_output_tail": self.test_output[-5000:],
                    "codex_output_tail": self.codex_output[-5000:],
                    "diff": self.diff[:30000],
                }
            )
        return result

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CodexTask":
        def parse_dt(value: Any) -> datetime | None:
            return datetime.fromisoformat(value) if isinstance(value, str) and value else None

        return cls(
            id=str(payload["id"]),
            prompt=str(payload.get("prompt", "")),
            requested_by=str(payload.get("requested_by", "telegram")),
            status=str(payload.get("status", "error")),
            created_at=parse_dt(payload.get("created_at")) or utc_now(),
            started_at=parse_dt(payload.get("started_at")),
            finished_at=parse_dt(payload.get("finished_at")),
            base_sha=payload.get("base_sha"),
            branch=payload.get("branch"),
            worktree=payload.get("worktree"),
            commit_sha=payload.get("commit_sha"),
            changed_files=[str(value) for value in payload.get("changed_files", [])],
            test_output=str(payload.get("test_output", "")),
            codex_output=str(payload.get("codex_output", "")),
            diff=str(payload.get("diff", "")),
            error=payload.get("error"),
            applied_at=parse_dt(payload.get("applied_at")),
            pushed_at=parse_dt(payload.get("pushed_at")),
        )


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def save(self, payload: dict[str, Any]) -> None:
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self._path)


__all__ = (
    "CodexTask",
    "JsonStateStore",
    "OperationState",
    "iso_or_none",
    "utc_now",
)
