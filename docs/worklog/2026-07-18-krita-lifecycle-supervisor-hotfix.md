# Сессия: управляемый жизненный цикл Krita и hardening Supervisor

- Дата: 2026-07-18
- ID: `2026-07-18-krita-lifecycle-supervisor-hotfix`
- Линия/фаза: стабилизация Krita watermark bridge и Windows Supervisor
- Статус: частично
- Ветка: `agent/krita-lifecycle-supervisor-hotfix`
- Базовый commit: `3baa4ac2b383ed60ce5d0be1a372644fc35bbe72`

## Перед началом

### Цель

Убрать ручной запуск Krita из watermark-сценария, автоматически закрывать только управляемый экземпляр после десяти минут простоя, сделать PNG-экспорт неинтерактивным и устранить ограничение Windows Task Scheduler, мешавшее перезапуску самого Supervisor.

### Исходный контекст

Krita bridge уже создавал preview и финальный PNG, но desktop-приложение приходилось запускать вручную. Krita 5.3 открывала окно параметров PNG и возвращала неуспех до ручного подтверждения. Telegram image-документы отклонялись при неточном MIME type. Обычный restart бота работал, а self-restart Supervisor падал, потому что полная Python-команда превышала ограничение параметра `/TR` у `schtasks.exe`.

### Планируемый объём

1. Добавить Supervisor-owned процесс Krita с PID marker и idle monitor.
2. Добавить локальные API-маршруты запуска, touch, status и stop.
3. Пробуждать Krita при входе в watermark и при каждом действии пользователя.
4. Не закрывать вручную открытый экземпляр Krita.
5. Синхронизировать актуальный плагин перед управляемым запуском.
6. Перевести PNG export в batch mode без диалога параметров.
7. Принимать image-документы по расширению и проверять фактическое содержимое Pillow.
8. Заменить длинный Task Scheduler action коротким временным wrapper-файлом.
9. Уточнить интерфейс выдачи финального PNG без сжатия.

### Критерии готовности

- вход в `💧 Водяной знак` запускает Krita без ручной консоли;
- повторный вход не создаёт второй процесс;
- Supervisor закрывает только запущенную им Krita после 600 секунд простоя;
- pending или processing bridge request блокирует idle shutdown;
- вручную открытая Krita определяется как unmanaged и не закрывается;
- PNG export не показывает диалог параметров;
- документы PNG, JPG, JPEG, WEBP, TIFF и BMP принимаются даже с generic MIME type, но повреждённые файлы отклоняются;
- финальный результат отправляется как PNG-документ без Telegram-сжатия;
- self-restart Supervisor создаёт Task Scheduler action короче лимита `/TR`;
- unit tests, Docker build и project notes contract проходят.

### Риски и ограничения

- реальный GUI-процесс Krita можно полноценно проверить только в интерактивной Windows-сессии;
- Task Scheduler должен запускать Supervisor от вошедшего пользователя, иначе GUI может оказаться в невидимой сессии;
- Linux CI проверяет контракты процесса и wrapper, но не заменяет живой Windows-тест;
- существующие watermark jobs со статусом error не переигрываются автоматически.

## После завершения

### Фактически сделано

- добавлен `KritaProcessManager`, который запускает Krita по требованию, хранит managed PID в runtime marker и восстанавливает ownership после self-restart Supervisor;
- idle monitor проверяет активность каждые две секунды и завершает managed Krita после заданного таймаута только при пустой bridge-очереди;
- существующий ручной процесс Krita используется как external/unmanaged и никогда не закрывается менеджером;
- перед управляемым запуском актуальный plugin source копируется в пользовательский каталог `pykrita`;
- добавлены локальные Supervisor API для status, ensure, touch и stop;
- watermark handler вызывает Supervisor при открытии формы, отправке изображения, изменении параметров и подтверждении результата;
- image-документы принимаются по whitelist расширений или точному image MIME type, после скачивания проверяются через Pillow;
- добавлен silent PNG exporter с batch mode, полным `InfoObject` и проверкой реально созданного файла;
- кнопка финального действия переименована в `✅ Скачать PNG без сжатия`, документ получает понятное PNG-имя;
- self-restart Supervisor передаёт Task Scheduler только короткий путь к временному `.cmd`, длинная bootstrap-команда выполняется внутри wrapper;
- добавлены unit tests ownership, external-process guard, busy bridge guard и длины Task Scheduler action.

### Миграции и совместимость

Миграции базы данных не менялись. Существующие таблицы watermark jobs/revisions и формат bridge request/response сохранены. При выключенном watermark feature flag Krita manager также остаётся выключенным. При включённом watermark автозапуск включается по умолчанию, но может быть отдельно отключён настройкой `KRITA_AUTOSTART_ENABLED`.

### Проверки

- workflow `tests` для первого head PR `#121` прошёл успешно;
- Docker build для первого head PR `#121` прошёл успешно;
- project notes contract первого head ожидаемо указал на отсутствие отдельного worklog; эта запись добавлена для повторной проверки;
- добавлены три теста Krita process manager и тест короткого bootstrap wrapper;
- живая Windows-проверка ещё не выполнена на итоговом head.

### PR и commit

- draft PR: `#121` — `Krita lifecycle, lossless export and Supervisor restart hardening`;
- ветка: `agent/krita-lifecycle-supervisor-hotfix`;
- первый CI head: `7b47f5d4026d77640b39b91a1cf9890ec4f960a3`.

### Незавершённое

- дождаться повторного зелёного project notes contract и полного CI итогового head;
- на Windows закрыть текущую ручную Krita, обновить main и перезапустить Supervisor;
- проверить автоматический запуск при открытии watermark;
- проверить отсутствие PNG-диалога;
- проверить автоматическое закрытие managed Krita после десяти минут;
- проверить self-restart Supervisor через Telegram.

### Следующий шаг

После зелёного CI слить PR `#121`, обновить рабочий `main` и выполнить один живой Windows smoke-test: открыть watermark при закрытой Krita, получить preview и PNG без диалога, затем проверить idle shutdown и self-restart Supervisor.
