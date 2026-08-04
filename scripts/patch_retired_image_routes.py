from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:100]!r}")
    write(path, content.replace(old, new, 1))


def sub_once(path: str, pattern: str, replacement: str) -> None:
    content = read(path)
    updated, count = re.subn(pattern, replacement, content, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{path}: expected one regex match, found {count}: {pattern[:100]!r}")
    write(path, updated)


def patch_models() -> None:
    path = "velvet_bot/domains/media_generation/models.py"
    replace_once(path, '    qwen2_image_edit: str = "qwen2/image-edit"\n', '')
    replace_once(path, '    flux_2_pro_image: str = "flux-2/pro-image-to-image"\n', '')
    replace_once(
        path,
        '''        elif alias is KieModelAlias.QWEN2_IMAGE_EDIT:
            model = self.qwen2_image_edit
''',
        '',
    )
    replace_once(
        path,
        '''        elif alias is KieModelAlias.FLUX_2_PRO_IMAGE:
            model = self.flux_2_pro_image
''',
        '',
    )
    replace_once(path, '    qwen2_image_edit_usd: Decimal = Decimal("0.02")\n', '')
    replace_once(path, '    flux_2_pro_1k_usd: Decimal = Decimal("0.045")\n', '')
    replace_once(path, '    flux_2_pro_2k_usd: Decimal = Decimal("0.075")\n', '')
    replace_once(
        path,
        '''        if request.model is KieModelAlias.QWEN2_IMAGE_EDIT:
            return self.qwen2_image_edit_usd
''',
        '',
    )
    replace_once(
        path,
        '''        if request.model is KieModelAlias.FLUX_2_PRO_IMAGE:
            return (
                self.flux_2_pro_2k_usd
                if request.resolution.casefold() == "2k"
                else self.flux_2_pro_1k_usd
            )
''',
        '',
    )
    sub_once(
        path,
        r'''        elif self\.model is KieModelAlias\.QWEN2_IMAGE_EDIT:.*?(?=        elif self\.model in \{\n            KieModelAlias\.WAN_27_IMAGE,)''',
        '',
    )
    sub_once(
        path,
        r'''        elif self\.model is KieModelAlias\.FLUX_2_PRO_IMAGE:.*?(?=        elif self\.model is KieModelAlias\.GROK_IMAGINE_VIDEO:)''',
        '',
    )


def patch_env(path: str, *, server: bool) -> None:
    content = read(path)
    content = content.replace(
        "# Генерация изображений и видео. Seedream/Qwen/Wan/FLUX/видео идут через Kie.ai.",
        "# Генерация изображений и видео. Seedream/Wan/видео идут через Kie.ai.",
    )
    content = content.replace("KIE_QWEN2_IMAGE_EDIT_MODEL=qwen2/image-edit\n", "")
    content = content.replace("KIE_FLUX_2_PRO_IMAGE_MODEL=flux-2/pro-image-to-image\n", "")
    content = content.replace(
        "KIE_WAN_27_IMAGE_MODEL=wan/2-7-image\n",
        "KIE_WAN_27_IMAGE_MODEL=wan/2-7-image\n"
        "KIE_WAN_27_IMAGE_PRO_MODEL=wan/2-7-image-pro\n",
    )
    content = content.replace("KIE_QWEN2_IMAGE_EDIT_USD=0.02\n", "")
    content = content.replace("KIE_FLUX_2_PRO_IMAGE_1K_USD=0.045\n", "")
    content = content.replace("KIE_FLUX_2_PRO_IMAGE_2K_USD=0.075\n", "")
    content = content.replace("KIE_WAN_27_IMAGE_1K_USD=0.05\n", "KIE_WAN_27_IMAGE_1K_USD=0.03\n")
    content = content.replace("KIE_WAN_27_IMAGE_2K_USD=0.08\n", "KIE_WAN_27_IMAGE_2K_USD=0.03\n")
    content = content.replace(
        "KIE_WAN_27_IMAGE_2K_USD=0.03\n",
        "KIE_WAN_27_IMAGE_2K_USD=0.03\n"
        "KIE_WAN_27_IMAGE_PRO_1K_USD=0.075\n"
        "KIE_WAN_27_IMAGE_PRO_2K_USD=0.075\n"
        "KIE_WAN_27_IMAGE_PRO_4K_USD=0.075\n",
    )
    if server:
        content = content.replace(
            "# Kie + GRS media generation. Banana 2/Pro работают только через GRS AI.",
            "# Kie + GRS media generation. Banana 2/Pro работают только через GRS AI; "
            "активные изображения: Banana 2, Banana Pro, Seedream, Wan 2.7 и Wan 2.7 Pro.",
        )
    write(path, content)


def patch_preflight() -> None:
    path = "scripts/server_preflight.py"
    replace_once(path, '            "KIE_QWEN2_IMAGE_EDIT_MODEL",\n', '')
    replace_once(path, '            "KIE_FLUX_2_PRO_IMAGE_MODEL",\n', '')
    replace_once(
        path,
        '            "KIE_WAN_27_IMAGE_MODEL",\n',
        '            "KIE_WAN_27_IMAGE_MODEL",\n'
        '            "KIE_WAN_27_IMAGE_PRO_MODEL",\n',
    )


def patch_preflight_tests() -> None:
    path = "tests/test_server_preflight.py"
    replace_once(path, '                    "KIE_QWEN2_IMAGE_EDIT_MODEL": "qwen2/image-edit",\n', '')
    replace_once(path, '                    "KIE_FLUX_2_PRO_IMAGE_MODEL": "flux-2/pro-image-to-image",\n', '')
    replace_once(
        path,
        '                    "KIE_WAN_27_IMAGE_MODEL": "wan/2-7-image",\n',
        '                    "KIE_WAN_27_IMAGE_MODEL": "wan/2-7-image",\n'
        '                    "KIE_WAN_27_IMAGE_PRO_MODEL": "wan/2-7-image-pro",\n',
    )


def patch_cloud_contract() -> None:
    path = "tests/test_cloud_migration_contract.py"
    replace_once(
        path,
        '''        # Cloud Kie model IDs such as qwen2/image-edit are legitimate and must not
        # be confused with the removed local Qwen/Ollama runtime.
        self.assertIn("kie_qwen2_image_edit_model=qwen2/image-edit", normalized)
''',
        '''        self.assertIn("kie_wan_27_image_model=wan/2-7-image", normalized)
        self.assertIn(
            "kie_wan_27_image_pro_model=wan/2-7-image-pro",
            normalized,
        )
        self.assertNotIn("kie_qwen2_image_edit_model", normalized)
        self.assertNotIn("kie_flux_2_pro_image_model", normalized)
''',
    )


def patch_capability_tests() -> None:
    path = "tests/test_photo_model_capabilities.py"
    replace_once(
        path,
        '''        self.assertFalse(KieModelAlias.QWEN2_IMAGE_EDIT.is_photo_model)
        self.assertFalse(KieModelAlias.FLUX_2_PRO_IMAGE.is_photo_model)

''',
        '''        self.assertFalse(KieModelAlias.QWEN2_IMAGE_EDIT.is_photo_model)
        self.assertFalse(KieModelAlias.FLUX_2_PRO_IMAGE.is_photo_model)

    def test_retired_image_aliases_have_no_provider_or_pricing_route(self) -> None:
        from velvet_bot.domains.media_generation import KieModelCatalog

        catalog = KieModelCatalog()
        pricing = KiePricing()
        for model in (
            KieModelAlias.QWEN2_IMAGE_EDIT,
            KieModelAlias.FLUX_2_PRO_IMAGE,
        ):
            with self.subTest(model=model):
                with self.assertRaisesRegex(ValueError, "Неизвестная модель"):
                    catalog.provider_model(model, input_mode=KieInputMode.PHOTO_TEXT)
                request = KieGenerationRequest(
                    model=model,
                    input_mode=KieInputMode.PHOTO_TEXT,
                    prompt="legacy",
                    references=_references(1),
                    aspect_ratio="1:1",
                    resolution="1K",
                )
                with self.assertRaisesRegex(ValueError, "Неизвестная модель"):
                    pricing.estimate_usd(request)

''',
    )


def patch_docs() -> None:
    write(
        "docs/photo_generation_capabilities.md",
        '''# Фото-генерация: активные модели, лимиты и цены

Интерфейс Ауф предлагает только пять активных моделей изображений. Удалённые
Qwen Image и FLUX не имеют capability, provider route, env-настроек или цен для
новых задач. Их старые строковые alias остаются только для чтения исторических
payload и не могут быть запущены повторно.

## Активные модели

| Alias | Provider model id | Провайдер | Референсы | Качество | Цена |
|---|---|---|---:|---|---|
| `nano_banana_2` | `nano-banana-2` | GRS AI | до 5 | 1K, 2K, 4K | 1 / 2 / 3 VL |
| `nano_banana_pro` | `nano-banana-pro` | GRS AI | до 5 | 1K, 2K, 4K | 2 / 3 / 4 VL |
| `seedream_5_pro` | `seedream/5-pro-*` | Kie.ai | до 10 | 1K, 2K | 2 / 4 VL |
| `wan_27_image` | `wan/2-7-image` | Kie.ai | до 9 | 1K, 2K | 1 / 2 VL |
| `wan_27_image_pro` | `wan/2-7-image-pro` | Kie.ai | до 9 | 1K, 2K, 4K | 3 / 4 / 5 VL |

Wan 2.7 Pro в 4K доступен только в режиме «Только текст». Для режима
«Фото + текст» интерфейс предлагает 1K и 2K.

## Переменные окружения

```dotenv
KIE_SEEDREAM_5_PRO_TEXT_MODEL=seedream/5-pro-text-to-image
KIE_SEEDREAM_5_PRO_IMAGE_MODEL=seedream/5-pro-image-to-image
KIE_WAN_27_IMAGE_MODEL=wan/2-7-image
KIE_WAN_27_IMAGE_PRO_MODEL=wan/2-7-image-pro
GRS_NANO_BANANA_2_MODEL=nano-banana-2
GRS_NANO_BANANA_PRO_MODEL=nano-banana-pro

KIE_WAN_27_IMAGE_1K_USD=0.03
KIE_WAN_27_IMAGE_2K_USD=0.03
KIE_WAN_27_IMAGE_PRO_1K_USD=0.075
KIE_WAN_27_IMAGE_PRO_2K_USD=0.075
KIE_WAN_27_IMAGE_PRO_4K_USD=0.075
```

Предварительная USD-оценка используется бюджетным guard. Пользовательская цена
берётся из версионированного каталога Ауф и фиксируется перед постановкой задачи
в очередь.

## Wan payload

Обе Wan-модели используют `prompt`, `input_urls` для режима с референсами,
`n`, `enable_sequential`, `resolution`, `aspect_ratio` и provider NSFW flag.
Количество результатов оплачивается пропорционально и не зависит от цен пакетов VL.
''',
    )


def patch_worklog() -> None:
    path = "docs/worklog/2026-08-04-auf-pricing-economy-hardening.md"
    replace_once(
        path,
        "- Qwen Image и FLUX удалены из активных capability/config/pricing-контуров; durable aliases сохранены только для чтения исторических задач.\n",
        "- Qwen Image и FLUX удалены из capability, provider routing, payload builders, env-конфигурации и pricing; строковые alias сохранены только для десериализации исторических задач.\n",
    )


def sync_inventory_test() -> None:
    inventory = json.loads(read("docs/package_architecture_inventory.json"))
    path = "tests/test_package_architecture_inventory.py"
    content = read(path)
    replacements = {
        r'self\.assertEqual\([\d_]+, self\.inventory\["production_module_count"\]\)':
            f'self.assertEqual({inventory["production_module_count"]:_}, self.inventory["production_module_count"])',
        r'self\.assertEqual\([\d_]+, self\.inventory\["production_loc"\]\)':
            f'self.assertEqual({inventory["production_loc"]:_}, self.inventory["production_loc"])',
        r'self\.assertEqual\([\d_]+, self\.inventory\["root_module_count"\]\)':
            f'self.assertEqual({inventory["root_module_count"]:_}, self.inventory["root_module_count"])',
        r'self\.assertEqual\([\d_]+, self\.inventory\["router_count"\]\)':
            f'self.assertEqual({inventory["router_count"]:_}, self.inventory["router_count"])',
        r'self\.assertEqual\([\d_]+, self\.inventory\["repository_module_count"\]\)':
            f'self.assertEqual({inventory["repository_module_count"]:_}, self.inventory["repository_module_count"])',
        r'self\.assertEqual\([\d_]+, self\.inventory\["violation_count"\]\)':
            f'self.assertEqual({inventory["violation_count"]:_}, self.inventory["violation_count"])',
    }
    shared = inventory["shared_contract_summary"]
    shared_keys = (
        "production_python_files",
        "function_count",
        "private_contract_access_count",
        "blocking_private_contract_access_count",
        "exact_duplicate_group_count",
        "normalized_duplicate_group_count",
        "semantic_near_duplicate_group_count",
    )
    for key in shared_keys:
        replacements[
            rf'self\.assertEqual\([\d_]+, shared\["{key}"\]\)'
        ] = f'self.assertEqual({int(shared[key]):_}, shared["{key}"])'
    for pattern, replacement in replacements.items():
        content, count = re.subn(pattern, replacement, content, count=1)
        if count != 1:
            raise RuntimeError(f"cannot sync inventory assertion: {pattern}")
    markdown_values = {
        "Production modules": inventory["production_module_count"],
        "Production LOC": inventory["production_loc"],
        "Startup installer stages": len(inventory["installer_graph"]),
        "Registered package violations": inventory["violation_count"],
        "Registered exemptions": inventory["violation_count"],
    }
    for label, value in markdown_values.items():
        content, count = re.subn(
            rf'"{re.escape(label)}: \*\*[\d]+\*\*"',
            f'"{label}: **{value}**"',
            content,
            count=1,
        )
        if count != 1:
            raise RuntimeError(f"cannot sync markdown assertion: {label}")
    write(path, content)


def main() -> None:
    patch_models()
    patch_env(".env.example", server=False)
    patch_env(".env.server.example", server=True)
    patch_preflight()
    patch_preflight_tests()
    patch_cloud_contract()
    patch_capability_tests()
    patch_docs()
    patch_worklog()


if __name__ == "__main__":
    if "--sync-inventory" in sys.argv:
        sync_inventory_test()
    else:
        main()
