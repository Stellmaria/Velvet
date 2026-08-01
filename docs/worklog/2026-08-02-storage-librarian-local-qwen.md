# Сессия: локальный Qwen для Storage Librarian

- Дата: 2026-08-02
- ID: `storage-librarian-local-qwen-20260802`
- Линия/фаза: Telegram Storage Librarian, local inference и индексный поиск
- Статус: `частично`
- Ветка: `agent/storage-librarian-local-qwen`
- Базовый commit: `056ea79c3fa4dcb66d574e206fea4d5f6b14565a`

## Перед началом

### Цель

Убрать провайдерские расходы Storage Librarian для анализа логов и ответов по индексу, сохранив отдельную Hermes-сущность и manual-first rollout.

### Исходный контекст

- VPS: 8 vCPU AMD Ryzen 9 5950X, 23 GiB RAM, 4 GiB swap, 202 GiB свободного диска;
- NVIDIA GPU отсутствует;
- Ollama до этого не был установлен;
- manual-first анализ объектов `#2149`, `#2134` и `#2143` успешно работал через отдельный Hermes runtime;
- `/storage_ask какие ошибки и предупреждения повторялись?` возвращал пустой результат, потому что repository искал весь вопрос одной строкой через `ILIKE` и не передавал контекст модели.

### Планируемый объём

- отдельный внутренний `ollama-librarian` без host port;
- закреплённый локальный Qwen 3.5 9B;
- persistent volume модели и bounded CPU/RAM limits;
- local-only Hermes profile без cloud fallback и cloud auxiliary routes;
- idempotent installer и systemd lifecycle;
- морфологический fallback для `/storage_ask`;
- tests, runbook и architecture inventory.

### Критерии готовности

- анализ и `/storage_ask` работают через локальный OpenAI-compatible endpoint;
- common cloud API keys внутри Librarian runtime обнулены;
- fallback providers и inherited auxiliary cloud routes отсутствуют;
- Ollama не публикует host port;
- `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` сохраняется;
- запрос об ошибках находит релевантный `#2134`, но не трактует «ошибок нет» как ошибку;
- CI полностью зелёный;
- production smoke подтверждает локальную модель, отчёт и отсутствие provider usage.

### Риски и ограничения

- CPU-only inference медленнее облачного;
- первый pull модели требует около 6,6 ГБ трафика и диска;
- большой контекст увеличивает RAM и время обработки;
- systemd должен допускать длительный первый запуск;
- локальная недоступность должна завершаться явной ошибкой, а не платным fallback;
- массовая очередь остаётся выключенной до проверки времени, памяти и swap.

## После завершения

### Фактически сделано

- добавлены `Modelfile` и `start.sh`;
- Compose получил отдельный Ollama service и persistent volume;
- используется image `ollama/ollama:0.32.3` и исходная модель `qwen3.5:9b-q4_K_M`;
- создаётся alias `velvet-librarian-local:v1` с `num_ctx=65536`;
- Ollama ограничен 14 GiB RAM, 6 vCPU, одной загруженной моделью и одним параллельным запросом;
- systemd сначала поднимает Ollama, скачивает/пересоздаёт модель и затем запускает Hermes;
- installer перезапускает существующий oneshot unit, а не ограничивается `enable --now`;
- Hermes profile использует `provider: custom`, private base URL и context 65536;
- fallback providers и legacy fallback model удалены;
- auxiliary compression направлена на main local model, title generation выключена;
- common cloud API keys внутри Librarian container обнулены;
- analyzer version изменена на `velvet-librarian:qwen3.5-9b-local:v3`;
- timeout CPU-only inference увеличен до 900 секунд;
- `/storage_ask` получил нормализацию русских/английских окончаний и bounded fallback;
- fallback не подставляет случайные последние записи и не принимает отрицательную фразу «ошибок нет» за инцидент;
- добавлены contract tests и runbook;
- открыт draft PR #544;
- feature-ветка синхронизирована с текущим `main` commit `056ea79c3fa4dcb66d574e206fea4d5f6b14565a`;
- package architecture inventory атомарно пересчитан с меткой `p1-package-architecture-baseline`;
- inventory фиксирует 640 production-модулей и 139184 строк кода;
- временный write-workflow удалён из итоговой ветки.

### Миграции и совместимость

SQL-миграций нет. Существующие анализы и очередь сохраняются. После installer новые и повторно обработанные объекты получают analyzer version `velvet-librarian:qwen3.5-9b-local:v3`. Основной Каэль, coder-агенты и их модели не меняются.

### Проверки

Подтверждено на промежуточных head:

- bounded mypy: зелёный;
- project notes contract: зелёный после приведения worklog к обязательному шаблону;
- bash syntax и новые local-runtime contract tests выполняются;
- морфологический fallback правильно выбирает `#2134`;
- запрос не трактует фразу «ошибок нет» как подтверждённый инцидент;
- Docker Compose принимает отдельный Ollama runtime;
- package architecture inventory синхронизирован штатным генератором на текущей базе `main`.

На финальном пользовательском commit повторно ожидаются:

- package architecture preflight;
- все четыре unit-test shards;
- bounded mypy;
- project notes contract;
- Docker Compose validation и полный Docker build;
- Krita smoke-test.

После merge на production остаются:

- pull модели и создание локального alias;
- smoke-test объектов `#2143`/`#2134`;
- проверка `docker stats`, swap, времени ответа и provider usage.

### PR и commit

- PR: `#544`;
- ветка: `agent/storage-librarian-local-qwen`;
- исходный проверяемый head: `219b8737eda79b3e032c25887ace08db6032e895`;
- синхронизированный с main head: `3259d1abd1895ac2864c8f1a201fda1a4331e787`;
- inventory commit: `2af5cdc216833ca43945d6886ef1ebf976b336e6`;
- финальный зелёный head: ожидается после повторного CI;
- merge commit: ожидается только после отдельного разрешения владельца.

### Незавершённое

- полностью зелёный CI на обычном пользовательском commit;
- перевод PR из draft и merge;
- production deployment;
- первый download модели;
- подтверждение, что `/storage_ask` отвечает локально и не создаёт provider usage.

### Следующий шаг

Получить полностью зелёный CI. После отдельного разрешения владельца слить PR #544, обновить VPS и выполнить production smoke-test локальной модели.
