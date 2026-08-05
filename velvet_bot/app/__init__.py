from velvet_bot.app.gpt_image_2_bootstrap import install_gpt_image_2_bootstrap

install_gpt_image_2_bootstrap()

from velvet_bot.app.composition import (
    ApplicationComposition,
    CompositionStage,
    build_application_composition,
    run_application,
)

__all__ = (
    "ApplicationComposition",
    "CompositionStage",
    "build_application_composition",
    "run_application",
)
