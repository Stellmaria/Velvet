from .config import SupervisorSettings
from .hardware_profile import install_ollama_status_hardware_hook
from .runtime import VelvetSupervisor

install_ollama_status_hardware_hook()

__all__ = ("SupervisorSettings", "VelvetSupervisor")
