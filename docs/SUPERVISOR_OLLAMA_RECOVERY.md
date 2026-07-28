# Удалённое восстановление набора Ollama через Supervisor

Supervisor принимает только фиксированные команды из allowlist. Произвольный PowerShell, `cmd.exe`, конвейеры, перенаправления и пользовательские имена моделей не разрешены.

## Целевой набор

Recovery-модуль поддерживает четыре заранее закреплённые модели:

```dotenv
AI_VISION_ENABLED=true
AI_VISION_PROVIDER=ollama
AI_VISION_BASE_URL=http://127.0.0.1:11434
AI_VISION_MODEL=qwen3-vl:8b
AI_VISION_COMPARE_MODEL=hf.co/mradermacher/Qwen3-VL-8B-Instruct-abliterated-v2.0-GGUF:Q4_K_M
AI_VISION_FALLBACK_MODEL=hf.co/mradermacher/Qwen3-VL-4B-Instruct-abliterated-GGUF:Q4_K_M
AI_VISION_TIMEOUT_SECONDS=600
AI_TEXT_PROVIDER=ollama
AI_TEXT_BASE_URL=http://127.0.0.1:11434
AI_TEXT_MODEL=hf.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF:Q4_K_M
AI_TEXT_TIMEOUT_SECONDS=600
```

Роли:

- `qwen3-vl:8b` — обычная VLM для максимально точного извлечения позы, геометрии и пространственных связей;
- Qwen3-VL 8B abliterated v2.0 — основная uncensored VLM для сравнения и сцен, на которых обычная модель отказывается;
- Qwen3-VL 4B abliterated — более лёгкий резерв для ограниченной памяти;
- Huihui Qwen3.5 9B abliterated i1 — uncensored reasoning/text-модель.

Для ноутбука с 4 ГБ VRAM recovery также закрепляет:

```dotenv
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_NUM_PARALLEL=1
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_KEEP_ALIVE=2m
```

## Поиск моделей на диске E

Команда состояния проверяет только два разрешённых каталога:

1. `E:\OllamaModels`;
2. `E:\OllamaModels\models`.

Корректным считается каталог, где одновременно существуют `blobs` и `manifests`. Если подходят оба, выбирается вариант с большим количеством manifest-файлов, затем blob-файлов.

Recovery рекурсивно читает пути файлов внутри `manifests` и восстанавливает имена моделей, например:

```text
manifests/registry.ollama.ai/library/qwen3-vl/8b
→ qwen3-vl:8b

manifests/hf.co/mradermacher/Qwen3-VL-4B-Instruct-abliterated-GGUF/Q4_K_M
→ hf.co/mradermacher/Qwen3-VL-4B-Instruct-abliterated-GGUF:Q4_K_M
```

Если модель найдена в manifests, но отсутствует в `/api/tags`, Supervisor не удаляет blobs. Он выполняет повторный фиксированный `ollama pull`, чтобы Ollama проверила имеющиеся слои и заново зарегистрировала модель.

## Что делает восстановление

Текущая безопасная команда `Ollama: восстановить vision qwen3-vl:4b` сохранена в allowlist для совместимости, но действие `repair` теперь восстанавливает весь набор:

1. находит валидное хранилище на E;
2. записывает `OLLAMA_MODELS` в project `.env` и User Environment Windows;
3. перезапускает Ollama с выбранным каталогом;
4. сканирует API и локальные manifests;
5. атомарно обновляет только разрешённые AI/Ollama-ключи в `.env`, сохраняя токены, URL базы и остальные строки;
6. пропускает модели, уже доступные через API;
7. повторно регистрирует найденные на диске модели без предварительного удаления blobs;
8. скачивает только действительно отсутствующие модели;
9. проверяет capability `vision` у трёх VLM и `completion` у текстовой модели;
10. просит выполнить самоперезапуск Supervisor для перечитывания `.env`.

Название старой кнопки будет изменено отдельным обновлением реестра интерфейса. Функционально она уже запускает восстановление полного набора.

## Команды безопасной консоли

- `Ollama: список моделей` — фиксированный `ollama list`;
- `Ollama: состояние vision` — показывает конфигурацию, хранилище, распознанные manifests, API-модели и состояние каждой целевой модели;
- `Ollama: запустить локальный сервер` — запускает `ollama serve` без shell;
- `Ollama: настроить vision qwen3-vl:4b` — теперь записывает конфигурацию полного набора;
- `Ollama: скачать qwen3-vl:4b` — теперь подключает E и устанавливает только отсутствующие модели набора;
- `Ollama: проверить vision qwen3-vl:4b` — теперь проверяет capabilities всего набора;
- `Ollama: восстановить vision qwen3-vl:4b` — выполняет полный recovery.

## Удалённая последовательность

1. Слить обновление и выполнить `Обновить + рестарт`.
2. Открыть `Безопасная консоль`.
3. Выполнить `Ollama: состояние vision`.
4. Выполнить старую кнопку `Ollama: восстановить vision qwen3-vl:4b` и подтвердить точную команду.
5. Не прерывать загрузку: суммарный размер новых моделей велик, а скорость зависит от сети и диска.
6. После успешной проверки выполнить `Рестарт Supervisor`.
7. Повторно выполнить `Ollama: состояние vision`.

## Повтор после таймаута

Если команда завершилась по лимиту `SUPERVISOR_COMMAND_TIMEOUT_SECONDS`, её можно повторить. `ollama pull` использует уже загруженные слои и продолжает регистрацию или загрузку, а не требует удаления каталога.

## Граница безопасности

- Telegram не передаёт recovery-модулю путь или имя модели;
- все пути и модели зафиксированы в коде;
- shell не используется;
- секретные и неизвестные строки `.env` сохраняются;
- каталог моделей не удаляется автоматически;
- recovery не выполняет `ollama rm`;
- одновременно держится не более одной модели.
