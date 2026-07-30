# 2026-07-30 — GRS-only Banana и deprecation Ollama

- Дата: 2026-07-30
- ID: grs-only-media-and-ollama-deprecation
- Статус: выполнено в feature-ветке
- Ветка: `agent/grs-only-media-config`

## Цель

Устранить остаточную Kie-конфигурацию Nano Banana, закрепить Nano Banana 2 и
Nano Banana Pro только за GRS AI и исключить случайное повторное включение
локального Ollama на production VPS.

## Сделано

- `Nano Banana 2` и `Nano Banana Pro` читают только `GRS_NANO_BANANA_*_MODEL`;
- удалён fallback `KIE_NANO_BANANA_PRO_MODEL`;
- старые `KIE_NANO_*` цены больше не читаются загрузчиком settings;
- включённый media-контур требует одновременно `KIE_API_KEY` и `GRS_API_KEY`;
- `.env.example` и `.env.server.example` синхронизированы с фактическими
  Kie/GRS маршрутами и содержат явные model ID всех подключённых моделей;
- server preflight проверяет оба провайдера и все обязательные media routes;
- server preflight запрещает `ollama` как text, vision или VL cascade provider;
- `docs/AI_VISION.md` переписан под текущий облачный VL-контур, Ollama помечен
  `legacy/deprecated`;
- тесты preflight покрывают обязательный GRS key и запрет Ollama.

## Совместимость

Runtime-типы и старые Ollama-адаптеры пока не удаляются. Они сохраняются для
чтения прежних конфигураций, старых queued payload и последующей контролируемой
миграции. Production server preflight блокирует их использование.

Внутренние legacy-поля `KiePricing.nano_1k_2k_usd` и `nano_4k_usd` также пока
не удаляются из dataclass, чтобы не расширять эту задачу до несовместимой
миграции сериализованных объектов. Загрузчик больше не связывает их с env.

## Следующий отдельный этап

Добавить model-specific input modes в Ауф:

- Seedream 5 Pro: text-to-image и image-to-image;
- Qwen2: `qwen2/text-to-image` и `qwen2/image-edit`;
- FLUX.2 Pro: `flux-2/pro-text-to-image` и
  `flux-2/pro-image-to-image`;
- Nano Banana 2/Pro через GRS: text-only, photo-only и photo+text;
- Seedance 1.5 Pro и Grok: отдельные text-to-video маршруты там, где они
  документированы провайдером.

Этот этап требует переработки текущего photo/video FSM, который сейчас жёстко
собирает фото + текст до выбора модели.
