# Krita watermark bridge

## Назначение

Контур автоматизирует существующую подготовку изображений Velvet Archive к публикации. Владелец отправляет изображение боту, выбирает положение, цвет, прозрачность, размер и отступ, получает preview и подтверждает отдельный финальный файл. Исходник никогда не перезаписывается.

Функция относится к существующим media/publication-сценариям и не создаёт новую предметную область.

## Архитектура

```text
Telegram owner UI
    ↓
WatermarkService
    ↓
WatermarkRepository + PostgreSQL revisions
    ↓
локальный файловый bridge
    ↓
Krita Python plugin
    ↓
PNG output + JSON response
    ↓
Telegram preview / final document
```

Сетевой сервер не открывается. Бот и Krita работают с одним локальным каталогом:

```text
VelvetKritaBridge/
├── sources/
├── requests/
├── responses/
├── outputs/
└── previews/
```

## Установка плагина

1. Выполнить:

```powershell
python tools/krita/package_plugin.py
```

2. Импортировать созданный ZIP через управление ресурсами Krita либо скопировать `velvet_logo.desktop` и каталог `velvet_logo` в `pykrita`.
3. Включить `Velvet Anatomy Logo` в настройках Python-плагинов.
4. Перезапустить Krita.
5. В Krita выбрать `Инструменты → Сценарии → Velvet Anatomy: настроить bridge-каталог…`.
6. Указать тот же каталог, который задан в `.env` бота.

## Конфигурация бота

По умолчанию функция выключена:

```env
KRITA_WATERMARK_ENABLED=false
KRITA_BRIDGE_DIR=C:\Users\username\VelvetKritaBridge
KRITA_PROCESSING_STALE_SECONDS=600
```

`KRITA_WATERMARK_ENABLED=true` разрешается только после живой проверки на целевой Windows. При выключенном флаге worker не регистрируется, а UI сообщает, что bridge отключён.

`KRITA_PROCESSING_STALE_SECONDS` определяет возраст `*.processing`, после которого безопасный незавершённый request можно вернуть в очередь. Минимальное значение в runtime — 30 секунд.

## Использование

1. Открыть `/menu`.
2. Нажать `💧 Водяной знак`.
3. Ответить изображением на форму.
4. Дождаться preview.
5. Кнопками изменить угол, цвет, прозрачность, размер или отступ.
6. `↩️ Предыдущая версия` создаёт новую revision с прошлыми настройками.
7. `🚫 Без знака` строит preview из исходника без watermark.
8. `✅ Сохранить` подтверждает только текущую ready revision и отправляет финальный PNG как документ.

Аварийный резерв: ответить командой `/watermark` на изображение.

## Состояния и revisions

- `pending`: текущая revision ждёт worker;
- `processing`: request передан Krita;
- `ready`: output получен и проверен;
- `error`: Krita, файловый protocol или path validation вернули контролируемую ошибку.

Каждая настройка создаёт новую revision. Worker забирает только текущую pending revision. Исторические revisions не переигрываются как новая очередь. Если старая processing revision завершилась после новой, её результат сохраняется в истории, но не заменяет актуальный Telegram preview.

Undo создаёт новую revision с предыдущими настройками. Строки истории не откатываются и не переписываются.

## Восстановление `*.processing`

При каждом цикле worker проверяет processing revisions:

1. если response уже существует, он обрабатывается;
2. если обычный request существует, новый request не создаётся;
3. если существует свежий `*.processing`, worker ждёт Krita;
4. stale `*.processing` атомарно возвращается в обычный request только при отсутствии response и обычного request;
5. если после порога нет request, processing и response, revision переводится в контролируемую ошибку;
6. recovery фиксируется в журнале с job и revision.

Таким образом, перезапуск бота или Krita не должен оставлять job в вечном `processing` и не должен создавать параллельные дубли обработки.

## Безопасность путей

- bridge не открывает TCP-порт;
- source разрешён только внутри `sources/`;
- request разрешён только внутри `requests/`;
- response разрешён только внутри `responses/`;
- output из response разрешён только внутри `outputs/` или `previews/`;
- output обязан точно совпадать с ожидаемым путём конкретной revision;
- пути нормализуются повторно перед чтением и отправкой Telegram;
- traversal, UNC, чужой Windows drive в несовместимой среде и выход через symlink/reparse point отклоняются;
- response и final output должны быть обычными файлами;
- request создаётся атомарно через временный файл;
- Krita открывает копию исходника и экспортирует отдельный output;
- исходник не сохраняется поверх себя;
- callback data не содержит файловых путей или произвольных команд.

## Транзакционные гарантии

Approve выполняется в одной PostgreSQL-транзакции:

1. блокируется job;
2. блокируется связанная текущая revision через `FOR UPDATE`;
3. проверяется, что job активен;
4. проверяется, что revision всё ещё текущая и имеет статус `ready`;
5. в `final_path` записывается output именно этой revision.

Повторный approve возвращает ясный доменный ответ. Устаревшая ready revision не может быть подтверждена после создания новой revision.

Cancel блокирует job и изменяет только активное задание. Approved job неизменяем; старый callback отмены получает спокойный ответ и не создаёт ERROR.

## Проверки CI

Перед merge обязательны:

- `project notes contract`;
- полный tests workflow с PostgreSQL 16;
- Docker build;
- применение миграций на пустой PostgreSQL 16;
- watermark repository integration tests;
- backup/restore drill с таблицами `watermark_jobs` и `watermark_revisions`;
- сборка ZIP плагина и `zipfile.testzip()`.

CI подтверждает Python-контракт, миграцию, callback data и файловый protocol, но не заменяет реальный Krita Python API и Windows filesystem semantics.

## Живая проверка Windows

До production-ready статуса обязательно проверить на целевой Windows:

1. Krita запущена;
2. плагин включён;
3. бот и Krita используют один bridge-root;
4. фото создаёт request;
5. Krita создаёт preview;
6. четыре угла работают;
7. белый, чёрный, auto и HEX работают;
8. прозрачность, размер и отступ создают revisions;
9. Undo работает;
10. `Без знака` работает;
11. финальный PNG отправляется документом;
12. перезапуск бота не теряет processing job;
13. перезапуск Krita восстанавливает stale request;
14. output вне bridge-root отклоняется;
15. старый callback не отменяет approved job.

До завершения этого списка:

```env
KRITA_WATERMARK_ENABLED=false
```
