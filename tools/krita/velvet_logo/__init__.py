from .silent_export import install_silent_export
from .velvet_logo import VelvetLogoExtension

from krita import Krita

install_silent_export(VelvetLogoExtension)
Krita.instance().addExtension(VelvetLogoExtension(Krita.instance()))
