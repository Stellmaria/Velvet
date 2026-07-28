from __future__ import annotations

import atexit
import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
_GIB = 1024 ** 3
_MIB = 1024 ** 2


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    total_bytes: int
    available_bytes: int
    total_pagefile_bytes: int
    available_pagefile_bytes: int


@dataclass(frozen=True, slots=True)
class DiskSnapshot:
    root: str
    total_bytes: int
    free_bytes: int


@dataclass(frozen=True, slots=True)
class GpuSnapshot:
    name: str
    memory_total_mib: int | None
    memory_free_mib: int | None
    driver_version: str
    cuda_version: str
    source: str


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    os: str
    architecture: str
    cpu: str
    logical_cpu_count: int | None
    physical_core_count: int | None
    memory: MemorySnapshot
    gpus: tuple[GpuSnapshot, ...]
    disks: tuple[DiskSnapshot, ...]
    ac_power: str
    battery_percent: int | None
    ollama_version: str
    ollama_models_path: str
    ollama_running_models: tuple[str, ...]


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _SystemPowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def _run_fixed(command: list[str], *, timeout: int = 20) -> str:
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode:
        return ""
    return (completed.stdout or "").strip()


def _powershell_json(script: str) -> Any:
    if os.name != "nt":
        return None
    executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if not executable:
        return None
    prefix = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new();$ProgressPreference='SilentlyContinue';"
    raw = _run_fixed(
        [executable, "-NoProfile", "-NonInteractive", "-Command", prefix + script],
        timeout=30,
    )
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def memory_snapshot() -> MemorySnapshot:
    if os.name == "nt":
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return MemorySnapshot(
                total_bytes=int(status.ullTotalPhys),
                available_bytes=int(status.ullAvailPhys),
                total_pagefile_bytes=int(status.ullTotalPageFile),
                available_pagefile_bytes=int(status.ullAvailPageFile),
            )
    total = 0
    available = 0
    try:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, raw = line.partition(":")
            if raw:
                values[key] = int(raw.strip().split()[0]) * 1024
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", values.get("MemFree", 0))
    except (OSError, ValueError):
        pass
    return MemorySnapshot(total, available, 0, 0)


def _cpu_details() -> tuple[str, int | None]:
    payload = _powershell_json(
        "Get-CimInstance Win32_Processor | Select-Object -First 1 Name,NumberOfCores | ConvertTo-Json -Compress"
    )
    if isinstance(payload, dict):
        name = str(payload.get("Name") or "").strip()
        try:
            cores = int(payload.get("NumberOfCores"))
        except (TypeError, ValueError):
            cores = None
        if name:
            return name, cores
    name = platform.processor().strip() or os.getenv("PROCESSOR_IDENTIFIER", "").strip()
    return name or "не определён", None


def _cuda_version_from_text(text: str) -> str:
    match = re.search(r"CUDA Version:\s*([0-9.]+)", text, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _nvidia_gpus() -> tuple[GpuSnapshot, ...]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return ()
    header = _run_fixed([executable], timeout=20)
    cuda_version = _cuda_version_from_text(header)
    raw = _run_fixed(
        [
            executable,
            "--query-gpu=name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ],
        timeout=20,
    )
    if not raw:
        return ()
    result: list[GpuSnapshot] = []
    for line in raw.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            total = int(float(parts[1]))
        except ValueError:
            total = None
        try:
            free = int(float(parts[2]))
        except ValueError:
            free = None
        result.append(
            GpuSnapshot(
                name=parts[0] or "NVIDIA GPU",
                memory_total_mib=total,
                memory_free_mib=free,
                driver_version=parts[3],
                cuda_version=cuda_version,
                source="nvidia-smi",
            )
        )
    return tuple(result)


def _fallback_gpus() -> tuple[GpuSnapshot, ...]:
    payload = _powershell_json(
        "@(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion) | ConvertTo-Json -Compress"
    )
    if payload is None:
        return ()
    rows = payload if isinstance(payload, list) else [payload]
    result: list[GpuSnapshot] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_memory = row.get("AdapterRAM")
        try:
            memory = int(raw_memory) // _MIB if raw_memory is not None else None
        except (TypeError, ValueError):
            memory = None
        result.append(
            GpuSnapshot(
                name=str(row.get("Name") or "GPU").strip(),
                memory_total_mib=memory,
                memory_free_mib=None,
                driver_version=str(row.get("DriverVersion") or "").strip(),
                cuda_version="",
                source="Win32_VideoController",
            )
        )
    return tuple(item for item in result if item.name)


def gpu_snapshots() -> tuple[GpuSnapshot, ...]:
    return _nvidia_gpus() or _fallback_gpus()


def disk_snapshots(roots: tuple[str, ...] = ("C:\\", "E:\\")) -> tuple[DiskSnapshot, ...]:
    result: list[DiskSnapshot] = []
    for root in roots:
        path = Path(root)
        if not path.exists():
            continue
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        result.append(DiskSnapshot(root=root, total_bytes=usage.total, free_bytes=usage.free))
    return tuple(result)


def power_status() -> tuple[str, int | None]:
    if os.name != "nt":
        return "не определено", None
    status = _SystemPowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return "не определено", None
    ac = {0: "батарея", 1: "сеть", 255: "неизвестно"}.get(status.ACLineStatus, "неизвестно")
    battery = None if status.BatteryLifePercent == 255 else int(status.BatteryLifePercent)
    return ac, battery


def _ollama_version() -> str:
    executable = shutil.which("ollama")
    if not executable:
        return "не найден в PATH"
    return _run_fixed([executable, "--version"], timeout=15) or "не определена"


def _ollama_running_models() -> tuple[str, ...]:
    request = urllib.request.Request(f"{_OLLAMA_BASE_URL}/api/ps", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=3.0) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return ()
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return ()
    names = [str(row.get("name")) for row in rows if isinstance(row, dict) and row.get("name")]
    return tuple(names)


def collect_hardware_profile() -> HardwareProfile:
    cpu, physical_cores = _cpu_details()
    ac_power, battery = power_status()
    return HardwareProfile(
        os=platform.platform(),
        architecture=platform.machine() or "не определена",
        cpu=cpu,
        logical_cpu_count=os.cpu_count(),
        physical_core_count=physical_cores,
        memory=memory_snapshot(),
        gpus=gpu_snapshots(),
        disks=disk_snapshots(),
        ac_power=ac_power,
        battery_percent=battery,
        ollama_version=_ollama_version(),
        ollama_models_path=os.getenv("OLLAMA_MODELS", "").strip(),
        ollama_running_models=_ollama_running_models(),
    )


def _gib(value: int) -> str:
    return f"{value / _GIB:.1f} ГБ"


def print_hardware_profile(profile: HardwareProfile | None = None) -> None:
    current = profile or collect_hardware_profile()
    print("\nПрофиль ПК для локальных моделей:")
    print(f"  ОС: {current.os}")
    print(f"  Архитектура: {current.architecture}")
    physical = current.physical_core_count if current.physical_core_count is not None else "не определено"
    logical = current.logical_cpu_count if current.logical_cpu_count is not None else "не определено"
    print(f"  CPU: {current.cpu}")
    print(f"  CPU cores: физических={physical}; логических={logical}")
    print(
        "  RAM: всего="
        f"{_gib(current.memory.total_bytes)}; доступно={_gib(current.memory.available_bytes)}; "
        f"pagefile всего={_gib(current.memory.total_pagefile_bytes)}; "
        f"доступно={_gib(current.memory.available_pagefile_bytes)}"
    )
    if current.gpus:
        for index, gpu in enumerate(current.gpus, start=1):
            total = f"{gpu.memory_total_mib} МиБ" if gpu.memory_total_mib is not None else "не определено"
            free = f"{gpu.memory_free_mib} МиБ" if gpu.memory_free_mib is not None else "не определено"
            print(
                f"  GPU {index}: {gpu.name}; VRAM всего={total}; свободно={free}; "
                f"driver={gpu.driver_version or 'не определён'}; "
                f"CUDA={gpu.cuda_version or 'не определена'}; source={gpu.source}"
            )
    else:
        print("  GPU: не определена")
    for disk in current.disks:
        print(f"  Диск {disk.root}: всего={_gib(disk.total_bytes)}; свободно={_gib(disk.free_bytes)}")
    battery = f"; батарея={current.battery_percent}%" if current.battery_percent is not None else ""
    print(f"  Питание: {current.ac_power}{battery}")
    print(f"  Ollama: {current.ollama_version}")
    print(f"  OLLAMA_MODELS процесса: {current.ollama_models_path or '<не задано>'}")
    running = ", ".join(current.ollama_running_models) if current.ollama_running_models else "нет"
    print(f"  Модели сейчас загружены в память: {running}")
    print("PROFILE_JSON=" + json.dumps(asdict(current), ensure_ascii=False, separators=(",", ":")))


def _is_ollama_status_main() -> bool:
    main_module = sys.modules.get("__main__")
    spec = getattr(main_module, "__spec__", None)
    name = getattr(spec, "name", "")
    return name == "velvet_supervisor.ollama_recovery" and sys.argv[1:] == ["status"]


def install_ollama_status_hardware_hook(
    register: Callable[[Callable[[], None]], Any] = atexit.register,
) -> None:
    def emit() -> None:
        if _is_ollama_status_main():
            print_hardware_profile()

    register(emit)


__all__ = (
    "DiskSnapshot",
    "GpuSnapshot",
    "HardwareProfile",
    "MemorySnapshot",
    "collect_hardware_profile",
    "disk_snapshots",
    "gpu_snapshots",
    "install_ollama_status_hardware_hook",
    "memory_snapshot",
    "print_hardware_profile",
)
