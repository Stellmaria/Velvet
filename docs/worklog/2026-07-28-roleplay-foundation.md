# Сессия: изолированный фундамент ролевого режима

- Дата: 2026-07-28
- ID: `2026-07-28-roleplay-foundation`
- Линия/фаза: новая линия F / RP1 Foundation
- Статус: `частично`
- Ветка: `agent/roleplay-foundation`
- Базовый commit: `ff70ad97133ee6508391082509a195af17ef8898`

## Перед началом

### Цель

Создать отдельный фундамент локального ролевого режима поверх Ollama: собственные
карточки персонажей, сессии, сообщения и память, не связанные с архивными
`characters`, медиа, историями, референсами или публикациями.

### Решение владельца и изменение предметной границы

Владелец проекта 28 июля 2026 года явно распорядился начать разработку ролевого
режима и отдельно запретил использовать архивные карточки персонажей. Это является
осознанным расширением предметной области после ранее зафиксированного режима
стабилизации, а не улучшением существующей архивной функции.

Работа поэтому оформляется отдельной линией F и изолированным доменом `roleplay`.
Существующие таблицы `characters`, `character_media`, story/reference/archive
repositories и Telegram-сценарии архива не изменяются и не используются как
источник RP-профилей.

### Исходный контекст

Velvet уже имеет PostgreSQL, Telegram presentation, owner access, Supervisor и
локальный Ollama runtime. При этом полноценного RP-движка нет: отсутствуют
долговечные RP-профили, сессии, сообщения, память, отношения, сборщик контекста и
отдельная текстовая AI-конфигурация.

Целевое окружение: MSI Katana, 16 ГБ RAM, RTX 3050 Ti 4 ГБ. Начальный бюджет
контекста должен быть консервативным и настраиваемым, по умолчанию 8192 токена.

### Планируемый объём RP1

- добавить отдельную миграцию с таблицами `rp_characters`, `rp_sessions`,
  `rp_session_characters`, `rp_messages` и `rp_memories`;
- создать transport-neutral domain models, repository и service внутри
  `velvet_bot/domains/roleplay`;
- добавить отдельные настройки `RP_*`, не переиспользующие `AI_VISION_MODEL`;
- добавить Ollama text client для roleplay chat completion;
- ввести детерминированный контекстный бюджет и базовый prompt contract;
- покрыть валидацию, persistence contracts и клиент unit-тестами;
- обновить `docs/project_memory.md`, `docs/development_status.md`, `.env.example`
  и предметную документацию;
- открыть отдельный draft PR без смешивания с архивными или vision-изменениями.

### Критерии готовности RP1

- миграция создаёт только таблицы с префиксом `rp_` и не содержит FK на архивные
  таблицы;
- RP-персонаж хранит отдельные блоки внешности, характера, речи, биографии,
  правил поведения и примеров реплик;
- RP-сессия сохраняет участников, сообщения, сводку, сцену и долговременные факты;
- настройки модели, контекста, sampling и timeout читаются из `RP_*`;
- Ollama client формирует запрос с `num_ctx`, ограничением ответа и sampling;
- unit-тесты подтверждают нормализацию, лимиты и отсутствие архивной связанности;
- полный CI запущен на head ветки;
- живая Ollama/Telegram проверка остаётся отдельным обязательством до merge.

### Риски и ограничения

- 16 ГБ RAM ограничивают практический контекст и размер модели;
- слишком подробные карточки могут вытеснить недавний диалог из окна контекста;
- автоматическая память не должна переписывать канонические факты без
  подтверждения владельца;
- adult RP требует явной проверки совершеннолетия всех участников на уровне
  создаваемых карточек и сессии;
- первая фаза не обещает готовый Telegram-отыгрыш: она создаёт проверяемый
  persistence и AI foundation.

### Архитектурные границы

- SQL находится только в migration и domain repository;
- Telegram handlers не получают SQL;
- архивные repositories и таблицы не импортируются доменом `roleplay`;
- один process-wide local AI lock остаётся общей защитой ресурсов ноутбука;
- каноническая память отделяется от изменяемого состояния сцены;
- пользовательский интерфейс будет добавлен следующим отдельным срезом после
  проверки foundation.

## После завершения

### Фактически сделано

- создан отдельный домен `velvet_bot.domains.roleplay`;
- добавлены RP models, validation service, repository и context builder;
- карточка персонажа хранит внешность, характер, речь, биографию, правила,
  канонические факты, примеры реплик и служебные заметки;
- создание карточки требует явного `adult_confirmed`;
- сессии сохраняют модель, сценарий, лор, сводку, состояние сцены и generation
  settings;
- сообщения получают атомарный sequence number внутри сессии;
- память разделена на `canonical`, `episodic`, `relationship` и `scene`;
- контекст собирается из карточек, сценария, лора, сводки, состояния сцены,
  памяти, последних сообщений и нового хода пользователя;
- слишком большой постоянный контекст отклоняется до запроса Ollama с понятной
  ошибкой вместо молчаливого вытеснения всей переписки;
- добавлен независимый `RoleplaySettings` и `load_roleplay_settings()`;
- добавлен `OllamaRoleplayClient` с `num_ctx`, `num_predict`, temperature, top_p,
  min_p, repeat penalty и keep-alive;
- обновлены `.env.example`, `docs/ROLEPLAY.md`, project memory, development status
  и stabilization policy;
- создан draft PR #332.

### Изменённые модули и контракты

- `velvet_bot/domains/roleplay/models.py`;
- `velvet_bot/domains/roleplay/service.py`;
- `velvet_bot/domains/roleplay/context.py`;
- `velvet_bot/domains/roleplay/repository.py`;
- `velvet_bot/domains/roleplay/__init__.py`;
- `velvet_bot/core/config/roleplay.py`;
- `velvet_bot/services/roleplay_ollama.py`;
- `tests/test_roleplay_foundation.py`;
- `tests/test_roleplay_repository.py`.

### Миграции и совместимость

Добавлена миграция `916_roleplay_foundation.sql`. Первоначальный номер 915 был
заменён после CI, поскольку он уже занят применяемой workspace-миграцией.

Миграция создаёт только:

- `rp_characters`;
- `rp_sessions`;
- `rp_session_characters`;
- `rp_messages`;
- `rp_memories`.

Foreign key на архивные `characters`, media, story или reference tables отсутствует.
Архивная карточка с совпадающим именем не появляется в RP repository и наоборот.

### Проверки

На head `d3717a3e2ecfe665bc129d5fe9e4d5319f2b5a42`:

- project notes contract: success;
- type check: success;
- Docker build: success;
- backup restore drill: success;
- полный tests workflow с PostgreSQL integration tests: success;
- repository layout inventory обновлён до 36 modules, из них 35 domain и 1
  infrastructure;
- Telegram navigation inventory обновлён до 463 Python files без новых buttons и
  violations.

Локально до CI выполнены syntax checks и целевые unit tests. Живой запрос к Ollama
на целевом MSI Katana не выполнялся и не считается подтверждённым.

### PR и commit

Draft PR #332: `Add isolated roleplay foundation`.

Проверенный CI head: `d3717a3e2ecfe665bc129d5fe9e4d5319f2b5a42`.

### Незавершённое

- установить и проверить выбранную RP-модель через Ollama на MSI Katana;
- выполнить живой запрос с 8192 context и измерить скорость/память;
- добавить отдельный Telegram-редактор RP-персонажей;
- добавить запуск и продолжение RP-сессии;
- добавить автоматическую сводку и подтверждаемое извлечение памяти;
- добавить управление отношениями, откат и экспорт.

### Следующий шаг

Начать RP2 отдельным срезом: Telegram-редактор RP-персонажей, который создаёт и
изменяет только `rp_characters` и не обращается к архиву.
