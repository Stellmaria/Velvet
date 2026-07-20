from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Awaitable, Callable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from velvet_bot.database import Database
from velvet_bot.domains.public_archive.watermark_repository import (
    PublicArchiveWatermarkRepository,
)
from velvet_bot.domains.telegram_storage.files import (
    build_zip,
    decrypt_file,
    encrypt_file,
    remove_paths,
    safe_token,
    sha256_file,
    storage_message_link,
    write_json,
)
from velvet_bot.domains.telegram_storage.models import (
    MigrationSummary,
    StorageCandidate,
    StoredPart,
    TelegramStorageSettings,
)
from velvet_bot.domains.telegram_storage.repository import (
    BackupBackfillItem,
    TelegramStorageRepository,
    WatermarkBackfillItem,
)
from velvet_bot.domains.telegram_storage.uploader import TelegramStorageUploader
from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str], Awaitable[None]]

_ACTIVE_CODEX_STATUSES = {"queued", "running", "testing"}
_SENSITIVE_SUFFIXES = {".key", ".pem", ".pfx", ".p12", ".crt", ".cer"}
_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".venv314",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}
_RELEASE_PATTERNS = ("*.zip", "*.7z", "*.rar", "*.tar", "*.tar.gz", "*.tgz")


class TelegramStorageMigrationService:
    _run_lock = asyncio.Lock()

    def __init__(
        self,
        *,
        bot: Bot,
        database: Database,
        settings: TelegramStorageSettings | None = None,
    ) -> None:
        self._bot = bot
        self._database = database
        self.settings = settings or TelegramStorageSettings.from_env()
        self.repository = TelegramStorageRepository(database)
        self.uploader = TelegramStorageUploader(
            bot=bot,
            repository=self.repository,
            settings=self.settings,
        )
        self.bridge = KritaBridge(default_krita_bridge_dir())

    async def run(
        self,
        *,
        migration_kind: str = "manual",
        requested_by: int | None = None,
        progress: ProgressCallback | None = None,
    ) -> MigrationSummary:
        if self._run_lock.locked():
            raise RuntimeError("Перенос в Telegram уже выполняется.")
        async with self._run_lock:
            run_id = await self.repository.start_run(migration_kind, requested_by)
            summary = MigrationSummary(run_id=run_id, migration_kind=migration_kind)
            self.settings.staging_dir.mkdir(parents=True, exist_ok=True)
            try:
                await self._notify(progress, "Watermarks Final: перенос и очистка")
                await self._migrate_watermarks(summary)
                await self._notify(progress, "DB Backups: шифрование и выгрузка")
                await self._migrate_backups(summary)
                await self._notify(progress, "Diagnostics: старые логи и инциденты")
                await self._migrate_diagnostics(summary)
                await self._notify(progress, "Exports Reports: выгрузка отчётов")
                await self._migrate_exports(summary)
                await self._notify(progress, "Codex Patches: упаковка завершённых задач")
                await self._migrate_codex(summary)
                await self._notify(progress, "Releases Emergency: перенос сборок")
                await self._migrate_releases(summary)
                await self._notify(progress, "Rework Review: снимок очереди")
                await self._snapshot_rework(summary)
            except Exception as error:
                logger.exception("Telegram storage migration failed run=%s", run_id)
                summary.failed_files += 1
                summary.errors.append(f"fatal: {error}")
            finally:
                await self.repository.finish_run(summary)
                self._remove_empty_directories()
            return summary

    async def run_initial_if_needed(self) -> MigrationSummary | None:
        if not self.settings.migrate_on_start:
            return None
        if await self.repository.initial_run_completed():
            return None
        return await self.run(migration_kind="initial_full")

    @staticmethod
    async def _notify(progress: ProgressCallback | None, text: str) -> None:
        if progress is not None:
            await progress(text)

    def _record_discovered(self, summary: MigrationSummary, kind: str) -> None:
        summary.discovered_files += 1
        summary.bump(kind, "discovered")

    def _record_failure(
        self,
        summary: MigrationSummary,
        kind: str,
        label: str,
        error: Exception,
    ) -> None:
        summary.failed_files += 1
        summary.bump(kind, "failed")
        summary.errors.append(f"{kind}:{label}: {error}"[:2000])
        logger.warning("Storage migration failed kind=%s item=%s: %s", kind, label, error)

    async def _upload_candidate(
        self,
        summary: MigrationSummary,
        candidate: StorageCandidate,
        *,
        manifest: dict | None = None,
        encryption_version: str | None = None,
    ):
        self._record_discovered(summary, candidate.kind)
        try:
            stored, deleted, freed, duplicate = await self.uploader.upload(
                candidate,
                manifest=manifest,
                encryption_version=encryption_version,
            )
        except Exception as error:
            self._record_failure(summary, candidate.kind, candidate.logical_key, error)
            return None
        if duplicate:
            summary.skipped_files += 1
            summary.bump(candidate.kind, "skipped")
        else:
            summary.stored_files += 1
            summary.bump(candidate.kind, "stored")
        summary.deleted_files += deleted
        summary.freed_bytes += freed
        summary.bump(candidate.kind, "deleted", deleted)
        return stored

    @staticmethod
    def _fallback_telegram_sha(item: WatermarkBackfillItem) -> str:
        identity = item.telegram_file_unique_id or item.telegram_file_id
        return hashlib.sha256(("telegram:" + identity).encode("utf-8")).hexdigest()

    async def _migrate_watermarks(self, summary: MigrationSummary) -> None:
        for item in await self.repository.list_watermarks_for_backfill(limit=5000):
            self._record_discovered(summary, "watermarks")
            digest = (
                await asyncio.to_thread(sha256_file, item.final_path)
                if item.final_path is not None and item.final_path.is_file()
                else self._fallback_telegram_sha(item)
            )
            logical_key = f"watermark:media:{item.media_id}"
            existing = await self.repository.get_existing("watermarks", logical_key, digest)
            if existing is not None and existing.parts:
                part = existing.parts[0]
                await self.repository.mark_watermark_backfilled(
                    media_id=item.media_id,
                    chat_id=existing.chat_id,
                    thread_id=existing.thread_id,
                    message_id=part.message_id,
                    telegram_file_id=part.telegram_file_id,
                    telegram_file_unique_id=part.telegram_file_unique_id,
                    file_size=part.size_bytes,
                    sha256=digest,
                )
                summary.skipped_files += 1
                summary.bump("watermarks", "skipped")
                continue

            characters = ", ".join(item.character_names) or "не привязаны"
            caption = "\n".join(
                (
                    f"#velvet_watermark #media_{item.media_id} #sha_{digest[:12]}",
                    f"Media ID: {item.media_id}",
                    f"Персонажи: {characters}",
                    f"Исходник: {item.file_name}",
                    f"Job: {item.job_id or 'legacy'} · revision: {item.revision or 'legacy'}",
                    f"SHA256: {digest}",
                )
            )[:1024]
            message = None
            try:
                message = await self._bot.send_document(
                    chat_id=self.settings.chat_id,
                    message_thread_id=self.settings.threads.watermarks,
                    document=item.telegram_file_id,
                    caption=caption,
                    disable_notification=True,
                )
                if message.document is None:
                    raise ValueError("Telegram не вернул file_id watermark-документа.")
                part = StoredPart(
                    part_number=1,
                    message_id=message.message_id,
                    telegram_file_id=message.document.file_id,
                    telegram_file_unique_id=message.document.file_unique_id,
                    size_bytes=int(message.document.file_size or item.file_size or 0),
                    sha256=digest,
                )
                candidate = StorageCandidate(
                    kind="watermarks",
                    path=item.final_path or Path(item.file_name),
                    logical_key=logical_key,
                    original_name=item.file_name,
                    source_path=str(item.final_path) if item.final_path else None,
                    mime_type="image/png",
                    metadata={
                        "media_id": item.media_id,
                        "job_id": item.job_id,
                        "revision": item.revision,
                        "characters": list(item.character_names),
                        "hash_source": (
                            "local_file"
                            if item.final_path is not None and item.final_path.is_file()
                            else "telegram_file_unique_id"
                        ),
                    },
                )
                stored = await self.repository.create_object(
                    candidate=candidate,
                    sha256=digest,
                    size_bytes=part.size_bytes,
                    chat_id=self.settings.chat_id,
                    thread_id=self.settings.threads.watermarks,
                    parts=(part,),
                    manifest=candidate.metadata,
                    encryption_version=None,
                )
                await self.repository.mark_watermark_backfilled(
                    media_id=item.media_id,
                    chat_id=stored.chat_id,
                    thread_id=stored.thread_id,
                    message_id=part.message_id,
                    telegram_file_id=part.telegram_file_id,
                    telegram_file_unique_id=part.telegram_file_unique_id,
                    file_size=part.size_bytes,
                    sha256=digest,
                )
                summary.stored_files += 1
                summary.bump("watermarks", "stored")
            except Exception as error:
                if message is not None:
                    try:
                        await self._bot.delete_message(
                            chat_id=self.settings.chat_id,
                            message_id=message.message_id,
                        )
                    except TelegramAPIError:
                        pass
                self._record_failure(summary, "watermarks", logical_key, error)

        await self._migrate_and_cleanup_watermark_jobs(summary)

    async def _migrate_and_cleanup_watermark_jobs(self, summary: MigrationSummary) -> None:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT wj.id, wj.status, wj.source_message_id, wj.source_path,
                       wj.final_path, wj.current_revision,
                       ARRAY_REMOVE(ARRAY_AGG(DISTINCT paths.path_value), NULL) AS paths
                FROM watermark_jobs AS wj
                LEFT JOIN watermark_revisions AS wr ON wr.job_id = wj.id
                LEFT JOIN LATERAL unnest(ARRAY[
                    wr.request_path, wr.output_path, wr.response_path
                ]) AS paths(path_value) ON TRUE
                WHERE wj.status IN ('approved', 'cancelled')
                GROUP BY wj.id
                ORDER BY wj.id
                """
            )
        archive_repository = PublicArchiveWatermarkRepository(self._database)
        for row in rows:
            job_id = int(row["id"])
            status = str(row["status"])
            media_id = -int(row["source_message_id"]) if int(row["source_message_id"]) < 0 else None
            paths = [Path(row["source_path"])]
            if row["final_path"]:
                paths.append(Path(row["final_path"]))
            paths.extend(Path(value) for value in (row["paths"] or ()))
            for directory in (
                self.bridge.paths.requests,
                self.bridge.paths.responses,
                self.bridge.paths.outputs,
                self.bridge.paths.previews,
            ):
                paths.extend(directory.glob(f"job-{job_id}-r*"))
            safe_paths = self._safe_bridge_paths(paths)

            if status == "cancelled":
                deleted, freed = await asyncio.to_thread(remove_paths, safe_paths)
                summary.deleted_files += deleted
                summary.freed_bytes += freed
                summary.bump("watermarks", "deleted", deleted)
                continue

            if media_id is not None:
                if await archive_repository.get_storage(media_id) is None:
                    continue
                deleted, freed = await asyncio.to_thread(remove_paths, safe_paths)
                summary.deleted_files += deleted
                summary.freed_bytes += freed
                summary.bump("watermarks", "deleted", deleted)
                if deleted:
                    await self.repository.mark_watermark_cleaned(media_id)
                continue

            final_path = Path(row["final_path"]) if row["final_path"] else None
            if final_path is None or not final_path.is_file():
                continue
            candidate = StorageCandidate(
                kind="watermarks",
                path=final_path,
                logical_key=f"watermark:job:{job_id}:revision:{int(row['current_revision'])}",
                original_name=f"velvet-watermark-job-{job_id}.png",
                source_path=str(final_path),
                mime_type="image/png",
                delete_paths=tuple(safe_paths),
                metadata={"job_id": job_id, "revision": int(row["current_revision"])},
            )
            await self._upload_candidate(summary, candidate)

    def _safe_bridge_paths(self, paths) -> tuple[Path, ...]:
        safe: list[Path] = []
        for value in paths:
            try:
                safe.append(self.bridge.paths.ensure_inside(value))
            except ValueError:
                logger.warning("Refusing to delete path outside Krita bridge: %s", value)
        return tuple(dict.fromkeys(safe))

    async def _migrate_backups(self, summary: MigrationSummary) -> None:
        items = await self.repository.list_backup_backfill(self.settings.backup_dir)
        backup_stage = self.settings.staging_dir / "backups"
        backup_stage.mkdir(parents=True, exist_ok=True)
        for item in items:
            self._record_discovered(summary, "backups")
            source_digest = item.sha256 or await asyncio.to_thread(sha256_file, item.path)
            token = safe_token(f"{item.run_id or 'raw'}-{item.file_name}")
            zip_path = backup_stage / f"{token}.zip"
            encrypted_path = backup_stage / f"{token}.velvet.enc"
            verify_path = backup_stage / f"{token}.verify.zip"
            manifest_path = item.path.with_suffix(item.path.suffix + ".json")
            files = {item.file_name: item.path}
            if manifest_path.is_file():
                files[manifest_path.name] = manifest_path
            text_entries = {
                "storage-manifest.json": json.dumps(
                    {
                        "backup_run_id": item.run_id,
                        "backup_kind": item.backup_kind,
                        "schema_version": item.schema_version,
                        "source_sha256": source_digest,
                        "validation": item.validation,
                        "packed_at": datetime.now(UTC).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            }
            try:
                await asyncio.to_thread(
                    build_zip,
                    zip_path,
                    files=files,
                    text_entries=text_entries,
                )
                zip_digest = await asyncio.to_thread(sha256_file, zip_path)
                await asyncio.to_thread(
                    encrypt_file,
                    zip_path,
                    encrypted_path,
                    self.settings.encryption_secret,
                )
                await asyncio.to_thread(
                    decrypt_file,
                    encrypted_path,
                    verify_path,
                    self.settings.encryption_secret,
                )
                if await asyncio.to_thread(sha256_file, verify_path) != zip_digest:
                    raise ValueError("Проверка расшифровки backup не совпала с исходным ZIP.")
                verify_path.unlink(missing_ok=True)

                candidate = StorageCandidate(
                    kind="backups",
                    path=encrypted_path,
                    logical_key=f"backup:{item.run_id or item.file_name}:{source_digest}",
                    original_name=encrypted_path.name,
                    source_path=str(item.path),
                    mime_type="application/octet-stream",
                    encrypted=True,
                    delete_paths=tuple(
                        path
                        for path in (item.path, manifest_path, zip_path, encrypted_path)
                        if path.exists()
                    ),
                    metadata={
                        "backup_run_id": item.run_id,
                        "backup_kind": item.backup_kind,
                        "schema_version": item.schema_version,
                        "source_sha256": source_digest,
                        "zip_sha256": zip_digest,
                    },
                )
                stored = await self.uploader.upload(
                    candidate,
                    manifest=candidate.metadata,
                    encryption_version="AES-256-GCM+scrypt:v1",
                )
                stored_object, deleted, freed, duplicate = stored
                if duplicate:
                    summary.skipped_files += 1
                    summary.bump("backups", "skipped")
                else:
                    summary.stored_files += 1
                    summary.bump("backups", "stored")
                summary.deleted_files += deleted
                summary.freed_bytes += freed
                summary.bump("backups", "deleted", deleted)
                if item.run_id is not None:
                    await self.repository.mark_backup_offloaded(item.run_id, stored_object.object_id)
            except Exception as error:
                remove_paths((zip_path, encrypted_path, verify_path))
                self._record_failure(summary, "backups", item.file_name, error)

    def _skip_file(self, path: Path, *, allow_recent: bool = False) -> bool:
        if not path.is_file() or path.is_symlink():
            return True
        if any(part.casefold() in _EXCLUDED_PARTS for part in path.parts):
            return True
        if path.name.casefold().startswith(".env"):
            return True
        if path.suffix.casefold() in _SENSITIVE_SUFFIXES:
            return True
        if not allow_recent:
            age = time.time() - path.stat().st_mtime
            if age < self.settings.active_file_grace_seconds:
                return True
        try:
            path.resolve().relative_to(self.settings.staging_dir.resolve())
            return True
        except ValueError:
            return False

    def _iter_root_files(self, roots: tuple[Path, ...]) -> list[tuple[Path, Path]]:
        result: list[tuple[Path, Path]] = []
        seen: set[Path] = set()
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                resolved = path.resolve()
                if resolved in seen or self._skip_file(resolved):
                    continue
                seen.add(resolved)
                result.append((root, resolved))
        return result

    async def _migrate_file_roots(
        self,
        summary: MigrationSummary,
        *,
        kind: str,
        roots: tuple[Path, ...],
    ) -> None:
        for root, path in self._iter_root_files(roots):
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                relative = path.name
            mime_type = mimetypes.guess_type(path.name)[0]
            candidate = StorageCandidate(
                kind=kind,
                path=path,
                logical_key=f"{kind}:{root.name}:{relative}",
                original_name=path.name,
                source_path=str(path),
                mime_type=mime_type,
                delete_paths=(path,),
                metadata={"relative_path": relative, "root": str(root)},
            )
            await self._upload_candidate(summary, candidate)

    async def _migrate_diagnostics(self, summary: MigrationSummary) -> None:
        roots = (
            self.settings.logs_dir,
            self.settings.project_dir / "diagnostics",
            self.settings.runtime_dir / "incidents",
        )
        await self._migrate_file_roots(summary, kind="diagnostics", roots=roots)

    async def _migrate_exports(self, summary: MigrationSummary) -> None:
        await self._migrate_file_roots(
            summary,
            kind="exports",
            roots=self.settings.export_dirs,
        )

    async def _migrate_codex(self, summary: MigrationSummary) -> None:
        tasks_path = self.settings.runtime_dir / "codex_tasks.json"
        if not tasks_path.is_file():
            return
        try:
            payload = json.loads(tasks_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            self._record_failure(summary, "codex", str(tasks_path), error)
            return
        tasks = payload.get("tasks", [])
        if not isinstance(tasks, list):
            return
        changed = False
        codex_stage = self.settings.staging_dir / "codex"
        codex_stage.mkdir(parents=True, exist_ok=True)
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("id") or "").strip()
            status = str(task.get("status") or "").strip()
            if not task_id or status in _ACTIVE_CODEX_STATUSES:
                continue
            logical_key = f"codex:{task_id}:{task.get('commit_sha') or status}"
            archive_path = codex_stage / f"codex-{safe_token(task_id)}.zip"
            text_entries = {
                "task.json": json.dumps(task, ensure_ascii=False, indent=2, default=str),
                "prompt.txt": str(task.get("prompt") or ""),
                "codex-output.txt": str(task.get("codex_output") or ""),
                "test-output.txt": str(task.get("test_output") or ""),
                "changes.diff": str(task.get("diff") or ""),
            }
            worktree_raw = str(task.get("worktree") or "").strip()
            worktree = Path(worktree_raw).expanduser().resolve() if worktree_raw else None
            if worktree is not None and worktree.is_dir():
                text_entries.update(await asyncio.to_thread(self._git_snapshot, worktree))
            try:
                await asyncio.to_thread(
                    build_zip,
                    archive_path,
                    files={},
                    text_entries=text_entries,
                )
                candidate = StorageCandidate(
                    kind="codex",
                    path=archive_path,
                    logical_key=logical_key,
                    original_name=archive_path.name,
                    source_path=str(worktree) if worktree else str(tasks_path),
                    mime_type="application/zip",
                    delete_paths=(archive_path,),
                    metadata={
                        "task_id": task_id,
                        "status": status,
                        "commit_sha": task.get("commit_sha"),
                        "branch": task.get("branch"),
                        "changed_files": task.get("changed_files") or [],
                    },
                )
                stored = await self._upload_candidate(summary, candidate)
                if stored is None:
                    continue
                if worktree is not None and worktree.is_dir():
                    await asyncio.to_thread(self._remove_git_worktree, worktree)
                task["worktree"] = None
                task["codex_output"] = ""
                task["test_output"] = ""
                task["diff"] = ""
                task["storage_object_id"] = stored.object_id
                task["storage_archived_at"] = datetime.now(UTC).isoformat()
                changed = True
            except Exception as error:
                archive_path.unlink(missing_ok=True)
                self._record_failure(summary, "codex", task_id, error)
        if changed:
            temporary = tasks_path.with_suffix(".json.storage.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            os.replace(temporary, tasks_path)

    def _git_snapshot(self, worktree: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, arguments in (
            ("git-status.txt", ("status", "--short", "--branch")),
            ("git-log.txt", ("log", "-1", "--decorate", "--stat")),
        ):
            process = subprocess.run(
                ("git", "-C", str(worktree), *arguments),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            result[name] = (process.stdout + process.stderr)[-200000:]
        return result

    def _remove_git_worktree(self, worktree: Path) -> None:
        project = self.settings.project_dir
        process = subprocess.run(
            ("git", "-C", str(project), "worktree", "remove", "--force", str(worktree)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        if process.returncode and worktree.exists():
            shutil.rmtree(worktree)
        subprocess.run(
            ("git", "-C", str(project), "worktree", "prune"),
            capture_output=True,
            timeout=60,
            check=False,
        )

    async def _migrate_releases(self, summary: MigrationSummary) -> None:
        roots = list(self.settings.release_dirs)
        await self._migrate_file_roots(summary, kind="releases", roots=tuple(roots))
        seen: set[Path] = set()
        for pattern in _RELEASE_PATTERNS:
            for path in sorted(self.settings.project_dir.glob(pattern)):
                resolved = path.resolve()
                if resolved in seen or self._skip_file(resolved):
                    continue
                seen.add(resolved)
                candidate = StorageCandidate(
                    kind="releases",
                    path=resolved,
                    logical_key=f"releases:project-root:{resolved.name}",
                    original_name=resolved.name,
                    source_path=str(resolved),
                    mime_type=mimetypes.guess_type(resolved.name)[0],
                    delete_paths=(resolved,),
                    metadata={"root": str(self.settings.project_dir)},
                )
                await self._upload_candidate(summary, candidate)

    async def _snapshot_rework(self, summary: MigrationSummary) -> None:
        rows = await self.repository.rework_snapshot()
        if not rows:
            return
        content_hash = hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        snapshot = self.settings.staging_dir / "rework" / (
            f"rework-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{content_hash[:12]}.json"
        )
        await asyncio.to_thread(
            write_json,
            snapshot,
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "count": len(rows),
                "items": rows,
            },
        )
        candidate = StorageCandidate(
            kind="rework",
            path=snapshot,
            logical_key=f"rework:snapshot:{content_hash}",
            original_name=snapshot.name,
            source_path="postgresql:media_rework_items",
            mime_type="application/json",
            delete_paths=(snapshot,),
            metadata={"item_count": len(rows), "content_sha256": content_hash},
        )
        await self._upload_candidate(summary, candidate)

    def _remove_empty_directories(self) -> None:
        roots = (
            self.settings.logs_dir,
            *self.settings.export_dirs,
            *self.settings.release_dirs,
            self.settings.staging_dir,
        )
        for root in roots:
            if not root.is_dir():
                continue
            for directory in sorted(
                (path for path in root.rglob("*") if path.is_dir()),
                key=lambda value: len(value.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    pass


__all__ = ("TelegramStorageMigrationService",)
