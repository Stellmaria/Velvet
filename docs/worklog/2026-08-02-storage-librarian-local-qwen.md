# Сессия: локальный Qwen для Storage Librarian

- Дата: 2026-08-02
- ID: `storage-librarian-local-qwen-20260802`
- Линия/фаза: Telegram Storage Librarian, local inference и индексный поиск
- Статус: `частично`
- Ветка: `agent/storage-librarian-local-qwen`
- Базовый commit: `3bbb7ba453b8244334f354d75ebba7f59ebf60cd`

## Перед началом

### Цель

Убрать провайдерские расходы Storage Librarian для анализа логов и ответов по индексу, сохранив отдельную Hermes-сущность и manual-first rollout.

### Подтверждённый production-контекст

- VPS: 8 vCPU AMD Ryzen 9 5950X, 23 GiB RAM, 4 GiB swap, 202 GiB свободного диска;
- NVIDIA GPU отсутствует;
- Ollama до этого не был установлен;
- manual-first анализ объектов `#2149`, `#2134` и `#2143` успешно работал через отдельный Hermes runtime;
- `/storage_ask какие ошибки и предупреждения повторялись?` возвращал пустой результат, потому что repository искал весь вопрос одной строкой через `ILIKE` и не передавал контекст модели.

### Решение

- отдельный внутренний `ollama-librarian` без host port;
- официальный image `ollama/ollama:0.32.3`;
- исходная модель `qwen3.5:9b-q4_K_M`;
- alias `velvet-librarian-local:v1` с `num_ctx=65536`;
- 14 GiB RAM и 6 vCPU как верхние container limits;
- local custom endpoint для Hermes;
- cloud fallback и inherited cloud auxiliary routes удаляются;
- common cloud API keys обнуляются внутри Librarian container;
- буквальный SQL search дополняется bounded morphologic fallback по последним анализам.

### Безопасность

- Telegram/GitHub credentials по-прежнему отсутствуют;
- toolsets остаются deny-all;
- Ollama доступен только через `velvet_backend`;
- backup, encrypted, watermarks и analysis остаются запрещёнными категориями;
- `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` не меняется;
- локальная ошибка не должна переключаться на платный provider.

## Фактически сделано

- добавлены `Modelfile` и `start.sh`;
- Compose получил отдельный Ollama service и persistent volume;
- systemd сначала поднимает Ollama, скачивает/создаёт модель и затем запускает Hermes;
- installer перезапускает существующий oneshot unit, а не ограничивается `enable --now`;
- Hermes profile использует `provider: custom`, private base URL и context 65536;
- fallback providers и legacy fallback model удалены;
- auxiliary compression направлена на main local model, title generation выключена;
- analyzer version изменена на `velvet-librarian:qwen3.5-9b-local:v3`;
- timeout CPU-only inference увеличен до 900 секунд;
- `/storage_ask` получил нормализацию русских/английских окончаний и bounded fallback;
- добавлены contract tests и runbook.

## Проверки

Ожидаются:

- bash syntax для installers/start script;
- Python compile;
- unit tests local runtime и поиска;
- mypy;
- Docker Compose validation;
- полный tests workflow;
- production pull модели и smoke-test объектов `#2143`/`#2134`;
- проверка `docker stats`, swap и времени ответа.

## Незавершённое

- CI;
- PR и merge;
- production deployment;
- первый download модели около 6,6 ГБ;
- подтверждение, что `/storage_ask` отвечает локально и не создаёт provider usage.
