from .silent_export import install_silent_export
from .svg_logo_patch import install_svg_logo_patch
from .velvet_logo import VelvetLogoExtension

from krita import Krita

install_svg_logo_patch(VelvetLogoExtension)
install_silent_export(VelvetLogoExtension)
Krita.instance().addExtension(VelvetLogoExtension(Krita.instance()))
