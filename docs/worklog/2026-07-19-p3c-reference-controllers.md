# Сессия: перенос reference presentation controllers

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-reference-controllers`
- Линия/фаза: Velvet Archive, P3C
- Статус: `завершено`
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
- AI callback coverage теперь сканирует как legacy handlers, так и canonical presentation controllers;
- добавлены проверки identity, alias size, canonical router ownership и порядка imports;
- layout inventory обновлён до 44 implementations и 24 aliases.

### Миграции и совместимость

Миграции PostgreSQL не требуются и не изменялись. Команды `/ref`, `/refs`, `/refadd`, `/refdel`, `/compare_ref`, callback prefixes, тексты, AI lifecycle и repository calls сохранены. Старые import paths и monkeypatch targets продолжают работать.

### Проверки

- первый tests run #970 выявил три устаревших ожидания `test_ai_menu_callback_coverage.py`, которые сканировали только `velvet_bot/handlers`;
- контракт обновлён для canonical presentation controllers;
- tests #971: 857 тестов, success;
- docker build #507: success;
- project notes contract #369: success;
- architecture inventory: root imports 0, active routers 55, duplicates 0, implementations 44, aliases 24.

### PR и commit

- PR: #198 `Move reference controllers into presentation`;
- основной move commit: `7998a009adf009aa16eb316e73746946282dea25`;
- inventory/worklog commit: `3a4921473bd9749bc45dd8d7f28f9a94fb5d1248`;
- callback coverage fix: `bd655bf7d5715c5b6a2da979dfbdf754216f6c40`;
- ветка: `agent/p3c-reference-controllers`.

### Незавершённое

Внутренние imports между частью reference controllers всё ещё проходят через совместимые legacy aliases. Это контролируемый остаток P3D и не влияет на runtime semantics. Он будет очищаться только отдельным срезом после стабилизации physical moves.

### Следующий шаг

Слить PR #198 после зелёного финального CI. Затем продолжить отдельным P3C-срезом переноса archive/public archive presentation controllers.
