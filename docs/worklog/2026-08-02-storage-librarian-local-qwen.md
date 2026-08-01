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
- feature-ветка синхронизирована с текущим `main` commit `056ea79c3fa4dcb66d574e206fea4d5f6b14565a`, чтобы generated inventory и PR merge-check проверяли одну базу.

### Миграции и совместимость

SQL-миграций нет. Существующие анализы и очередь сохраняются. После installer новые и повторно обработанные объекты получают analyzer version `velvet-librarian:qwen3.5-9b-local:v3`. Основной Каэль, coder-агенты и их модели не меняются.

### Проверки

Первый CI подтвердил:

- bounded mypy: зелёный;
- bash syntax и новые local-runtime contract tests выполняются;
- морфологический fallback правильно выбрал `#2134`, а исходное ошибочное ожидание теста было исправлено;
- обнаружен и исправляется drift package architecture inventory;
- project notes contract потребовал полный обязательный шаблон этого worklog;
- Docker workflow продолжает отдельную проверку Compose и images.

Ожидаются повторно:

- package architecture preflight;
- все четыре unit-test shards;
- project notes contract;
- Docker Compose validation и полный Docker build;
- production pull модели и smoke-test объектов `#2143`/`#2134`;
- проверка `docker stats`, swap, времени ответа и provider usage.

### PR и commit

- PR: `#544`;
- ветка: `agent/storage-librarian-local-qwen`;
- исходный проверяемый head: `219b8737eda79b3e032c25887ace08db6032e895`;
- синхронизированный с main head: `3259d1abd1895ac2864c8f1a201fda1a4331e787`;
- финальный зелёный head: ожидается после синхронизации inventory и повторного CI;
- merge commit: ожидается только после отдельного разрешения владельца.

### Незавершённое

- синхронизация package architecture inventory;
- полностью зелёный CI;
- перевод PR из draft и merge;
- production deployment;
- первый download модели;
- подтверждение, что `/storage_ask` отвечает локально и не создаёт provider usage.

### Следующий шаг

Пересчитать package architecture inventory штатным генератором на ветке, уже синхронизированной с `main`, получить зелёный CI, затем после отдельного разрешения владельца слить PR #544 и выполнить production smoke-test.
