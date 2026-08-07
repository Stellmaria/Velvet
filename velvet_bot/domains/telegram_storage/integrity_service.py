from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from velvet_bot.domains.telegram_storage.files import (
    build_zip,
    decrypt_file,
    encrypt_file,
    remove_paths,
    safe_token,
    sha256_file,
    write_json,
)
from velvet_bot.domains.telegram_storage.models import (
    MigrationSummary,
    StorageCandidate,
)
from velvet_bot.domains.telegram_storage.repository import BackupBackfillItem
from velvet_bot.domains.telegram_storage.service import (
    TelegramStorageMigrationService as BaseTelegramStorageMigrationService,
)


class TelegramStorageMigrationService(BaseTelegramStorageMigrationService):
    """Storage migration with stable semantic dedupe for generated artifacts."""

    async def _existing_object_id(self, kind: str, logical_key: str) -> int | None:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT id
                FROM telegram_storage_objects
                WHERE storage_kind = $1::VARCHAR
                  AND logical_key = $2::TEXT
                ORDER BY migrated_at DESC, id DESC
                LIMIT 1
                """,
                kind,
                logical_key,
            )
        return int(value) if value is not None else None

    async def _skip_existing_backup(
        self,
        *,
        summary: MigrationSummary,
        item: BackupBackfillItem,
        manifest_path: Path,
        object_id: int,
    ) -> None:
        summary.skipped_files += 1
        summary.bump("backups", "skipped")
        if item.run_id is not None:
            await self.repository.mark_backup_offloaded(item.run_id, object_id)
        if not self.settings.delete_after_upload:
            return
        paths = tuple(
            path for path in (item.path, manifest_path) if path.exists()
        )
        if not paths:
            return
        result = await asyncio.to_thread(
            remove_paths,
            paths,
            policy=self.settings.deletion_policy_for("backups"),
        )
        summary.deleted_files += result.deleted_count
        summary.freed_bytes += result.freed_bytes
        summary.bump("backups", "deleted", result.deleted_count)
        if result.complete and result.deleted_count:
            await self.repository.mark_local_deleted(object_id)

    async def _migrate_backups(self, summary: MigrationSummary) -> None:
        items = await self.repository.list_backup_backfill(self.settings.backup_dir)
        backup_stage = self.settings.staging_dir / "backups"
        backup_stage.mkdir(parents=True, exist_ok=True)
        for item in items:
            self._record_discovered(summary, "backups")
            token = safe_token(f"{item.run_id or 'raw'}-{item.file_name}")
            zip_path = backup_stage / f"{token}.zip"
            encrypted_path = backup_stage / f"{token}.velvet.enc"
            verify_path = backup_stage / f"{token}.verify.zip"
            manifest_path = item.path.with_suffix(item.path.suffix + ".json")
            try:
                source_digest = item.sha256 or await asyncio.to_thread(
                    sha256_file,
                    item.path,
                )
                logical_key = f"backup:{item.run_id or item.file_name}:{source_digest}"
                existing_id = await self._existing_object_id("backups", logical_key)
                if existing_id is not None:
                    await self._skip_existing_backup(
                        summary=summary,
                        item=item,
                        manifest_path=manifest_path,
                        object_id=existing_id,
                    )
                    continue

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
                            "encryption_key_id": self.settings.encryption_key_id,
                            "encryption_version": "AES-256-GCM+scrypt:v2",
                            "packed_at": datetime.now(UTC).isoformat(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                }
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
                    self.settings.encryption_keyring,
                )
                await asyncio.to_thread(
                    decrypt_file,
                    encrypted_path,
                    verify_path,
                    self.settings.encryption_keyring,
                )
                if await asyncio.to_thread(sha256_file, verify_path) != zip_digest:
                    raise ValueError(
                        "Проверка расшифровки backup не совпала с исходным ZIP."
                    )
                verify_path.unlink(missing_ok=True)

                candidate = StorageCandidate(
                    kind="backups",
                    path=encrypted_path,
                    logical_key=logical_key,
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
                        "encryption_key_id": self.settings.encryption_key_id,
                    },
                )
                stored_object, deleted, freed, duplicate = await self.uploader.upload(
                    candidate,
                    manifest=candidate.metadata,
                    encryption_version="AES-256-GCM+scrypt:v2",
                )
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
                    await self.repository.mark_backup_offloaded(
                        item.run_id,
                        stored_object.object_id,
                    )
            except Exception as error:  # p2-approved-boundary: isolate-telegram-storage-operation
                remove_paths((zip_path, encrypted_path, verify_path))
                self._record_failure(summary, "backups", item.file_name, error)

    async def _snapshot_rework(self, summary: MigrationSummary) -> None:
        rows = await self.repository.rework_snapshot()
        if not rows:
            return
        content_hash = hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        logical_key = f"rework:snapshot:{content_hash}"
        if await self._existing_object_id("rework", logical_key) is not None:
            self._record_discovered(summary, "rework")
            summary.skipped_files += 1
            summary.bump("rework", "skipped")
            return

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
            logical_key=logical_key,
            original_name=snapshot.name,
            source_path="postgresql:media_rework_items",
            mime_type="application/json",
            delete_paths=(snapshot,),
            metadata={"item_count": len(rows), "content_sha256": content_hash},
        )
        await self._upload_candidate(summary, candidate)


__all__ = ("TelegramStorageMigrationService",)
