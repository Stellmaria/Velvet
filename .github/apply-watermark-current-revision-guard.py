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
    """                    UPDATE watermark_revisions
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
""",
    """                    UPDATE watermark_revisions AS revision
                    SET status = 'pending',
                        request_path = NULL,
                        output_path = NULL,
                        response_path = NULL,
                        telegram_preview_file_id = NULL,
                        error = NULL,
                        completed_at = NULL
                    FROM watermark_jobs AS job
                    WHERE revision.job_id = $1
                      AND revision.revision = $2
                      AND revision.status IN ('draft', 'error')
                      AND job.id = revision.job_id
                      AND job.current_revision = revision.revision
""",
)

controller = Path(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
    "workspace_product_experience.py"
)
replace_once(
    controller,
    "from velvet_bot.domains.watermark.service import WatermarkService\n",
    "",
)

integration = Path("tests/test_watermark_repository_integration.py")
replace_once(
    integration,
    """    async def test_approved_job_is_idempotently_protected_from_cancel(self) -> None:
""",
    """    async def test_stale_draft_revision_cannot_be_queued(self) -> None:
        first = await self._create_job(
            source_message_id=35,
            revision_status="draft",
        )
        current = await self.repository.create_revision(
            first.job.id,
            settings=WatermarkSettings(position="top_right"),
            revision_status="draft",
        )
        self.assertEqual(2, current.revision.revision)

        with self.assertRaisesRegex(ValueError, "Черновик уже изменился"):
            await self.repository.queue_revision(
                job_id=first.job.id,
                revision=first.revision.revision,
            )
        self.assertIsNone(await self.repository.claim_pending())

    async def test_approved_job_is_idempotently_protected_from_cancel(self) -> None:
""",
)
