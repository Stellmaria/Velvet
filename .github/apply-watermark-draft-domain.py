from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one block in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


repository = Path("velvet_bot/domains/watermark/repository.py")
replace_once(
    repository,
    'CancelResult = Literal["cancelled", "already_cancelled", "approved"]\n',
    'CancelResult = Literal["cancelled", "already_cancelled", "approved"]\nRevisionStatus = Literal["draft", "pending"]\n',
)
replace_once(
    repository,
    """        source_path: str,
        settings: WatermarkSettings,
        workspace_id: int = 1,
""",
    """        source_path: str,
        settings: WatermarkSettings,
        revision_status: RevisionStatus = "pending",
        workspace_id: int = 1,
""",
)
replace_once(
    repository,
    """                    revision=1,
                    settings=settings,
                )
""",
    """                    revision=1,
                    settings=settings,
                    status=revision_status,
                )
""",
)
replace_once(
    repository,
    """        job_id: int,
        *,
        settings: WatermarkSettings,
    ) -> WatermarkWorkItem:
""",
    """        job_id: int,
        *,
        settings: WatermarkSettings,
        revision_status: RevisionStatus = "pending",
    ) -> WatermarkWorkItem:
""",
)
replace_once(
    repository,
    """                    revision=revision,
                    settings=settings,
                )
""",
    """                    revision=revision,
                    settings=settings,
                    status=revision_status,
                )
""",
)
replace_once(
    repository,
    """    async def undo(self, job_id: int) -> WatermarkWorkItem:
""",
    """    async def undo(
        self,
        job_id: int,
        *,
        revision_status: RevisionStatus = "pending",
    ) -> WatermarkWorkItem:
""",
)
replace_once(
    repository,
    """        return await self.create_revision(job_id, settings=self._settings_from_row(row))

    async def set_control_message(self, job_id: int, message_id: int) -> None:
""",
    """        return await self.create_revision(
            job_id,
            settings=self._settings_from_row(row),
            revision_status=revision_status,
        )

    async def queue_revision(self, *, job_id: int, revision: int) -> WatermarkWorkItem:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    \"\"\"
                    UPDATE watermark_revisions
                    SET status = 'pending',
                        request_path = NULL,
                        output_path = NULL,
                        response_path = NULL,
                        telegram_preview_file_id = NULL,
                        error = NULL,
                        completed_at = NULL
                    WHERE job_id = $1
                      AND revision = $2
                      AND status IN ('draft', 'error')
                    \"\"\",
                    int(job_id),
                    int(revision),
                )
                if not result.endswith("1"):
                    raise ValueError("Черновик уже изменился. Обновите карточку.")
                row = await connection.fetchrow(self._current_query(), int(job_id))
        if row is None:
            raise ValueError("Задание водяного знака не найдено.")
        return self._map_work_item(row)

    async def set_control_message(self, job_id: int, message_id: int) -> None:
""",
)
replace_once(
    repository,
    """        revision: int,
        settings: WatermarkSettings,
    ):
""",
    """        revision: int,
        settings: WatermarkSettings,
        status: RevisionStatus,
    ):
""",
)
replace_once(
    repository,
    """                opacity, size, margin, lock_layer
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
""",
    """                opacity, size, margin, lock_layer, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
""",
)
replace_once(
    repository,
    """            settings.margin,
            settings.lock,
        )
""",
    """            settings.margin,
            settings.lock,
            status,
        )
""",
)
replace_once(
    repository,
    '__all__ = ("CancelResult", "WatermarkRepository")\n',
    '__all__ = ("CancelResult", "RevisionStatus", "WatermarkRepository")\n',
)

service = Path("velvet_bot/domains/watermark/service.py")
replace_once(
    service,
    """        source_file_unique_id: str | None,
        source_path: str,
        workspace_id: int = 1,
""",
    """        source_file_unique_id: str | None,
        source_path: str,
        settings: WatermarkSettings | None = None,
        draft: bool = False,
        workspace_id: int = 1,
""",
)
replace_once(
    service,
    """            source_file_unique_id=source_file_unique_id,
            source_path=source_path,
            settings=WatermarkSettings(),
            workspace_id=workspace_id,
""",
    """            source_file_unique_id=source_file_unique_id,
            source_path=source_path,
            settings=settings or WatermarkSettings(),
            revision_status="draft" if draft else "pending",
            workspace_id=workspace_id,
""",
)
replace_once(
    service,
    """        margin_delta: float = 0.0,
        enabled: bool | None = None,
    ) -> WatermarkWorkItem:
""",
    """        margin_delta: float = 0.0,
        enabled: bool | None = None,
        draft: bool = False,
    ) -> WatermarkWorkItem:
""",
)
replace_once(
    service,
    """        return await self._repository.create_revision(job_id, settings=next_settings)

    async def undo(self, job_id: int, *, owner_user_id: int) -> WatermarkWorkItem:
        await self.get_current(job_id, owner_user_id=owner_user_id)
        return await self._repository.undo(job_id)

    async def approve(self, job_id: int, *, owner_user_id: int) -> WatermarkWorkItem:
""",
    """        return await self._repository.create_revision(
            job_id,
            settings=next_settings,
            revision_status="draft" if draft else "pending",
        )

    async def undo(
        self,
        job_id: int,
        *,
        owner_user_id: int,
        draft: bool = False,
    ) -> WatermarkWorkItem:
        await self.get_current(job_id, owner_user_id=owner_user_id)
        return await self._repository.undo(
            job_id,
            revision_status="draft" if draft else "pending",
        )

    async def generate(self, job_id: int, *, owner_user_id: int) -> WatermarkWorkItem:
        current = await self.get_current(job_id, owner_user_id=owner_user_id)
        status = current.revision.status
        if status not in {"draft", "error"}:
            if status in {"pending", "processing"}:
                raise ValueError("Генерация этой версии уже запущена.")
            raise ValueError("Сначала измените настройки, затем запустите новую генерацию.")
        return await self._repository.queue_revision(
            job_id=job_id,
            revision=current.revision.revision,
        )

    async def approve(self, job_id: int, *, owner_user_id: int) -> WatermarkWorkItem:
""",
)
