from __future__ import annotations

from velvet_bot.ai_quality_schema_compat import install_ai_quality_schema_compatibility
from velvet_bot.media_set_ui_compat import install_media_set_ui
from velvet_bot.owner_menu_compat import install_owner_menu_navigation
from velvet_bot.quality_calibration_dashboard import install_quality_calibration_dashboard
from velvet_bot.quality_calibration_ui import install_quality_calibration_report_ui
from velvet_bot.quality_set_ai_dashboard import install_set_consistency_dashboard

# Compatibility remains explicit and measurable while legacy root modules are
# migrated into their canonical domains. Stage ordering is part of the contract:
# pre-import adapters must run before handler modules bind imported functions,
# while post-import adapters intentionally update already imported UI bindings.
PRE_IMPORT_COMPONENTS = (
    "ai-quality-schema",
    "set-consistency-dashboard",
    "quality-calibration-dashboard",
    "media-set-actions",
    "media-set-ai-discovery",
    "media-set-ui",
    "owner-menu-navigation",
)
POST_IMPORT_COMPONENTS = ("quality-calibration-report-ui",)
ACTIVE_COMPATIBILITY_COMPONENTS = PRE_IMPORT_COMPONENTS + POST_IMPORT_COMPONENTS


def install_pre_router_compatibility() -> None:
    install_ai_quality_schema_compatibility()
    install_set_consistency_dashboard()
    install_quality_calibration_dashboard()

    # These modules still expose import-time compatibility bindings. Keep them in
    # one named boundary until their behavior is moved into canonical services.
    import velvet_bot.media_set_duplicate_actions  # noqa: F401
    import velvet_bot.media_set_ai_discovery  # noqa: F401

    install_media_set_ui()
    install_owner_menu_navigation()


def install_post_router_compatibility() -> None:
    install_quality_calibration_report_ui()


def install_legacy_compatibility() -> None:
    """Historical no-op retained only for external imports.

    Runtime compatibility is installed explicitly by the Telegram composition root
    through the staged functions above.
    """


__all__ = (
    "ACTIVE_COMPATIBILITY_COMPONENTS",
    "POST_IMPORT_COMPONENTS",
    "PRE_IMPORT_COMPONENTS",
    "install_legacy_compatibility",
    "install_post_router_compatibility",
    "install_pre_router_compatibility",
)
