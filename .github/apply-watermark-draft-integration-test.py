from pathlib import Path

path = Path("tests/test_watermark_repository_integration.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one integration block, found {count}: {old[:120]!r}")
    text = text.replace(old, new, 1)


replace_once(
    """    async def _create_job(self, *, source_message_id: int = 30) -> WatermarkWorkItem:
        return await self.repository.create_job(
""",
    """    async def _create_job(
        self,
        *,
        source_message_id: int = 30,
        revision_status: str = "pending",
    ) -> WatermarkWorkItem:
        return await self.repository.create_job(
""",
)
replace_once(
    """            source_path=f"/bridge/sources/source-{source_message_id}.png",
            settings=WatermarkSettings(),
        )
""",
    """            source_path=f"/bridge/sources/source-{source_message_id}.png",
            settings=WatermarkSettings(),
            revision_status=revision_status,  # type: ignore[arg-type]
        )
""",
)
replace_once(
    """    async def test_approved_job_is_idempotently_protected_from_cancel(self) -> None:
""",
    """    async def test_draft_revision_is_not_claimed_until_explicitly_queued(self) -> None:
        draft = await self._create_job(
            source_message_id=34,
            revision_status="draft",
        )
        self.assertEqual("draft", draft.revision.status)
        self.assertIsNone(await self.repository.claim_pending())

        queued = await self.repository.queue_revision(
            job_id=draft.job.id,
            revision=draft.revision.revision,
        )
        self.assertEqual("pending", queued.revision.status)

        claimed = await self.repository.claim_pending()
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(draft.job.id, claimed.job.id)
        self.assertEqual("processing", claimed.revision.status)

    async def test_approved_job_is_idempotently_protected_from_cancel(self) -> None:
""",
)

path.write_text(text, encoding="utf-8")
