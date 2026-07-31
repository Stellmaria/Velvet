from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from scripts import inventory_package_architecture as inventory

ROOT = Path(__file__).resolve().parents[1]
LABEL = "hotfix-remove-qwen-flux-generation"


def _run(*args: str) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def _replace_once(path: str, old: str, new: str) -> None:
    file = ROOT / path
    source = file.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement, found {count}")
    file.write_text(source.replace(old, new), encoding="utf-8")


def _patch_root_keyboard() -> None:
    _replace_once(
        "velvet_bot/presentation/telegram/routers/workspace_auf.py",
        '''                    InlineKeyboardButton(
                        text="Создать",
                        callback_data=_callback(
                            "create",
                            workspace_id=workspace_id,
                        ),
                    ),
                    InlineKeyboardButton(
                        text="Оживить",
                        callback_data=_callback(
                            "animate",
                            workspace_id=workspace_id,
                        ),
                    ),''',
        '''                    InlineKeyboardButton(
                        text="Фото",
                        callback_data=_callback(
                            "create",
                            workspace_id=workspace_id,
                        ),
                    ),
                    InlineKeyboardButton(
                        text="Видео",
                        callback_data=_callback(
                            "animate",
                            workspace_id=workspace_id,
                        ),
                    ),''',
    )


def _patch_active_models() -> None:
    old = '''    KieModelAlias.SEEDREAM_5_PRO,
    KieModelAlias.QWEN2_IMAGE_EDIT,
    KieModelAlias.WAN_27_IMAGE,
    KieModelAlias.FLUX_2_PRO_IMAGE,'''
    new = '''    KieModelAlias.SEEDREAM_5_PRO,
    KieModelAlias.WAN_27_IMAGE,'''
    for path in (
        "velvet_bot/app/auf_photo_model_modes.py",
        "velvet_bot/presentation/telegram/routers/workspace_auf_photo.py",
    ):
        _replace_once(path, old, new)

    _replace_once(
        "velvet_bot/presentation/telegram/routers/workspace_auf_photo.py",
        '            "Лимиты: Banana — 5, Qwen — 3, FLUX — 8, Wan — 9, Seedream — 10."\n',
        '            "Лимиты референсов: Banana — 5, Wan — 9, Seedream — 10."\n',
    )


def _patch_existing_tests() -> None:
    path = ROOT / "tests/test_auf_photo_model_modes.py"
    source = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"    def test_request_preserves_qwen_photo_and_two_prompt_parts\(self\) -> None:\n.*?(?=    def test_flux_photo_payload_keeps_uploaded_reference)",
        re.DOTALL,
    )
    replacement = '''    def test_retired_qwen_and_flux_are_rejected_by_active_request_builder(self) -> None:
        for model in (
            KieModelAlias.QWEN2_IMAGE_EDIT,
            KieModelAlias.FLUX_2_PRO_IMAGE,
        ):
            with self.subTest(model=model):
                with self.assertRaisesRegex(ValueError, "Сначала выберите модель"):
                    modes._request(
                        {
                            "auf_model": model.value,
                            "auf_input_mode": KieInputMode.PHOTO_TEXT.value,
                            "auf_prompt_parts": ["first part", "second part"],
                            "auf_references": [_reference().to_payload()],
                            "auf_resolution": "2K",
                            "auf_aspect_ratio": "9:16",
                        }
                    )

'''
    source, count = pattern.subn(replacement, source)
    if count != 1:
        raise RuntimeError(f"request test replacement count={count}")

    old = '''        flux = modes._request(
            {
                "auf_model": KieModelAlias.FLUX_2_PRO_IMAGE.value,
                "auf_input_mode": KieInputMode.TEXT.value,
                "auf_prompt_parts": ["portrait"],
                "auf_resolution": "2K",
                "auf_aspect_ratio": "9:16",
                "auf_output_format": "jpeg",
            }
        )
        self.assertEqual("png", flux.output_format)
'''
    new = '''        wan = modes._request(
            {
                "auf_model": KieModelAlias.WAN_27_IMAGE.value,
                "auf_input_mode": KieInputMode.TEXT.value,
                "auf_prompt_parts": ["portrait"],
                "auf_resolution": "1K",
                "auf_aspect_ratio": "9:16",
                "auf_output_format": "jpeg",
            }
        )
        self.assertEqual("png", wan.output_format)
'''
    if source.count(old) != 1:
        raise RuntimeError("seedream non-seedream request block not found")
    path.write_text(source.replace(old, new), encoding="utf-8")


def _write_surface_regression() -> None:
    (ROOT / "tests/test_auf_generation_surface_policy.py").write_text(
        '''from __future__ import annotations

import unittest

from velvet_bot.app import auf_photo_model_modes
from velvet_bot.domains.media_generation import KieModelAlias
from velvet_bot.presentation.telegram.routers import (
    workspace_auf,
    workspace_auf_photo,
    workspace_auf_root,
)


_RETIRED_MODELS = frozenset(
    {
        KieModelAlias.QWEN2_IMAGE_EDIT,
        KieModelAlias.FLUX_2_PRO_IMAGE,
    }
)


class AufGenerationSurfacePolicyTests(unittest.TestCase):
    def test_qwen_and_flux_are_absent_from_active_photo_catalogs(self) -> None:
        self.assertTrue(
            _RETIRED_MODELS.isdisjoint(workspace_auf_photo._PHOTO_MODELS)
        )
        self.assertTrue(
            _RETIRED_MODELS.isdisjoint(auf_photo_model_modes._PHOTO_MODELS)
        )
        for model in _RETIRED_MODELS:
            with self.subTest(model=model):
                self.assertIsNone(workspace_auf_photo._model(model.value))
                self.assertIsNone(auf_photo_model_modes._model(model.value))

    def test_every_root_keyboard_uses_photo_and_video_labels(self) -> None:
        for builder in (
            workspace_auf.build_auf_root_keyboard,
            workspace_auf_photo.build_auf_root_keyboard,
            workspace_auf_root.build_auf_root_keyboard,
        ):
            with self.subTest(builder=builder.__module__):
                keyboard = builder(workspace_id=9, enabled=True)
                labels = [
                    button.text
                    for row in keyboard.inline_keyboard
                    for button in row
                ]
                self.assertEqual(
                    ["Фото", "Видео", "↩️ Моё пространство"],
                    labels,
                )
                self.assertIn(
                    "auf:create:",
                    keyboard.inline_keyboard[0][0].callback_data or "",
                )
                self.assertIn(
                    "auf:animate:",
                    keyboard.inline_keyboard[0][1].callback_data or "",
                )


if __name__ == "__main__":
    unittest.main()
''',
        encoding="utf-8",
    )


def _write_worklog() -> None:
    (ROOT / "docs/worklog/2026-08-01-remove-qwen-flux-generation.md").write_text(
        '''# 2026-08-01 — Удаление Qwen и FLUX из генерации Ауф

- Дата: `2026-08-01`
- ID: `remove-qwen-flux-generation`
- Линия/фаза: `production hotfix`
- Статус: `завершено`
- Ветка: `hotfix/remove-qwen-flux-generation-root-buttons`
- Базовый commit: `1d763e9217204841a0b7ed0437434737f4cbae27`

## Перед началом

### Цель

Полностью убрать Qwen Image и FLUX из доступной пользователю генерации Ауф и восстановить главные кнопки `Фото` и `Видео` вместо устаревших подписей `Создать` и `Оживить`.

### Исходный контекст

Qwen2 Image Edit и FLUX 2 Pro снова входили в оба активных фото-каталога. Канонический root builder по-прежнему создавал старые подписи, а отдельный wrapper заменял их только у части импортов. Поэтому экраны после завершения или отмены могли вернуть старую клавиатуру.

Ошибки `Could not persist provider submission` и `Could not normalize provider success` относятся к durable media delivery. Исправления durable repository и at-most-once recovery уже присутствуют в актуальном `main` после PR #527 и #531. Этот hotfix не удаляет исторические aliases и provider payload contracts, чтобы не сломать восстановление уже оплаченных задач.

### Планируемый объём

- исключить `QWEN2_IMAGE_EDIT` и `FLUX_2_PRO_IMAGE` из обеих активных фото-поверхностей;
- отклонять старые или вручную собранные callback-состояния через существующую проверку активного каталога;
- исправить канонический root builder на `Фото` и `Видео`;
- сохранить callback actions `create` и `animate`;
- оставить legacy aliases и низкоуровневые provider contracts только для восстановления исторических задач;
- добавить регрессионные тесты.

### Критерии готовности

- Qwen Image и FLUX отсутствуют в выборе моделей;
- новые задачи с этими aliases нельзя собрать через Telegram flow;
- все root keyboard consumers показывают `Фото`, `Видео`, `Моё пространство`;
- callback actions не изменены;
- существующие durable tasks остаются читаемыми для recovery без повторной генерации.

### Риски и ограничения

Физическое удаление enum aliases или provider mappings сломало бы десериализацию исторических очередей и могло лишить пользователя уже оплаченного результата. Поэтому генераторы удалены из активного каталога и новых пользовательских запросов, а compatibility contracts сохранены для recovery.

## После завершения

### Фактически сделано

- Qwen2 Image Edit и FLUX 2 Pro удалены из обоих активных `_PHOTO_MODELS`;
- `_model()` теперь отвергает их в новом и сохранённом пользовательском flow;
- канонический `build_auf_root_keyboard()` сразу создаёт кнопки `Фото` и `Видео`, поэтому старые bound imports больше не возвращают прежние подписи;
- fallback-текст выбора моделей очищен от Qwen и FLUX;
- низкоуровневые payload и provider mappings сохранены только ради совместимости исторических задач;
- тесты закрепляют отсутствие генераторов в UI и единый callback contract.

### Миграции и совместимость

Миграции базы не требуются. `KieModelAlias` и provider payload contracts сохранены для reconciliation и durable delivery. Новые пользовательские задачи через отключённые модели создать нельзя.

### Проверки

Финализация выполняет architecture inventory check, `compileall` и целевые регрессионные тесты. После deployment нужен production smoke: открыть Ауф, проверить корневой экран, список фото-моделей и одну генерацию на оставшейся модели.

### PR и commit

PR: `#532 Убрать Qwen и FLUX из генерации и вернуть кнопки Фото/Видео`.

### Незавершённое

После deployment требуется проверить, что новые occurrence ошибок #465 и #466 не появляются. Если production всё ещё работает на старом commit, процесс необходимо обновить до нового `main`.

### Следующий шаг

После зелёного CI слить PR #532, обновить production и выполнить smoke без повторного списания для старой durable задачи.
''',
        encoding="utf-8",
    )


def _refresh_architecture_inventory() -> None:
    data = inventory.build_inventory(label=LABEL)
    exemptions_path = inventory.EXEMPTIONS_JSON
    exemptions = json.loads(exemptions_path.read_text(encoding="utf-8"))
    registered = {
        str(row["id"]): row for row in exemptions.get("exceptions", [])
    }
    consumers = inventory._reverse_consumers(list(data["modules"]))
    exemptions["shared_private_access_sha256"] = data[
        "shared_contract_summary"
    ]["private_access_sha256"]
    exemptions["root_module_sha256"] = data["root_module_sha256"]
    exemptions["exceptions"] = [
        registered.get(str(violation["id"]))
        or inventory._suggest_exception(violation, consumers)
        for violation in sorted(
            data["violations"], key=lambda row: str(row["id"])
        )
    ]
    inventory.INVENTORY_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    exemptions_path.write_text(
        json.dumps(exemptions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    inventory.INVENTORY_MD.write_text(
        inventory.render_markdown(data, exemptions),
        encoding="utf-8",
    )


def _remove_temporary_files() -> None:
    for path in (
        ROOT / ".github/workflows/finalize-remove-qwen-flux.yml",
        ROOT / "scripts/finalize_remove_qwen_flux_hotfix.py",
    ):
        path.unlink(missing_ok=True)


def main() -> None:
    _patch_root_keyboard()
    _patch_active_models()
    _patch_existing_tests()
    _write_surface_regression()
    _write_worklog()
    _refresh_architecture_inventory()
    _run(
        "python",
        "scripts/inventory_package_architecture.py",
        "--label",
        LABEL,
        "--check",
    )
    _run("python", "-m", "compileall", "-q", "main.py", "velvet_bot", "scripts", "tests")
    _remove_temporary_files()


if __name__ == "__main__":
    main()
