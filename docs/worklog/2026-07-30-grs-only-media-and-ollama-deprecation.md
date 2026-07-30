# 2026-07-30 — GRS-only Banana и deprecation Ollama

- Дата: 2026-07-30
- ID: grs-only-media-and-ollama-deprecation
- Линия/фаза: Media providers / cloud migration cleanup
- Статус: завершено
- Ветка: `agent/grs-only-media-config`
- Базовый commit: `d18ad4fd24b3dfa84d255148aee065b97b52ea9b`

## Перед началом

### Цель

Устранить остаточную Kie-конфигурацию Nano Banana, закрепить Nano Banana 2 и
Nano Banana Pro только за GRS AI и исключить случайное повторное включение
локального Ollama на production VPS.

### Исходный контекст

Клиент уже отправлял обе Banana в GRS AI, однако загрузчик settings, публичные
env-шаблоны и server preflight всё ещё содержали Kie fallback для
`Nano Banana Pro` и старые Kie-тарифы Banana. Ollama был отключён фактически,
но production validator всё ещё разрешал указать его как text или vision
provider. Одновременно публичный env-контракт ошибочно запрещал любое слово
`qwen`, из-за чего облачный Kie ID `qwen2/image-edit` нельзя было описать явно.

### Планируемый объём

- удалить чтение `KIE_NANO_BANANA_PRO_MODEL` и Kie-тарифов Banana;
- сделать `GRS_API_KEY` обязательным при включённом media-контуре;
- синхронизировать `.env.example` и `.env.server.example`;
- проверить все обязательные Kie и GRS model IDs в server preflight;
- запретить Ollama на production VPS, сохранив runtime-совместимость;
- обновить документацию и регрессионные тесты;
- не менять FSM генерации и queued payload в этой задаче.

### Критерии готовности

- обе Banana читают только `GRS_NANO_BANANA_*` переменные;
- без `GRS_API_KEY` включённый media-контур не запускается;
- env-шаблоны не содержат Kie Banana fallback и локальных Ollama моделей;
- облачный `qwen2/image-edit` не ошибочно считается локальным runtime;
- server preflight отклоняет Ollama для text, vision и VL cascade;
- project notes, type check, unit tests и docker build проходят.

### Риски и ограничения

- удаление legacy runtime-классов Ollama может сломать старые queued payload и
  поэтому вынесено в отдельную миграцию;
- внутренние поля `KiePricing.nano_1k_2k_usd` и `nano_4k_usd` сохраняются до
  отдельной несовместимой очистки dataclass;
- текущий photo/video FSM по-прежнему собирает фото + текст и не раскрывает все
  text-only режимы провайдеров;
- фактические тарифы и доступность моделей требуют live smoke-test с балансом.

## После завершения

### Фактически сделано

- `Nano Banana 2` и `Nano Banana Pro` читают только
  `GRS_NANO_BANANA_*_MODEL`;
- удалён fallback `KIE_NANO_BANANA_PRO_MODEL`;
- старые `KIE_NANO_*` цены больше не читаются загрузчиком settings;
- включённый media-контур требует одновременно `KIE_API_KEY` и `GRS_API_KEY`;
- `.env.example` и `.env.server.example` синхронизированы с фактическими
  Kie/GRS маршрутами и содержат явные model ID подключённых моделей;
- server preflight проверяет оба провайдера и обязательные media routes;
- server preflight запрещает `ollama` как text, vision или VL cascade provider;
- облачный Kie Qwen ID отделён в тестах от локального Qwen/Ollama runtime;
- `docs/AI_VISION.md` переписан под облачный VL-контур, Ollama помечен
  `legacy/deprecated`;
- добавлены тесты обязательного GRS key и запрета Ollama.

### Миграции и совместимость

Миграции PostgreSQL не требуются. Runtime-типы и старые Ollama-адаптеры пока не
удаляются: они сохраняются для чтения прежних конфигураций, старых queued payload
и последующей контролируемой миграции. Production server preflight блокирует их
использование. Внутренние legacy-поля `KiePricing.nano_1k_2k_usd` и
`nano_4k_usd` остаются в dataclass, но загрузчик больше не связывает их с env.

### Проверки

- type check: успешно на первом запуске CI;
- docker build: успешно на первом запуске CI;
- unit tests: первый запуск выявил устаревшие фикстуры без `GRS_API_KEY` и слишком
  широкий запрет слова `qwen`; фикстуры и контракт уточнены;
- project notes contract: первый запуск выявил неполный worklog; запись приведена
  к обязательной структуре;
- повторный CI запускается новым commit ветки.

### PR и commit

- PR: `#477`
- Ветка: `agent/grs-only-media-config`
- Первый функциональный head: `04481c27012ed8652d6e7304d7cd1b7a27c1dc40`
- CI-fix commits добавляются поверх него.

### Незавершённое

- дождаться зелёного повторного CI;
- выполнить live smoke-test Banana 2 и Pro через GRS AI;
- проверить реальные provider credits и обновить budget estimates при
  расхождении;
- отдельной задачей переработать model-specific input modes в Ауф;
- отдельной миграцией удалить legacy Ollama runtime после проверки queued data.

### Следующий шаг

После зелёного CI перевести PR из draft в ready, слить в `main`, затем выполнить
server preflight и по одной дешёвой тестовой генерации Nano Banana 2/Pro через
GRS AI. Следующей задачей добавить text-only/photo-only/photo+text режимы по
возможностям конкретных моделей, а не продолжать заставлять все модели жить в
одинаковом FSM.
