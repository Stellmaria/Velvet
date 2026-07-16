from __future__ import annotations

import velvet_bot.discussion_insights as discussion_insights_module
import velvet_bot.multi_story_support as multi_story_support
import velvet_bot.publication_workflow as publication_workflow_module
from velvet_bot.discussion_summary_runtime import get_discussion_summary
from velvet_bot.multi_story_queries import list_assigned_character_stories
from velvet_bot.publication_drafts import (
    cancel_publication,
    capture_publication_inbox,
    create_draft_from_message,
    get_publication_draft,
    list_publication_drafts,
    retry_publication,
    schedule_publication,
    set_publication_spoiler,
    update_publication_text,
)
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

    publication_workflow_module.capture_publication_inbox = capture_publication_inbox
    publication_workflow_module.create_draft_from_message = create_draft_from_message
    publication_workflow_module.get_publication_draft = get_publication_draft
    publication_workflow_module.list_publication_drafts = list_publication_drafts
    publication_workflow_module.validate_publication_draft = validate_publication_draft
    publication_workflow_module.set_publication_spoiler = set_publication_spoiler
    publication_workflow_module.update_publication_text = update_publication_text
    publication_workflow_module.schedule_publication = schedule_publication
    publication_workflow_module.cancel_publication = cancel_publication
    publication_workflow_module.retry_publication = retry_publication

    install_safe_analytics_edit()
    _INSTALLED = True


__all__ = ("install_legacy_compatibility",)
