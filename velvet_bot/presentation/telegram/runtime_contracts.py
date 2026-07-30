from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CompatibilityStage = Literal["pre-import", "post-import"]
CompatibilityDecision = Literal[
    "permanent-contract",
    "explicit-registration",
    "remove-after-consumer-migration",
]


@dataclass(frozen=True, slots=True)
class CompatibilityContract:
    name: str
    stage: CompatibilityStage
    decision: CompatibilityDecision
    owner_module: str
    consumers: tuple[str, ...]
    side_effect: str
    replacement: str


COMPATIBILITY_CONTRACTS = (
    CompatibilityContract(
        name="ai-quality-schema",
        stage="pre-import",
        decision="remove-after-consumer-migration",
        owner_module="velvet_bot.ai_quality_schema_compat",
        consumers=("velvet_bot.ai_quality.AIQualityRepository",),
        side_effect=(
            "Replaces AIQualityRepository row mapping and list/get queries at runtime "
            "because media_files has no file_name column."
        ),
        replacement=(
            "Move MIME-based display labels and the deployed media_files query shape "
            "directly into AIQualityRepository, then delete the installer."
        ),
    ),
    CompatibilityContract(
        name="set-consistency-dashboard",
        stage="pre-import",
        decision="remove-after-consumer-migration",
        owner_module="velvet_bot.quality_set_ai_dashboard",
        consumers=("velvet_bot.quality_ui.build_quality_dashboard",),
        side_effect="Wraps the quality dashboard factory to insert the media-set report button.",
        replacement="Render the media-set report button in the canonical quality dashboard factory.",
    ),
    CompatibilityContract(
        name="quality-calibration-dashboard",
        stage="pre-import",
        decision="remove-after-consumer-migration",
        owner_module="velvet_bot.quality_calibration_dashboard",
        consumers=("velvet_bot.quality_ui.build_quality_dashboard",),
        side_effect="Wraps the quality dashboard factory to insert the owner calibration button.",
        replacement="Render the calibration button in the canonical quality dashboard factory.",
    ),
    CompatibilityContract(
        name="media-set-actions",
        stage="pre-import",
        decision="remove-after-consumer-migration",
        owner_module="velvet_bot.media_set_duplicate_actions",
        consumers=("velvet_bot.media_sets.create_set_candidate_from_duplicate",),
        side_effect="Replaces a media_sets module function with a repository-backed implementation.",
        replacement=(
            "Route duplicate-to-set actions through the canonical media-set application/domain "
            "boundary without assigning functions at import time."
        ),
    ),
    CompatibilityContract(
        name="media-set-ai-discovery",
        stage="pre-import",
        decision="remove-after-consumer-migration",
        owner_module="velvet_bot.media_set_ai_discovery",
        consumers=("velvet_bot.media_sets.discover_media_set_candidates",),
        side_effect="Replaces the media-set discovery function with semantic AI discovery.",
        replacement=(
            "Expose semantic discovery as the canonical media-set service and inject/call it "
            "explicitly from its consumers."
        ),
    ),
    CompatibilityContract(
        name="media-set-ui",
        stage="pre-import",
        decision="remove-after-consumer-migration",
        owner_module="velvet_bot.media_set_ui_compat",
        consumers=(
            "velvet_bot.archive_ui.format_archive_caption",
            "velvet_bot.public_ui.format_public_archive_caption",
            "velvet_bot.public_preview_overrides.format_public_archive_caption",
        ),
        side_effect="Rebinds archive/public caption formatters so media-set titles are appended.",
        replacement=(
            "Move set-title rendering into canonical caption formatters and import those functions "
            "normally from preview delivery code."
        ),
    ),
    CompatibilityContract(
        name="owner-menu-navigation",
        stage="pre-import",
        decision="remove-after-consumer-migration",
        owner_module="velvet_bot.owner_menu_compat",
        consumers=(
            "character directory keyboard",
            "analytics dashboard keyboard",
            "backup center keyboard",
            "publication center keyboard",
            "system center keyboard",
            "quality dashboard keyboard",
        ),
        side_effect="Wraps several keyboard factories to append the owner-home button.",
        replacement=(
            "Use a shared owner-navigation keyboard helper directly in each canonical factory."
        ),
    ),
    CompatibilityContract(
        name="quality-calibration-report-ui",
        stage="post-import",
        decision="remove-after-consumer-migration",
        owner_module="velvet_bot.quality_calibration_ui",
        consumers=(
            "velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_ai._report_text",
        ),
        side_effect="Rebinds the already imported quality report renderer to append calibration data.",
        replacement="Render calibration data directly in the canonical quality report formatter.",
    ),
)


def contracts_for_stage(stage: CompatibilityStage) -> tuple[CompatibilityContract, ...]:
    return tuple(contract for contract in COMPATIBILITY_CONTRACTS if contract.stage == stage)


def contract_names(stage: CompatibilityStage | None = None) -> tuple[str, ...]:
    contracts = COMPATIBILITY_CONTRACTS if stage is None else contracts_for_stage(stage)
    return tuple(contract.name for contract in contracts)


__all__ = (
    "COMPATIBILITY_CONTRACTS",
    "CompatibilityContract",
    "CompatibilityDecision",
    "CompatibilityStage",
    "contract_names",
    "contracts_for_stage",
)
