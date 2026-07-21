from __future__ import annotations

from importlib import import_module
from typing import Final, cast

from velvet_bot.domains.references.models import (
    AddReferenceResult,
    CharacterReference,
    DeleteReferenceResult,
    ReferenceMediaPayload,
    ReferencePage,
)

_RUNTIME_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "ReferenceRepository": (
        "velvet_bot.domains.references.repository",
        "ReferenceRepository",
    ),
    "ReferenceService": (
        "velvet_bot.domains.references.service",
        "ReferenceService",
    ),
}

__all__ = (
    "AddReferenceResult",
    "CharacterReference",
    "DeleteReferenceResult",
    "ReferenceMediaPayload",
    "ReferencePage",
    "ReferenceRepository",
    "ReferenceService",
)


def __getattr__(name: str) -> object:
    target = _RUNTIME_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = target
    value = cast(object, getattr(import_module(module_name), attribute_name))
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
