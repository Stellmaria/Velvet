from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import SupervisorSettings as SupervisorSettings
    from .runtime import VelvetSupervisor as VelvetSupervisor

__all__ = ("SupervisorSettings", "VelvetSupervisor")


def __getattr__(name: str) -> Any:
    """Keep lightweight submodules importable without legacy runtime dependencies."""

    if name == "SupervisorSettings":
        from .config import SupervisorSettings

        return SupervisorSettings
    if name == "VelvetSupervisor":
        from .hardware_profile import install_ollama_status_hardware_hook
        from .runtime import VelvetSupervisor

        install_ollama_status_hardware_hook()
        return VelvetSupervisor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
