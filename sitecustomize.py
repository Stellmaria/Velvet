import unittest

_original_init = unittest.TextTestRunner.__init__


def _quiet_init(self, *args, **kwargs):
    kwargs["verbosity"] = 0
    _original_init(self, *args, **kwargs)


unittest.TextTestRunner.__init__ = _quiet_init
