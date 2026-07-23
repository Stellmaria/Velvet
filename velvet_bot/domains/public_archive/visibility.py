from __future__ import annotations

PUBLIC_IMAGE_MAX_BYTES = 20 * 1024 * 1024
ACTIVE_REWORK_STATUSES = ("needs_fix", "checking", "ready_for_review")


def public_media_visibility_sql(
    *,
    link_alias: str = "cm",
    file_alias: str = "mf",
    include_adult_restricted: bool = False,
    include_oversized_images: bool = False,
    include_active_rework: bool = False,
) -> str:
    """Return the SQL predicate for media allowed to the current viewer."""
    allowed_aliases = {
        "cm",
        "mf",
        "media",
        "file",
        "character_media",
        "media_file",
    }
    if link_alias not in allowed_aliases or file_alias not in allowed_aliases:
        raise ValueError("Unsupported SQL alias for public media visibility.")

    adult_predicate = (
        "TRUE"
        if include_adult_restricted
        else f"{link_alias}.requires_adult_channel = FALSE"
    )
    size_predicate = (
        "TRUE"
        if include_oversized_images
        else f"""
        NOT (
            (
                {file_alias}.media_type = 'photo'
                OR COALESCE({file_alias}.mime_type, '') LIKE 'image/%'
            )
            AND COALESCE({file_alias}.file_size, 0) > {PUBLIC_IMAGE_MAX_BYTES}
        )
        """.strip()
    )
    rework_predicate = (
        "TRUE"
        if include_active_rework
        else f"""
        NOT EXISTS (
            SELECT 1
            FROM media_rework_items AS active_rework
            WHERE active_rework.media_id = {link_alias}.media_id
              AND active_rework.workspace_id = (
                    SELECT rework_character.workspace_id
                    FROM characters AS rework_character
                    WHERE rework_character.id = {link_alias}.character_id
                  )
              AND active_rework.status IN (
                    'needs_fix',
                    'checking',
                    'ready_for_review'
                  )
        )
        """.strip()
    )
    return f"""
        {link_alias}.is_public = TRUE
        AND ({adult_predicate})
        AND ({size_predicate})
        AND ({rework_predicate})
    """.strip()


__all__ = (
    "ACTIVE_REWORK_STATUSES",
    "PUBLIC_IMAGE_MAX_BYTES",
    "public_media_visibility_sql",
)
