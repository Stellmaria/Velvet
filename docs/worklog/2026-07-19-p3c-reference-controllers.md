# Сессия: перенос reference presentation controllers

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-reference-controllers`
- Линия/фаза: Velvet Archive, P3C
- Статус: `частично`
- Ветка: `agent/p3c-reference-controllers`
- Базовый commit: `c26970d8cc6fccbc1602e48a203897ae00df7b2d`

## Перед началом

### Цель

Перенести связный набор активных Telegram-контроллеров референсов из legacy `velvet_bot/handlers` в канонический presentation-пакет без изменения команд, callback contracts, порядка регистрации и поведения AI-сравнения.

### Исходный контекст

После слияния PR #197 архитектурный inventory содержал 50 активных legacy implementations и 18 временных module aliases. Следующим измеримым P3C-срезом были назначены шесть reference controllers: просмотр, альбомы, управление, документы и два сценария сравнения с референсом.

### Планируемый объём

- перенести шесть reference implementations в `velvet_bot/presentation/telegram/routers/references/`;
- заменить старые handler-файлы module aliases того же объекта;
- перевести active router bundle на canonical imports при неизменном порядке;
- обновить Phase 9 source-path contract, P3 router inventory и layout inventory;
- добавить regression-тесты module identity и canonical ownership;
- не менять AI clients, PostgreSQL repositories, команды, callbacks и тексты.

### Критерии готовности

- canonical reference modules содержат реальные router implementations;
- legacy paths возвращают те же module objects и не содержат decorators;
- bundle сохраняет все 32 router registrations в прежнем порядке;
- active legacy implementations уменьшаются с 50 до 44;
- aliases увеличиваются с 18 до 24;
- полный tests, Docker build и project notes contract зелёные.

### Риски и ограничения

Reference controllers импортируют друг друга и character presentation через исторические пути. В этом срезе такие внутренние imports сохраняются через module aliases, чтобы физический перенос не смешивался с cleanup import graph и не создавал дополнительный риск циклической загрузки.

## После завершения

### Фактически сделано

- шесть reference controllers перенесены в canonical package `presentation/telegram/routers/references`;
- старые paths заменены короткими aliases через `importlib` и `sys.modules`;
- `archive_and_public` использует canonical reference imports без изменения регистрационного порядка;
- Phase 9 и P3 architecture contracts переведены на canonical paths;
- добавлены проверки identity, alias size, canonical router ownership и порядка imports;
- layout inventory обновлён до 44 implementations и 24 aliases.

### Миграции и совместимость

Миграции PostgreSQL не требуются и не изменялись. Команды `/ref`, `/refs`, `/refadd`, `/refdel`, `/compare_ref`, callback prefixes, тексты, AI lifecycle и repository calls сохранены. Старые import paths и monkeypatch targets продолжают работать.

### Проверки

Статическая сверка tree diff и import order выполнена. Обязательные GitHub Actions будут зафиксированы после открытия PR.

### PR и commit

- основной move commit: `7998a009adf009aa16eb316e73746946282dea25`;
- ветка: `agent/p3c-reference-controllers`;
- PR: будет создан после фиксации worklog и inventory.

### Незавершённое

До завершения среза требуется получить зелёные tests, Docker build и project notes contract, затем обновить эту запись финальными номерами прогонов. Внутренние imports через legacy aliases остаются контролируемой совместимостью и не очищаются в этом PR.

### Следующий шаг

После зелёного CI слить reference PR и продолжить отдельным P3C-срезом переноса archive/public archive presentation controllers.
