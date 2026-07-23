from .silent_export import install_silent_export
from .velvet_logo import VelvetLogoExtension

from krita import Krita


try:
    from .svg_logo_patch import install_svg_logo_patch

    install_svg_logo_patch(VelvetLogoExtension)
except Exception as error:
    # A watermark compatibility patch must never prevent Krita from starting.
    # The base plugin remains available for the built-in logo and PNG assets.
    print(f"Velvet Anatomy: SVG compatibility patch disabled: {error}")

install_silent_export(VelvetLogoExtension)
Krita.instance().addExtension(VelvetLogoExtension(Krita.instance()))
