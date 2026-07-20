from __future__ import annotations

PUBLIC_IMAGE_MAX_BYTES = 20 * 1024 * 1024


def public_media_visibility_sql(
    *,
    link_alias: str = "cm",
    file_alias: str = "mf",
    include_adult_restricted: bool = False,
    include_oversized_images: bool = False,
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
    return f"""
        {link_alias}.is_public = TRUE
        AND ({adult_predicate})
        AND ({size_predicate})
    """.strip()


__all__ = ("PUBLIC_IMAGE_MAX_BYTES", "public_media_visibility_sql")
