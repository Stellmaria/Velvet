from __future__ import annotations

from velvet_bot.database import Database


async def recover_interrupted_media_scans(database: Database) -> int:
    """Return interrupted fingerprint jobs to the pending queue after restart."""
    async with database._require_pool().acquire() as connection:
        result = await connection.execute(
            """
            UPDATE media_files
            SET visual_scan_status = 'pending',
                visual_scan_error = NULL
            WHERE visual_scan_status = 'processing'
            """
        )
    return int(result.split()[-1])
