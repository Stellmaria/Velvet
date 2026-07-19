# Сессия: перенос publication presentation controllers

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-publication-controllers`
- Линия/фаза: Velvet Archive, P3C
- Статус: `завершено`
- Ветка: `agent/p3c-publication-controllers`
- Базовый commit: `8a91f196e54ed92cbfe91173b15f4b01bc20b2fc`

## Перед началом

### Цель

Перенести Telegram-контроллеры центра публикаций из legacy `velvet_bot/handlers` в канонический presentation-пакет без изменения команд, callback contracts, расписания, проверки постов и порядка регистрации перед catch-all архивом.

### Исходный контекст

После слияния PR #199 архитектурный inventory содержал 37 активных legacy implementations и 31 временный module alias. Следующим P3C-срезом были назначены publication controllers.

### Планируемый объём

- перенести `publication_center` и `publication_center_safe` в `presentation/telegram/routers/publication/`;
- заменить старые handler-файлы module aliases того же объекта;
- перевести safe-router на прямой canonical import центра публикаций;
- перевести `archive_and_public` bundle на canonical safe-router;
- сохранить регистрацию publication router перед catch-all archive router;
- обновить Phase 13, P3 router inventory и layout inventory;
- добавить regression-тесты module identity и canonical ownership;
- не менять команды, callback data, publication services, timezone parsing и тексты.

### Критерии готовности

- canonical publication modules содержат реальные implementations;
- legacy paths возвращают те же module objects и не содержат decorators;
- команды `/publish`, `/publishing`, `/publications`, `/checkpost` сохранены;
- callback prefix `pubq` и reply markers сохранены;
- active legacy implementations уменьшаются с 37 до 35;
- aliases увеличиваются с 31 до 33;
- полный tests, Docker build и project notes contract зелёные.

### Риски и ограничения

`publication_center_safe` специально ограничивает reply handler marker-фильтром и должен оставаться перед catch-all обработчиком архивной темы. Физический перенос не смешивается с изменением workflow, timezone parsing, очереди публикаций или application services.

## После завершения

### Фактически сделано

- `publication_center` перенесён в `presentation/telegram/routers/publication/center.py`;
- `publication_center_safe` перенесён в `presentation/telegram/routers/publication/safe.py`;
- safe-router использует canonical center import;
- старые paths заменены aliases через `importlib` и `sys.modules`;
- `archive_and_public` использует canonical safe-router в прежней позиции;
- Phase 13 и P3 architecture contracts переведены на canonical paths;
- добавлены проверки identity, alias size, canonical ownership и порядка регистрации;
- layout inventory обновлён до 35 implementations и 33 aliases.

### Миграции и совместимость

Миграции PostgreSQL не требуются и не изменялись. Команды `/publish`, `/publishing`, `/publications`, `/checkpost`, callback prefix `pubq`, reply markers `PUBLICATION_SCHEDULE` и `PUBLICATION_TEXT`, timezone `Europe/Berlin`, публикация сейчас, расписание, повторная проверка и редактирование текста сохранены. Старые import paths и monkeypatch targets продолжают работать.

### Проверки

- tests #977: 867 тестов, success;
- docker build #513: success;
- project notes contract #373: success;
- architecture inventory: root imports 0, active routers 55, archive/public bundle 32, duplicates 0, implementations 35, aliases 33;
- отдельные исправления после первого CI не потребовались.

### PR и commit

- PR: #200 `Move publication controllers into presentation`;
- ветка: `agent/p3c-publication-controllers`;
- canonical modules созданы точным переносом исходных blob-объектов с отдельной заменой import boundary;
- финальная документационная фиксация выполнена после зелёного CI.

### Незавершённое

Внешние imports legacy publication paths остаются совместимыми aliases. Это контролируемый остаток P3D и не влияет на runtime semantics. Очистка выполняется отдельным срезом после завершения физических переносов.

### Следующий шаг

Слить PR #200 после зелёного финального CI. Затем продолжить отдельным P3C-срезом переноса analytics presentation controllers.
