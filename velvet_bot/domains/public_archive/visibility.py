from __future__ import annotations

PUBLIC_IMAGE_MAX_BYTES = 20 * 1024 * 1024


def public_media_visibility_sql(
    *,
    link_alias: str = "cm",
    file_alias: str = "mf",
) -> str:
    """Return the SQL predicate for media allowed in the public archive."""
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
    return f"""
        {link_alias}.is_public = TRUE
        AND {link_alias}.requires_adult_channel = FALSE
        AND NOT (
            (
                {file_alias}.media_type = 'photo'
                OR COALESCE({file_alias}.mime_type, '') LIKE 'image/%'
            )
            AND COALESCE({file_alias}.file_size, 0) > {PUBLIC_IMAGE_MAX_BYTES}
        )
    """.strip()


__all__ = ("PUBLIC_IMAGE_MAX_BYTES", "public_media_visibility_sql")
