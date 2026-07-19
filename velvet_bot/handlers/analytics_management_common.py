from __future__ import annotations

import importlib as _importlib
import sys as _sys

P3_COMPAT_MODULE_ALIAS = "velvet_bot.presentation.telegram.routers.analytics_controllers.management_common"
_target = _importlib.import_module(P3_COMPAT_MODULE_ALIAS)
_sys.modules[__name__] = _target
