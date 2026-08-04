# Фото-генерация: активные модели, лимиты и цены

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

Канонические shared/package architecture snapshots пересобраны для этого каталога.
PR остаётся feature-веткой: merge, миграция `z031` и production rollout выполняются
отдельно.
