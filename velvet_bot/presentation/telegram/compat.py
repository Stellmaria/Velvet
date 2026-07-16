from __future__ import annotations

import velvet_bot.discussion_insights as discussion_insights_module
import velvet_bot.multi_story_support as multi_story_support
import velvet_bot.publication_workflow as publication_workflow_module
from velvet_bot.discussion_summary_runtime import get_discussion_summary
from velvet_bot.multi_story_queries import list_assigned_character_stories
from velvet_bot.publication_validation import validate_publication_draft
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
    publication_workflow_module.validate_publication_draft = validate_publication_draft
    install_safe_analytics_edit()
    _INSTALLED = True


__all__ = ("install_legacy_compatibility",)
