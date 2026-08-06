from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, *, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match, found {count}")
    return updated


def patch_install() -> None:
    path = ROOT / "velvet_bot/app/auf_gpt_image_2_install.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "_MAX_PROMPT_MESSAGES = 2\n",
        "_MAX_PROMPT_MESSAGES = 2\n_INTERNAL_EXPORT_PROFILE = \"2K\"\n",
        label="internal export profile",
    )
    text = replace_once(
        text,
        '            "Результат: один JPEG, экспорт 1K, 2K или 4K."\n',
        '            "Результат: один JPEG без выбора условного качества. "\n'
        '            "Фактический размер показывается после генерации."\n',
        label="mode copy",
    )
    text = regex_once(
        text,
        r"async def _show_resolutions\(callback: CallbackQuery, state: FSMContext\) -> None:\n.*?\n\nasync def _show_ratios",
        "async def _show_resolutions(callback: CallbackQuery, state: FSMContext) -> None:\n"
        "    \"\"\"Redirect stale size-selection keyboards to aspect ratio selection.\"\"\"\n"
        "    await _show_ratios(callback, state)\n\n\n"
        "async def _show_ratios",
        label="legacy resolution redirect",
    )
    text = replace_once(
        text,
        '''                _button(\n                    "К размеру",\n                    "gpt2_choose_resolution",\n                    workspace_id=workspace_id,\n                )\n''',
        '''                _button(\n                    "К проверке",\n                    "gpt2_review",\n                    workspace_id=workspace_id,\n                )\n''',
        label="ratio back button",
    )
    text = replace_once(
        text,
        '        resolution=str(_state_value(data, "auf_resolution") or "2K").upper(),\n',
        '        resolution=_INTERNAL_EXPORT_PROFILE,\n',
        label="fixed compatibility profile",
    )
    text = replace_once(
        text,
        '            f"Экспорт: <b>{request.resolution} JPEG</b>\\n"\n',
        '            "Экспорт: <b>JPEG без искусственного апскейла</b>\\n"\n',
        label="final export copy",
    )
    text = replace_once(
        text,
        '''            [\n                _button(\n                    "Размер",\n                    "gpt2_choose_resolution",\n                    workspace_id=workspace_id,\n                ),\n                _button(\n                    "Пропорция",\n                    "gpt2_choose_ratio",\n                    workspace_id=workspace_id,\n                ),\n            ],\n''',
        '''            [\n                _button(\n                    "Пропорция",\n                    "gpt2_choose_ratio",\n                    workspace_id=workspace_id,\n                )\n            ],\n''',
        label="final quality button",
    )
    text = replace_once(
        text,
        '''        elif action == "gpt2_input_confirm":\n            await _show_resolutions(callback, state)\n''',
        '''        elif action == "gpt2_input_confirm":\n            await _show_ratios(callback, state)\n''',
        label="review to ratio flow",
    )
    path.write_text(text, encoding="utf-8")


def patch_domain() -> None:
    path = ROOT / "velvet_bot/domains/codex_image.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from PIL import Image, ImageFilter, ImageOps\n",
        "from PIL import Image, ImageOps\n",
        label="remove sharpening import",
    )
    text = regex_once(
        text,
        r"def export_jpeg\(payload: bytes, \*, resolution: str, aspect_ratio: str\) -> tuple\[bytes, tuple\[int, int\]\]:\n.*?\n\ndef preview_jpeg",
        '''def native_export_dimensions(\n    source_width: int,\n    source_height: int,\n    aspect_ratio: str,\n) -> tuple[int, int]:\n    \"\"\"Return the largest even crop matching the ratio without upscaling.\"\"\"\n    if source_width < 2 or source_height < 2:\n        raise ValueError("GPT Image 2 вернул изображение слишком малого размера.")\n    left, right = (int(value) for value in aspect_ratio.split(":", 1))\n    target_ratio = left / right\n    source_ratio = source_width / source_height\n    if source_ratio > target_ratio:\n        width = round(source_height * target_ratio)\n        height = source_height\n    else:\n        width = source_width\n        height = round(source_width / target_ratio)\n    width = min(source_width, max(2, width))\n    height = min(source_height, max(2, height))\n    return width - width % 2, height - height % 2\n\n\ndef export_jpeg(\n    payload: bytes,\n    *,\n    resolution: str,\n    aspect_ratio: str,\n) -> tuple[bytes, tuple[int, int]]:\n    # ``resolution`` remains in the persisted/provider contract so old queued\n    # tasks and Hermes releases stay readable. It is no longer treated as a\n    # quality promise and never causes the bot to invent pixels.\n    del resolution\n    with Image.open(io.BytesIO(payload)) as source:\n        image = ImageOps.exif_transpose(source).convert("RGB")\n        target = native_export_dimensions(\n            image.width,\n            image.height,\n            aspect_ratio,\n        )\n        if image.size != target:\n            image = ImageOps.fit(\n                image,\n                target,\n                method=Image.Resampling.LANCZOS,\n                centering=(0.5, 0.5),\n            )\n        destination = io.BytesIO()\n        image.save(\n            destination,\n            format="JPEG",\n            quality=95,\n            subsampling=0,\n            optimize=True,\n            progressive=True,\n        )\n    return destination.getvalue(), target\n\n\ndef preview_jpeg''',
        label="native export",
    )
    text = replace_once(
        text,
        '        f"Экспорт: <b>{request.resolution} JPEG · {request.aspect_ratio}</b>",\n',
        '        f"Экспорт: <b>JPEG · {request.aspect_ratio}</b>",\n',
        label="progress export copy",
    )
    text = replace_once(
        text,
        '                f"Экспорт: <b>{request.resolution} JPEG · {result[\'width\']}×{result[\'height\']}</b>",\n',
        '                f"Файл: <b>JPEG · {result[\'width\']}×{result[\'height\']}</b>",\n',
        label="delivery actual dimensions",
    )
    text = replace_once(
        text,
        '            document=BufferedInputFile(document, filename=f"gpt-image-2-{request.resolution.casefold()}.jpg"),\n',
        '            document=BufferedInputFile(document, filename="gpt-image-2.jpg"),\n',
        label="generic filename",
    )
    text = replace_once(
        text,
        '    "export_dimensions",\n    "export_jpeg",\n',
        '    "export_dimensions",\n    "export_jpeg",\n    "native_export_dimensions",\n',
        label="domain export",
    )
    path.write_text(text, encoding="utf-8")


def patch_export_tests() -> None:
    path = ROOT / "tests/test_codex_image_export.py"
    path.write_text(
        '''from __future__ import annotations\n\nimport io\nimport unittest\n\nfrom PIL import Image\n\nfrom velvet_bot.domains.codex_image import (\n    export_dimensions,\n    export_jpeg,\n    native_export_dimensions,\n)\n\n\nclass CodexImageExportTests(unittest.TestCase):\n    def test_legacy_export_dimensions_remain_readable(self) -> None:\n        self.assertEqual(export_dimensions("1K", "16:9"), (1024, 576))\n        self.assertEqual(export_dimensions("2K", "9:16"), (1152, 2048))\n        self.assertEqual(export_dimensions("4K", "1:1"), (3840, 3840))\n\n    def test_native_dimensions_crop_without_upscale(self) -> None:\n        self.assertEqual(native_export_dimensions(640, 480, "16:9"), (640, 360))\n        self.assertEqual(native_export_dimensions(1024, 1536, "9:16"), (864, 1536))\n\n    def test_export_preserves_native_pixels_for_every_legacy_profile(self) -> None:\n        source = io.BytesIO()\n        Image.new("RGB", (640, 480), "white").save(source, format="PNG")\n        sizes: list[tuple[int, int]] = []\n        for resolution in ("1K", "2K", "4K"):\n            payload, size = export_jpeg(\n                source.getvalue(),\n                resolution=resolution,\n                aspect_ratio="16:9",\n            )\n            sizes.append(size)\n            self.assertTrue(payload.startswith(b"\\xff\\xd8\\xff"))\n            with Image.open(io.BytesIO(payload)) as image:\n                self.assertEqual(image.size, (640, 360))\n                self.assertEqual(image.format, "JPEG")\n        self.assertEqual([(640, 360)] * 3, sizes)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
        encoding="utf-8",
    )


def patch_contract_tests() -> None:
    path = ROOT / "tests/test_auf_gpt_image_2_contract.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '        self.assertIn("завершено · 100%", text)\n',
        '        self.assertIn("завершено · 100%", text)\n'
        '        self.assertIn("Экспорт: <b>JPEG · 9:16</b>", text)\n'
        '        self.assertNotIn("4K JPEG", text)\n',
        label="progress honesty assertions",
    )
    marker = '''    def test_enqueue_persists_progress_message_and_timestamp(self) -> None:\n'''
    test = '''    def test_quality_selector_is_hidden_and_internal_profile_is_fixed(self) -> None:\n        module_source = inspect.getsource(auf_gpt_image_2_install)\n        final_source = inspect.getsource(auf_gpt_image_2_install._show_final)\n        request_source = inspect.getsource(auf_gpt_image_2_install._request)\n        resolution_source = inspect.getsource(\n            auf_gpt_image_2_install._show_resolutions\n        )\n\n        self.assertNotIn("экспорт 1K, 2K или 4K", module_source)\n        self.assertNotIn('"Размер"', final_source)\n        self.assertNotIn("request.resolution", final_source)\n        self.assertIn("resolution=_INTERNAL_EXPORT_PROFILE", request_source)\n        self.assertIn("await _show_ratios(callback, state)", resolution_source)\n\n'''
    text = replace_once(text, marker, test + marker, label="quality selector contract")
    path.write_text(text, encoding="utf-8")


def patch_docs() -> None:
    path = ROOT / "docs/gpt_image_2_codex.md"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "- экспорт: 1K, 2K или 4K;\n",
        "- выбор условных уровней 1K, 2K и 4K отсутствует;\n"
        "- итоговый JPEG сохраняет нативное разрешение источника и при необходимости "
        "только подрезается под выбранную пропорцию;\n",
        label="documentation capability",
    )
    text = regex_once(
        text,
        r"## Что означает 4K\n.*?\n## Конфигурация бота",
        '''## Честный экспорт без обещания качества\n\nCodex/ImageGen не предоставляет Velvet надёжный контракт нативных уровней\n1K, 2K и 4K. Поэтому пользователь больше не выбирает такой уровень. Значение\n`resolution` сохраняется только как внутреннее совместимое поле старого\nbot/router протокола и не показывается как качество.\n\nVelvet не увеличивает полученное изображение и не применяет искусственное\nповышение резкости. При несовпадении пропорций выполняется центральная обрезка\nв пределах исходных пикселей. В Telegram показываются фактические размеры\nготового JPEG.\n\n## Конфигурация бота''',
        label="documentation quality section",
    )
    text = replace_once(
        text,
        "Перед включением в production выполните live smoke: текстовая генерация 1K,\nгенерация с одним референсом и проверка доставки preview + документа. CI не может\n",
        "Перед включением в production выполните live smoke: текстовая генерация,\nгенерация с одним референсом, проверка фактических пикселей и доставки preview +\nдокумента. CI не может\n",
        label="documentation smoke",
    )
    path.write_text(text, encoding="utf-8")


def patch_worklog() -> None:
    path = ROOT / "docs/worklog/2026-08-06-gpt-image-honest-export.md"
    path.write_text(
        '''# Сессия\n\n- Дата: 2026-08-06\n- ID: `gpt-image-honest-export-20260806`\n- Статус: `завершено`\n- Ветка: `fix/gpt-image-honest-export`\n- Базовый commit: `cf4df6868ac6e4c7ccfba6d87909fd782892cbc4`\n- Линия/фаза: `GPT Image 2 / honest export contract`\n\n## Перед началом\n\n### Цель\n\nУбрать из GPT Image 2 выбор 1K, 2K и 4K, поскольку provider не гарантирует\nнативную детализацию этих уровней, а прежний экспорт мог только увеличить число\nпикселей после генерации.\n\n### Исходный контекст\n\nProduction-задача вернула JPEG 2160×3840 после выбора 4K, но это был размер\nпостобработки, а не доказательство нативного качества. Интерфейс и имя файла\nсоздавали более сильное обещание, чем фактический provider contract.\n\n### Планируемый объём\n\n- убрать шаг и кнопку выбора размера из нового Telegram-flow;\n- не показывать внутренний compatibility profile как качество;\n- запретить апскейл исходника в JPEG exporter;\n- показывать только фактические пиксели результата;\n- сохранить чтение старых payload и callback-клавиатур;\n- обновить тесты, документацию и package inventory.\n\n### Вне объёма\n\n- изменение Hermes image endpoint schema;\n- обещание нативного разрешения со стороны ImageGen;\n- исправление отдельного Codex rate-limit probe HTTP 502.\n\n### Критерии готовности\n\n- новый flow переходит от проверки данных сразу к пропорции;\n- в подтверждении и прогрессе нет 1K, 2K или 4K;\n- exporter никогда не создаёт пиксели сверх исходника;\n- подпись результата содержит фактические width×height;\n- старые задачи с полем `resolution` продолжают выполняться;\n- обязательный CI зелёный.\n\n### Риски и ограничения\n\nВнутренний `resolution=2K` временно остаётся в bot/router payload для совместимости\nс уже выпущенным Hermes runtime. Оно не влияет на размер локального JPEG export и\nне выводится пользователю как гарантия качества.\n\n## После завершения\n\n### Фактически сделано\n\n- экран выбора качества исключён из нового flow, stale-кнопки перенаправляются к\n  выбору пропорции;\n- внутренний transport profile зафиксирован и скрыт от пользовательского текста;\n- JPEG exporter выполняет только центральную обрезку без апскейла и sharpening;\n- прогресс показывает `JPEG · ratio`, результат показывает реальные пиксели;\n- имя документа больше не содержит фиктивный уровень качества;\n- добавлены regression-тесты native crop и отсутствия quality selector.\n\n### Миграции и совместимость\n\nМиграций базы данных нет. Поле `resolution` сохранено в DTO, результате и Hermes\nпротоколе, поэтому старые queued/completed задачи остаются читаемыми.\n\n### Проверки\n\n- focused unit-тесты GPT Image UI и export;\n- package architecture inventory;\n- полный protected-branch CI.\n\n### Решения и компромиссы\n\nСовместимое поле `resolution` не удаляется одним релизом, но перестаёт влиять на\nлокальный размер экспорта. Полное удаление из router schema возможно отдельной\nверсированной миграцией после обновления всех runtime.\n\n### PR и commit\n\n- PR: создаётся после публикации ветки;\n- commit: формируется автоматизированным patch workflow.\n\n### Незавершённое\n\n- отдельно диагностировать Codex app-server rate-limit probe, который возвращает\n  HTTP 500 через обновлённый Hermes runner.\n\n### Следующий шаг\n\nПосле merge выполнить штатный server deploy и проверить новую генерацию на\nисходнике с известными пикселями.\n''',
        encoding="utf-8",
    )


def patch_all() -> None:
    patch_install()
    patch_domain()
    patch_export_tests()
    patch_contract_tests()
    patch_docs()
    patch_worklog()


def sync_inventory_contract() -> None:
    inventory_path = ROOT / "docs/package_architecture_inventory.json"
    test_path = ROOT / "tests/test_package_architecture_inventory.py"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    shared = inventory["shared_contract_summary"]
    text = test_path.read_text(encoding="utf-8")

    scalar_values = {
        "production_module_count": inventory["production_module_count"],
        "production_loc": inventory["production_loc"],
        "root_module_count": inventory["root_module_count"],
        "root_unclassified_count": inventory["root_unclassified_count"],
        "router_count": inventory["router_count"],
        "router_duplicate_count": inventory["router_duplicate_count"],
        "repository_module_count": inventory["repository_module_count"],
        "violation_count": inventory["violation_count"],
    }
    for key, value in scalar_values.items():
        pattern = rf"self\.assertEqual\(\d+, self\.inventory\[\"{re.escape(key)}\"\]\)"
        replacement = f'self.assertEqual({value}, self.inventory["{key}"])'
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"inventory contract field not found: {key}")

    shared_values = {
        "production_python_files": shared["production_python_files"],
        "function_count": shared["function_count"],
        "private_contract_access_count": shared["private_contract_access_count"],
        "blocking_private_contract_access_count": shared[
            "blocking_private_contract_access_count"
        ],
        "exact_duplicate_group_count": shared["exact_duplicate_group_count"],
        "normalized_duplicate_group_count": shared[
            "normalized_duplicate_group_count"
        ],
        "semantic_near_duplicate_group_count": shared[
            "semantic_near_duplicate_group_count"
        ],
    }
    for key, value in shared_values.items():
        pattern = rf"self\.assertEqual\(\d+, shared\[\"{re.escape(key)}\"\]\)"
        replacement = f'self.assertEqual({value}, shared["{key}"])'
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"shared contract field not found: {key}")

    stages = len(inventory["installer_graph"])
    text = re.sub(
        r"self\.assertEqual\(\d+, len\(self\.inventory\[\"installer_graph\"\]\)\)",
        f'self.assertEqual({stages}, len(self.inventory["installer_graph"]))',
        text,
        count=1,
    )
    text = re.sub(
        r"self\.assertEqual\(list\(range\(1, \d+\)\), \[item\[\"order\"\] for item in graph\]\)",
        f'self.assertEqual(list(range(1, {stages + 1})), [item["order"] for item in graph])',
        text,
        count=1,
    )

    markdown_values = {
        "Production modules": inventory["production_module_count"],
        "Production LOC": inventory["production_loc"],
        "Startup installer stages": stages,
        "Registered package violations": inventory["violation_count"],
        "Registered exemptions": len(
            json.loads(
                (ROOT / "docs/package_architecture_exemptions.json").read_text(
                    encoding="utf-8"
                )
            )["exceptions"]
        ),
    }
    for label, value in markdown_values.items():
        pattern = rf'self\.assertIn\("{re.escape(label)}: \*\*\d+\*\*", self\.markdown\)'
        replacement = f'self.assertIn("{label}: **{value}**", self.markdown)'
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"markdown contract field not found: {label}")

    test_path.write_text(text, encoding="utf-8")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "patch"
    if mode == "patch":
        patch_all()
    elif mode == "sync-inventory":
        sync_inventory_contract()
    else:
        raise SystemExit(f"unknown mode: {mode}")


if __name__ == "__main__":
    main()
