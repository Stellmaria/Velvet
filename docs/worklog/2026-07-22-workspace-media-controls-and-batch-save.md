# Сессия: пакетное сохранение и управление медиа личного пространства

- Дата: 22 июля 2026 года
- ID: `2026-07-22-workspace-media-controls-and-batch-save`
- Линия/фаза: Velvet Archive / stabilization — workspace media UX and access policy
- Статус: `частично`
- Ветка: `codex/workspace-media-controls`
- Базовый commit: `4956432`

## Перед началом

### Цель

Сделать существующий сценарий сохранения медиа в личный архив пакетным и явно завершаемым, а карточку медиа владельца и публичного читателя привести к понятной матрице действий: лайк, подписка, управляемое скачивание, watermark, доработка, публичность, +18 и blur.

### Исходный контекст

Кнопка «Сохранить» запускает историческую one-shot `SaveUploadSessions`: после выбора персонажа принимается только один файл. Основной Velvet уже содержит доменные операции лайков, подписок, скачивания, watermark, очереди доработки, `is_public`, `requires_adult_channel` и blur, но personal workspace UI не предоставляет владельцу полный безопасный контур настройки и не формулирует читателю фактические ограничения. Публичная выдача сейчас намеренно скрывает +18 и image-документы больше 20 МБ вместо управляемого доступа.

### Планируемый объём

- инвентаризировать и переиспользовать существующие media/public/watermark/rework contracts;
- перевести save-session из one-shot в ограниченную TTL пакетную сессию с кнопками «Завершить», «Сменить персонажа» и понятным счётчиком;
- сохранить reply `/save` и автоматический topic archive без регрессий;
- определить tenant-safe настройки скачивания (`запрещено`, `разрешено`, `по подписке`, `watermark-копия`) и +18-канала;
- дать владельцу доступ к допустимым media actions независимо от публичности, показывая настройку вместо тупика;
- оставить читателю только лайк, подписку/отписку и разрешённое политикой скачивание;
- защитить скрытые и +18 материалы, не заменять и не терять оригинал при создании watermark-копии;
- объяснить ограничение Telegram для файлов больше 20 МБ;
- добавить миграции только новыми файлами, domain/repository boundaries, кнопочные входы, tests и документацию.

### Критерии готовности

- после выбора «Сохранить» владелец может последовательно прислать несколько поддерживаемых медиа одному персонажу;
- каждое сообщение даёт результат и оставляет явные кнопки завершения/смены персонажа; `/savecancel`, `/cancel` и `/start` безопасно завершают сессию;
- альбом Telegram обрабатывается без случайного завершения после первого элемента;
- владелец видит и понимает все заявленные действия карточки, а недонастроенная операция ведёт в настройку;
- публичный читатель не получает административных callback и видит download только при выполненной политике;
- оригинал сохраняется отдельно от watermark/public delivery copy;
- скрытые материалы видны только владельцу, +18 выдаётся только после настроенной проверки доступа;
- точные regression tests, full tests, navigation inventory, project notes contract и diff check проходят.

### Риски и ограничения

Telegram media group доставляется несколькими updates и требует debounce/идемпотентности. Защита контента Telegram запрещает штатную пересылку и сохранение сообщения, но не является DRM; файлы больше лимита Bot API требуют отдельного download-delivery пути и честного предупреждения. Проверка подписки возможна только когда бот имеет право читать членство в указанном канале. Watermark-копия не должна заменять оригинал в архивной записи. Настройки обязаны быть workspace-scoped, а handlers не получают новый SQL.

### Обоснование стабилизации

Срез улучшает существующие archive save, public archive и media moderation workflows: уменьшает повторные действия, исключает зависшие one-shot состояния, делает права и последствия кнопок видимыми и переносит уже существующие возможности основного Velvet в личное пространство без новой предметной области. Проверяемость обеспечивается session/service tests, access matrix contracts, PostgreSQL integration tests и navigation inventory; границы domain/repository/presentation сохраняются.

## После завершения

### Фактически сделано

- `SaveUploadSessions` переведена с one-shot на пакетный режим: после каждого
  поддерживаемого файла сессия остаётся активной, продлевает TTL и показывает
  счётчик, кнопки завершения и смены персонажа;
- подсказки персонажа явно разделяют «Ссылка на промт», «Загрузить медиа» и
  создание новой карточки; в карточке владельца добавлена отдельная подробная
  справка по всем действиям;
- карточка владельца personal workspace получила workspace-scoped лайк,
  подписку, отправку сохранённого оригинала, быстрый watermark, очередь
  доработки, публичность, +18, blur, удаление и настройки доступа;
- для читателя сохранены только engagement-действия и download, который
  появляется после проверки выбранной владельцем политики;
- добавлены режимы скачивания `disabled`, `watermark`, `original` и
  `subscription`; режим watermark требует настроенный asset, subscription —
  подключённый публичный канал;
- onboarding поддерживает отдельное назначение `adult`, а personal +18
  проверяет членство именно в канале выбранного workspace;
- активная доработка использует существующую единую очередь и скрывает материал
  только из публичной выдачи; владелец продолжает видеть его в архиве;
- image-документы больше 20 МБ больше не исчезают из personal public archive:
  они показываются защищённым документом с предупреждением, а отдельная выдача
  файла остаётся под download policy;
- быстрый watermark передаёт workspace и snapshot личного watermark asset;
  выдача владельцу и режим original используют сохранённый source file id.

### Изменённые модули и контракты

- application: `velvet_bot/app/save_sessions.py`;
- workspace domain: models, onboarding destination `adult`, product service и
  personal character directory;
- public archive domain: download-source policy и прокидывание
  `download_access`;
- Telegram presentation: save flow, guided actions, character pickers,
  personal owner controls, public catalog/display/notification и новый helper
  `workspace_public_access.py`;
- display/lookup: oversized personal documents и предупреждение;
- contracts: новые/обновлённые unit tests, navigation inventory и P2 stability
  inventory.

### Миграции и совместимость

Добавлена только новая миграция
`migrations/912_workspace_media_access_controls.sql`: CHECK constraint
`workspace_settings.downloads_mode` расширен значением `subscription`. Миграция
`901_workspaces.sql` не редактировалась. Значения существующих строк и прежние
три режима совместимы. Структура хранения watermark не менялась: оригинал
остаётся в `source_telegram_file_id`, delivery-копия — в `telegram_file_id`.

### Проверки

- `.\.venv\Scripts\python.exe -m compileall -q velvet_bot tests` — успешно;
- `.\.venv\Scripts\python.exe -m unittest -q tests.test_workspace_media_controls tests.test_save_next_media_session tests.test_p2al_public_archive_display_fallbacks tests.test_telegram_navigation_inventory tests.test_public_repository_safety` — `31` тест, успешно;
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -q` с локальным
  `safe.directory` для subprocess Git — `1209` тестов, успешно, `83` пропущены
  по штатным условиям внешней integration-среды;
- `.\.venv\Scripts\python.exe scripts\telegram_navigation_inventory.py --root velvet_bot --check` — `422` Python-файла, `729` кнопок, `0` нарушений;
- `.\.venv\Scripts\python.exe scripts\check_project_notes.py --base-ref main` —
  `Project notes contract: OK`;
- `git diff --check` — успешно;
- bounded mypy локально не выполнен: в активной `.venv` отсутствует пакет
  `mypy`; CI устанавливает `requirements-dev.txt` отдельно.

### PR и commit

PR не создавался. Implementation commit создаётся после финальной проверки
этой записи; его hash будет добавлен отдельным documentation commit.

### Незавершённое

Не выполнены живые проверки, которые невозможно достоверно эмулировать unit
tests: применение миграции к production PostgreSQL, Telegram media-group на
реальном боте, membership lookup в личных public/+18 каналах и полный цикл
Krita bridge с личным watermark asset. Поэтому статус остаётся `частично`.

### Следующий шаг

Опубликовать ветку, пройти CI и staging smoke-test: создать personal workspace,
подключить public и +18 каналы, загрузить Telegram-альбом, проверить четыре
download policy двумя пользователями, затем выполнить быстрый watermark и
закрыть/принять запись очереди доработки. Только после этого сливать и выполнять
обычный перезапуск бота; Supervisor self-update нельзя запускать поверх
неопубликованного/разошедшегося рабочего дерева.
