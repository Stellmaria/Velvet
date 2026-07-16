from __future__ import annotations

from velvet_bot.app.discussion_post_insights import (
    build_discussion_post_insight_service,
)
from velvet_bot.database import Database
from velvet_bot.domains.discussions.insight_models import (
    DiscussedPost,
    DiscussedPostPage,
)


async def list_discussed_posts(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
    page: int,
    page_size: int = 6,
) -> DiscussedPostPage:
    return await build_discussion_post_insight_service(database).list_posts(
        discussion_chat_id=discussion_chat_id,
        parent_channel_id=parent_channel_id,
        period=period,
        page=page,
        page_size=page_size,
    )


async def get_discussed_post(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    post_id: int,
    *,
    period: str,
) -> DiscussedPost | None:
    return await build_discussion_post_insight_service(database).get_post(
        discussion_chat_id=discussion_chat_id,
        parent_channel_id=parent_channel_id,
        post_id=post_id,
        period=period,
    )


__all__ = (
    "DiscussedPost",
    "DiscussedPostPage",
    "get_discussed_post",
    "list_discussed_posts",
)
