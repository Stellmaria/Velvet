# 2026-07-30 — Ауф editing contract

- Дата: 2026-07-30
- ID: `auf-editing-contract`
- Issue: #419
- Линия/фаза: P3 shared helper family migration
- Статус: `завершено`
- Ветка: `agent/shared-helper-auf-edit-family`
- Базовый commit: `06640c58d137596c3f2e4b8e15bbd1d4b7fc8241`

## Перед началом

### Цель

Убрать внешние private `_edit_or_answer` contracts из Ауф routers и runtime installers,
сохранив callback acknowledgement, media fallback и финальное преобразование текстов
через GRS branding hook.

### Исходный контекст

Исходный feature-срез PR #469 был собран от commit
`c553dcbe61ae6225f83e7390cdd81b650cdb1208`, после чего `main` ушёл вперёд на 25
коммитов. Среди новых изменений находились исправление рекурсии GRS action handler,
переименование пользовательской валюты и подключение платной очереди. Прямое слияние
устаревшей ветки создавало риск отката этих исправлений и не проходило project notes
contract из-за отсутствующего worklog.

### Планируемый объём

- добавить общий callback edit-or-answer helper в shared Telegram package;
- добавить публичный Ауф editing adapter и text-transform hook;
- перевести Ауф photo/GRS routers и installers с private `_edit_or_answer`;
- сохранить current-main fallback на `_handle_base_auf_action` в GRS router;
- добавить async и AST regression tests;
- обновить shared contract и Telegram navigation inventories;
- перенести срез поверх актуального `main` без постороннего accumulated diff.

### Критерии готовности

- внешние consumers больше не импортируют и не переназначают private `_edit_or_answer`;
- text callback редактируется, media callback получает новую текстовую карточку;
- `message is not modified` не создаёт дубликат, прочий Telegram edit rejection даёт fallback;
- callback подтверждается ровно один раз;
- GRS text sanitization продолжает работать через публичный transformer hook;
- исправление рекурсивного fallback из PR #470 сохранено;
- branch не отстаёт от `main`, обязательный CI проходит.

### Риски и ограничения

Срез не меняет callback payloads, FSM, биллинг, provider routing, модельный каталог или
пользовательские тексты. Generated JSON остаётся крупной частью diff, поскольку repository
versionирует полный package-wide inventory. Другие helper families из #419 намеренно не
мигрируются в этом PR, иначе очередной «небольшой рефакторинг» снова превратился бы в
археологический пласт на несколько эпох.

## После завершения

### Фактически сделано

- добавлен `edit_or_answer_callback_text` в `presentation.telegram.shared.editing`;
- helper экспортирован через public shared package;
- добавлен `presentation.telegram.auf_editing` с `edit_or_answer_auf_callback` и
  `install_auf_text_transformer`;
- `workspace_auf`, photo routers, photo UI installer и GRS resilience переведены на public API;
- `workspace_auf_grs` вручную сведен с current `main`: публичный editing contract подключён,
  а fallback продолжает делегировать `_handle_base_auf_action` без рекурсии;
- добавлен `tests/test_auf_editing_contract.py` с async behavior и AST boundary checks;
- shared contract inventory обновлён, private cross-module debt уменьшен;
- Telegram navigation inventory обновлён с учётом нового production Python module;
- feature branch пересобран непосредственно поверх актуального `main` без 25-коммитного хвоста.

### Миграции и совместимость

Миграций базы данных и persistent identifiers нет. Callback data, FSM states, клавиатуры,
модельные alias, wallet settlement, charging, result delivery и provider task contracts не
изменены. Сохранены изменения PR #470, #471 и #472, появившиеся после исходной базы PR.

### Проверки

На исходном feature-срезе успешно проходили unit tests, type check и Docker build. После
переноса на current `main` подтверждены:

- branch ahead of `main` и behind by 0;
- type check — success;
- Docker build — success;
- project notes contract повторно запущен после приведения worklog к canonical schema;
- full unit tests запущены GitHub Actions;
- generated shared/navigation inventories входят в regression suite.

### PR и commit

- PR: #469;
- ветка: `agent/shared-helper-auf-edit-family`;
- current reviewed head до исправления worklog: `e128b01071f081eeff6393fda544bcf41de70eb6`;
- итоговый squash merge commit будет зафиксирован GitHub после зелёного CI.

### Незавершённое

- дождаться повторного полного CI после обновления worklog;
- снять draft и слить PR #469 при зелёных обязательных checks;
- umbrella issue #419 не закрывать, поскольку в ней остаются другие helper families.

### Следующий шаг

После merge использовать обновлённый inventory как baseline следующего отдельного среза
#419. Не объединять его с P0 composition/delivery работой #455 и #457: архитектурный долг
лучше устранять измеримыми PR, а не одним героическим коммитом, который потом никто не
решится трогать.
