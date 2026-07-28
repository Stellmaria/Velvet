from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from velvet_supervisor.hardware_profile import (
    DiskSnapshot,
    GpuSnapshot,
    HardwareProfile,
    MemorySnapshot,
    _nvidia_gpus,
    install_ollama_status_hardware_hook,
    print_hardware_profile,
)


class HardwareProfileNvidiaTests(unittest.TestCase):
    def test_nvidia_smi_is_parsed_without_shell(self) -> None:
        outputs = iter(
            [
                "NVIDIA-SMI 580.00 Driver Version: 580.00 CUDA Version: 13.0",
                "NVIDIA GeForce RTX 3050 Ti Laptop GPU, 4096, 3072, 580.00",
            ]
        )
        with patch("velvet_supervisor.hardware_profile.shutil.which", return_value="nvidia-smi.exe"):
            with patch(
                "velvet_supervisor.hardware_profile._run_fixed",
                side_effect=lambda *args, **kwargs: next(outputs),
            ) as run:
                gpus = _nvidia_gpus()

        self.assertEqual(1, len(gpus))
        self.assertEqual("NVIDIA GeForce RTX 3050 Ti Laptop GPU", gpus[0].name)
        self.assertEqual(4096, gpus[0].memory_total_mib)
        self.assertEqual(3072, gpus[0].memory_free_mib)
        self.assertEqual("13.0", gpus[0].cuda_version)
        self.assertEqual(["nvidia-smi.exe"], run.call_args_list[0].args[0])


class HardwareProfileOutputTests(unittest.TestCase):
    def test_output_contains_human_summary_and_machine_json(self) -> None:
        profile = HardwareProfile(
            os="Windows-11",
            architecture="AMD64",
            cpu="Example CPU",
            logical_cpu_count=16,
            physical_core_count=8,
            memory=MemorySnapshot(
                total_bytes=16 * 1024**3,
                available_bytes=8 * 1024**3,
                total_pagefile_bytes=24 * 1024**3,
                available_pagefile_bytes=12 * 1024**3,
            ),
            gpus=(
                GpuSnapshot(
                    name="RTX Test",
                    memory_total_mib=4096,
                    memory_free_mib=3000,
                    driver_version="1.2.3",
                    cuda_version="13.0",
                    source="nvidia-smi",
                ),
            ),
            disks=(
                DiskSnapshot(
                    root="E:\\",
                    total_bytes=100 * 1024**3,
                    free_bytes=60 * 1024**3,
                ),
            ),
            ac_power="сеть",
            battery_percent=80,
            ollama_version="ollama version 0.32.3",
            ollama_models_path=r"E:\OllamaModels",
            ollama_running_models=("qwen3-vl:4b",),
        )
        stream = io.StringIO()
        with redirect_stdout(stream):
            print_hardware_profile(profile)
        output = stream.getvalue()

        self.assertIn("Профиль ПК для локальных моделей", output)
        self.assertIn("RTX Test", output)
        self.assertIn("VRAM всего=4096 МиБ", output)
        self.assertIn(r"E:\OllamaModels", output)
        json_line = next(
            line for line in output.splitlines() if line.startswith("PROFILE_JSON=")
        )
        payload = json.loads(json_line.removeprefix("PROFILE_JSON="))
        self.assertEqual("Example CPU", payload["cpu"])
        self.assertEqual(4096, payload["gpus"][0]["memory_total_mib"])


class HardwareProfileHookTests(unittest.TestCase):
    def test_hook_emits_only_for_ollama_status_module(self) -> None:
        callbacks = []
        install_ollama_status_hardware_hook(callbacks.append)
        self.assertEqual(1, len(callbacks))
        callback = callbacks[0]

        fake_main = SimpleNamespace(
            __spec__=SimpleNamespace(name="velvet_supervisor.ollama_recovery")
        )
        with patch.dict(sys.modules, {"__main__": fake_main}):
            with patch.object(sys, "argv", ["ollama_recovery.py", "status"]):
                with patch(
                    "velvet_supervisor.hardware_profile.print_hardware_profile"
                ) as printer:
                    callback()
        printer.assert_called_once_with()

    def test_hook_is_silent_for_other_commands(self) -> None:
        callbacks = []
        install_ollama_status_hardware_hook(callbacks.append)
        fake_main = SimpleNamespace(
            __spec__=SimpleNamespace(name="velvet_supervisor.ollama_recovery")
        )
        with patch.dict(sys.modules, {"__main__": fake_main}):
            with patch.object(sys, "argv", ["ollama_recovery.py", "repair"]):
                with patch(
                    "velvet_supervisor.hardware_profile.print_hardware_profile"
                ) as printer:
                    callbacks[0]()
        printer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
