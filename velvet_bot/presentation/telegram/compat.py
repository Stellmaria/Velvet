from __future__ import annotations

import velvet_bot.discussion_insights as discussion_insights_module
import velvet_bot.multi_story_support as multi_story_support
from velvet_bot.discussion_post_insights import (
    get_discussed_post,
    list_discussed_posts,
)
from velvet_bot.discussion_rankings import (
    list_active_participants,
    list_discussed_characters,
    list_discussed_stories,
    list_discussed_universes,
    list_most_replied_participants,
    list_reaction_leaders,
)
from velvet_bot.discussion_summary_runtime import get_discussion_summary
from velvet_bot.multi_story_queries import list_assigned_character_stories
from velvet_bot.runtime_log_hotfixes import install_runtime_log_hotfixes
from velvet_bot.safe_analytics_edit import install_safe_analytics_edit

_INSTALLED = False


def install_legacy_compatibility() -> None:
    """Install temporary bridges kept until their domains are fully migrated."""
    global _INSTALLED
    if _INSTALLED:
        return

    install_runtime_log_hotfixes()
    multi_story_support.list_assigned_character_stories = list_assigned_character_stories
    multi_story_support.install_multi_story_support()

    discussion_insights_module.get_discussion_summary = get_discussion_summary
    discussion_insights_module.list_discussed_posts = list_discussed_posts
    discussion_insights_module.get_discussed_post = get_discussed_post
    discussion_insights_module.list_active_participants = list_active_participants
    discussion_insights_module.list_most_replied_participants = (
        list_most_replied_participants
    )
    discussion_insights_module.list_reaction_leaders = list_reaction_leaders
    discussion_insights_module.list_discussed_characters = list_discussed_characters
    discussion_insights_module.list_discussed_universes = list_discussed_universes
    discussion_insights_module.list_discussed_stories = list_discussed_stories

    install_safe_analytics_edit()
    _INSTALLED = True


__all__ = ("install_legacy_compatibility",)
