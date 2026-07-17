# Сессия: интеграция и hardening Krita watermark bridge

- Дата: 2026-07-17
- ID: `2026-07-17-krita-watermark-hardening`
- Линия/фаза: стабилизация media/publication, отдельный Krita integration hardening
- Статус: частично
- Ветка: `agent/krita-watermark-hardening`
- Базовый commit: интеграционная основа `7543ed7807a41e38d47ca91d854bbb916547927c`, созданная поверх актуального `main` `9127a423184c48b753da28cb15d71ec132ec3e88`

## Перед началом

### Цель

Создать чистый интеграционный срез Krita watermark bridge от актуального `main`, вручную сохранить изменения Фаз 18U–18V в общих файлах и закрыть обязательные дефекты надёжности: recovery зависших `*.processing`, повторную проверку `output_path`, атомарный approve текущей revision и запрет отмены approved job.

### Исходный контекст

Старый draft PR `#117` содержал исходную реализацию watermark bridge, но его нельзя продолжать несвязанными изменениями. Интеграционная основа `7543ed…` содержала только новые watermark-модули и не изменяла общие файлы актуального `main`: в частности, регистрация `krita-watermark` отсутствовала в `velvet_bot/app/workers.py`. Функция должна оставаться выключенной по умолчанию до живой проверки Krita на целевой Windows.

### Какую существующую функцию улучшает изменение

Изменение автоматизирует существующую подготовку изображений Velvet Archive к публикации: сохраняет неизменяемый source, строит preview, позволяет изменять параметры через revisions и подтверждает отдельный финальный PNG.

### Что станет проще и надёжнее

- аварийное завершение Krita или бота не оставляет revision в вечном `processing`;
- response JSON не может заставить бота открыть путь вне разрешённых output/preview каталогов;
- approve подтверждает только заблокированную текущую `ready` revision в одной транзакции;
- устаревший callback отмены не меняет approved job;
- общие файлы интегрируются поверх актуального `main`, а не заменяются старыми версиями.

### Почему это не новая предметная область

Watermark остаётся внутренним этапом уже существующего media/publication-сценария. Новые роли, аукционные сущности, валюты, ставки, колоды и независимые пользовательские механики не добавляются.

### Планируемый объём

1. Вручную интегрировать feature flag, WorkerManager, owner menu и handlers с актуальным `main`.
2. Добавить recovery stale processing requests без дублей.
3. Добавить строгую валидацию response output path внутри разрешённых каталогов.
4. Сделать repository approve транзакционным и идемпотентным.
5. Добавить status guard отмены и спокойный доменный результат для stale callback.
6. Расширить unit и PostgreSQL integration tests.
7. Обновить документацию, changelog и эту запись фактическими результатами.

### Критерии готовности

- feature flag по умолчанию равен `false`;
- watermark worker регистрируется только при включённом флаге;
- stale `*.processing` восстанавливается, завершается готовым response либо переводится в контролируемую ошибку;
- output вне `outputs/` или `previews/`, traversal, UNC и выход через symlink/reparse point отклоняются до чтения файла;
- approve блокирует job и текущую revision через `FOR UPDATE`, принимает только `ready` и сохраняет путь именно этой revision;
- повторный approve возвращает ясный доменный ответ;
- cancel изменяет только незавершённые статусы и не меняет approved job;
- handler не содержит SQL, callbacks подтверждаются рано, callback data остаётся в лимите Telegram;
- migration применяется на пустой PostgreSQL 16;
- полный CI, Docker build и restore drill зелёные либо незапущенные проверки честно записаны как остаток;
- живая Windows-проверка не объявляется выполненной без фактического запуска.

### Риски и ограничения

- текущая среда не предоставляет живой Krita Python API и Windows filesystem semantics;
- UNC/reparse point полностью подтверждаются только на Windows, поэтому код и unit-контракт не заменяют живую проверку;
- старые применённые миграции не редактируются;
- private pool baseline Фазы 18 не меняется;
- Krita hardening не смешивается с Фазой 18W.

## После завершения

### Фактически сделано

- создана отдельная ветка `agent/krita-watermark-hardening` от интеграционной основы, которая непосредственно основана на актуальном `main`;
- общие файлы `.env.example`, `CHANGELOG.md`, integrity tests, `WorkerManager`, owner router и owner menu слиты вручную без замены актуального кода Фаз 18U–18V;
- `krita-watermark` зарегистрирован в штатном `WorkerManager` только при `KRITA_WATERMARK_ENABLED=true`;
- значение feature flag по умолчанию оставлено `false`, все stale callbacks кроме возврата в меню также блокируются при выключенной функции;
- каждый Telegram source сохраняется под уникальным именем внутри `sources/` и не перезаписывается повторным запуском;
- `claim_pending()` забирает только текущую revision активного job, исторические pending revisions не создают лишнюю очередь;
- добавлен recovery stale `*.processing`: готовый response имеет приоритет, существующий request не дублируется, свежий processing ожидается, stale processing атомарно возвращается в очередь;
- отсутствие request, processing и response после порога переводит revision в контролируемую ошибку и записывается в журнал;
- response и final `output_path` повторно нормализуются и сверяются с ожидаемым путём; traversal, UNC, выход из разрешённых каталогов и symlink escape отклоняются до чтения или отправки файла;
- approve выполняется в одной PostgreSQL-транзакции с `FOR UPDATE OF j, r`, подтверждает только текущую ready revision и сохраняет её output;
- approved job нельзя отменить старым callback; повторные approve/cancel получают ясные доменные ответы без изменения результата;
- callbacks подтверждаются до длительной работы, SQL в handler не добавлен;
- расширены unit-тесты bridge path boundary/recovery и PostgreSQL integration tests transitions/locking guards;
- обновлена эксплуатационная документация с полным Windows checklist из 15 пунктов.

### Миграции и совместимость

Используется новая миграция `900_krita_watermark_bridge.sql` с таблицами `watermark_jobs` и `watermark_revisions`. Старые применённые миграции не редактировались. Repository использует публичный `Database.acquire()`. Private pool baseline Фазы 18 остаётся `100 / 25`; Фаза 18W в этот PR не включена. При выключенном feature flag существующие worker и пользовательские сценарии продолжают работать без Krita.

### Проверки

- локальный `python -m py_compile` успешно выполнен для изменённых repository, service, bridge, handler и новых тестовых модулей;
- добавлены unit-тесты request protocol, callback length, UNC/traversal/symlink boundary, exact output match и stale processing recovery;
- добавлены PostgreSQL integration tests current revision claim, stale ready approve rejection, repeat approve, approved cancel guard и повторной отмены;
- первый запуск `project notes contract #83` обнаружил незаполненный финальный блок этой записи; структура и обязательное поле `Базовый commit` исправлены в текущем commit;
- tests, Docker build и backup restore drill запущены GitHub Actions для PR #120; их окончательные результаты фиксируются в PR после повторного запуска на финальном head;
- живая Windows/Krita проверка не выполнялась и не объявляется пройденной.

### PR и commit

- новый чистый draft PR: `#120` — `Krita watermark bridge: чистая интеграция и hardening`;
- старый draft PR `#117` закрыт как заменённый и снабжён ссылкой на `#120`;
- интеграционная основа: `7543ed7807a41e38d47ca91d854bbb916547927c`;
- последний production hardening head до финализации журнала: `814270c2cac2193e31c83248720dc369e3998ea4`.

### Незавершённое

- дождаться зелёного project notes contract, полного tests workflow с PostgreSQL 16, Docker build и backup restore drill на финальном head;
- выполнить живую Windows-проверку реального Krita Python API, общего bridge-root, revisions, recovery, path rejection и stale callback;
- до живой проверки не менять `KRITA_WATERMARK_ENABLED=false` и не переводить PR из draft в production-ready.

### Следующий шаг

После зелёного CI провести 15-пунктовую Windows-проверку из `docs/krita_watermark.md`. Только после её фактического результата можно завершить Krita integration PR. Следующий независимый архитектурный срез после Krita — Фаза 18W для `velvet_bot/ai_vision.py`, отдельная ветка, worklog и PR.
