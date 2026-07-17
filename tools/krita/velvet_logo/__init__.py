from .velvet_logo import VelvetLogoExtension

from krita import Krita

Krita.instance().addExtension(VelvetLogoExtension(Krita.instance()))
