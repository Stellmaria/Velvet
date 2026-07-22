# Сессия: выравнивание media-контракта личного пространства

- Дата: 23 июля 2026 года
- ID: `2026-07-23-workspace-media-contract-alignment`
- Линия/фаза: Velvet Archive / stabilization — personal workspace media contract alignment
- Статус: `частично`
- Ветка: `codex/workspace-media-controls`
- Базовый commit: `b3bcbad`

## Перед началом

### Цель

Закрыть расхождения между первым срезом personal workspace media controls и
утверждённым пользовательским контрактом: полные кнопки пакетной загрузки, два
независимых измерения download policy, понятные места хранения оригинала и
watermark-копии, явное возвращение материала после доработки и корректное
разделение личной отметки владельца от публичной статистики.

### Исходный контекст

Commit `a9dfd1c` добавил пакетную save-session, owner media card, workspace +18,
четыре совмещённых режима скачивания и tenant-aware watermark/public access.
После сверки с финальной спецификацией обнаружены конкретные расхождения:
batch UI не содержит отдельные действия открытия карточки и отмены режима;
download audience и выдаваемая версия объединены в одно поле; rework скрывается
через активный status, но после закрытия автоматически возвращается в public
visibility; owner-like приватного архива использует публичную таблицу; storage
destinations и результат быстрого watermark требуют проверки и явного UX.

### Планируемый объём

- добавить в активную save-session четыре явных действия: завершить, открыть
  карточку, сменить персонажа и отменить режим без удаления сохранённого;
- разделить download policy на audience (`disabled`, `all`, `subscribers`) и
  variant (`watermark`, `original`) с безопасной миграцией существующих данных;
- показать оба параметра отдельными группами кнопок и валидировать channel/
  watermark prerequisites;
- определить существующие workspace destinations для оригинала и delivery-copy,
  не дублируя Telegram storage без необходимости, и вывести это в guide;
- сделать manual rework сохраняющим явный public hold до решения владельца;
- отделить личную owner-like приватного материала от публичных likes;
- связать fast-watermark с существующим revision/approve UI и добавить понятные
  переходы к переделке и настройке шаблона там, где их не хватает;
- обновить tests, generated inventories и документацию, затем создать commits.

### Критерии готовности

- все четыре batch-кнопки имеют рабочий callback и понятный результат;
- читательская download-кнопка вычисляется как audience × variant, default —
  disabled, подписка проверяется в выбранном workspace channel;
- владелец всегда получает сохранённый original source, watermark delivery не
  перезаписывает его;
- rework item не возвращается публично автоматически после завершения;
- private owner-like не увеличивает публичный like count;
- быстрый watermark ведёт через существующие revisions к явному подтверждению,
  переделке и настройке asset;
- targeted и полный test suite, navigation inventory, project notes contract и
  diff check проходят.

### Риски и ограничения

Нельзя редактировать уже применённые миграции; новые поля требуют новой
миграции и совместимого mapping старого `downloads_mode`. Telegram file_id не
является физическим каталогом: destination описывает канал/тему доставки, а не
копирование байтов без операции отправки. Membership lookup требует прав бота в
канале. Живой Krita/Telegram/PostgreSQL smoke-test остаётся отдельным
эксплуатационным обязательством.

### Обоснование стабилизации

Срез не добавляет новую предметную область. Он делает уже существующие save,
public archive, watermark и rework сценарии однозначными, безопасными и
проверяемыми, уменьшает риск ошибочной публичной выдачи и сохраняет границы
domain/repository/presentation без SQL в handlers.

## После завершения

### Фактически сделано

- пакетная загрузка личного пространства получила четыре постоянных действия:
  завершить, открыть карточку без закрытия сессии, выбрать другого персонажа и
  отменить режим без удаления уже сохранённых материалов;
- политика скачивания разделена на независимые audience и variant; безопасное
  значение по умолчанию запрещает читательское скачивание;
- для subscriber-only выдачи добавлена отдельная привязка download-канала, а
  для одобренных watermark-копий — отдельный channel/topic destination;
- оригинал продолжает храниться через существующий characters destination и
  персональную тему персонажа; подтверждённая watermark-копия отправляется в
  настроенный watermarks destination и не заменяет source;
- приватный или скрытый owner-like стал личной отметкой и не меняет публичный
  счётчик; публичный видимый материал сохраняет обычную like-механику;
- отправка на доработку сразу снимает public-флаг, повторный active request не
  возвращает видимость, а после завершения требуется явная команда владельца;
- fast-watermark проверяет template и storage destination, а review предлагает
  использовать результат, переделать его или открыть настройку шаблона;
- owner settings и guide объясняют prerequisites скачивания, +18, оригиналов и
  watermark storage; требования продукта и generated inventories обновлены.

### Изменённые модули и контракты

- `domains/workspaces`: новые download audience/variant, destinations,
  owner-media preferences и service/repository contracts;
- `domains/public_archive` и `workspace_public_access`: вычисление разрешения
  как audience × variant с membership-проверкой выбранного download-канала;
- `domains/media_rework`: active-state lookup и постоянный public hold;
- Telegram archive/workspace/public/watermark routers: batch callbacks,
  настройки, подсказки, owner controls и destination-aware approval storage;
- repository inventory: 34 модуля, из них 33 domain и 1 infrastructure.

### Миграции и совместимость

- добавлена только новая миграция `913_workspace_media_contract_alignment.sql`;
- legacy `downloads_mode` переносится в новые поля и продолжает вычисляться для
  старых consumers;
- constraints destinations/channels расширены для `adult`, `download`,
  `downloads` и `watermarks` без редактирования применённых миграций;
- создана tenant-scoped таблица личных owner favorites;
- до применения миграции на production обязателен штатный backup/migration run.

### Проверки

- `python -m unittest -q tests.test_workspace_media_controls ...
  tests.test_telegram_navigation_inventory` — 57 tests, OK, skipped=1;
- `python -X utf8 -m unittest discover -s tests -q` — 1213 tests, OK,
  skipped=83;
- `python -m compileall -q velvet_bot tests` — OK;
- `telegram_navigation_inventory.py --check` — 423 files, 738 inline buttons,
  0 violations;
- `inventory_repository_layout.py --check --label
  p3e-repository-layout-complete` — OK;
- `git diff --check` — OK (только информационные Windows LF/CRLF warnings);
- PostgreSQL integration test пропущен без `TEST_DATABASE_URL`; `mypy` в
  активном `.venv` не установлен и остаётся CI-проверкой.

### PR и commit

- PR не создавался;
- implementation commit: `8acc4b5` (`Align personal workspace media contracts`);
- итоговый documentation commit фиксирует эту ссылку и чистое состояние ветки.

### Незавершённое

- не выполнен живой smoke-test с реальным Telegram bot/channel membership,
  PostgreSQL migration и Krita watermark worker;
- ветка не отправлялась в remote и не сливалась с `main`;
- поэтому статус сессии остаётся `частично`, несмотря на зелёный локальный suite.

### Следующий шаг

После применения миграции на staging пройти owner flow: настроить characters,
download и watermarks destinations, пакетно загрузить альбом, проверить четыре
выхода сессии, public/private like, все четыре сочетания download policy,
subscriber denial/success, +18, rework hold и approve/retry fast-watermark.
