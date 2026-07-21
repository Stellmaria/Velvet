# Сессия: Global Telegram navigation audit

- Дата: 2026-07-21
- ID: `2026-07-21-global-navigation-audit`
- Линия/фаза: Telegram UX and navigation
- Статус: `завершено`
- Ветка: `agent/global-navigation-audit`
- Базовый commit: `8340fd0adf906b91a564d27d3e47608aa73d3db9`

## Перед началом

### Цель

Полностью проинвентаризировать Telegram-интерфейс Velvet, привести кнопки и переходы к понятной структуре для Android и desktop Telegram, не потерять ни одной существующей функции и закрепить единые правила автоматическими проверками.

### Исходный контекст

Qwen-контур и верхнеуровневое owner-меню уже получили компактную навигацию. В остальных доменах оставались локальные клавиатуры с длинными подписями, неодинаковыми названиями одинаковых действий, перегруженными строками и динамическими именами без безопасной обрезки.

### Планируемый объём

- собрать generated inventory всех `InlineKeyboardButton`, `KeyboardButton`, inline/reply markup и callback actions;
- измерить длину подписей, число кнопок в строке, динамические названия и callback limit;
- определить единый словарь навигации и компактных названий;
- исправить owner, archive, public archive, characters, stories, references, publication, analytics, quality, backup, supervisor, diagnostics, watermark и notification UI;
- сохранить callback data, команды и доступность всех функций;
- добавить contract tests для мобильной сетки и generated coverage;
- проверить full suite, PostgreSQL, type check, Docker и project notes.

### Критерии готовности

- все production-клавиатуры учтены generated inventory;
- основные панели используют не более двух кнопок в строке, кроме стандартной пагинации;
- длинные подписи сокращены без потери смысла;
- динамические названия безопасно ограничены;
- основные разделы используют единое название `Главная`;
- callback data не превышает Telegram limit;
- ни одна зарегистрированная функция не теряет кнопку или командный fallback;
- все CI-проверки зелёные.

### Риски и ограничения

Автоматическая замена текста без знания контекста может сделать подпись короче, но менее понятной. Поэтому inventory используется как измеритель, а изменения выполнены по доменам с сохранением callback semantics. Однострочные динамические карточки элементов используют отдельный лимит 44 символа, а двухколоночные действия ограничиваются 24 символами.

## После завершения

### Фактически сделано

- добавлен AST-based scanner production-клавиатур;
- проинвентаризированы 378 Python-файлов, 54 UI-файла и 509 inline-кнопок;
- первоначальный реальный baseline составлял 37 проблем: 34 динамические подписи без безопасной обрезки, две перегруженные строки и одна длинная статическая кнопка;
- ложные срабатывания на понятные контекстные кнопки возврата исключены из контракта;
- итоговый generated baseline: 509 кнопок, 0 нарушений, максимальная строка из трёх кнопок только для пагинации;
- создан общий `compact_button_text()` для имён персонажей, историй, вселенных, аналитических источников и публикационных черновиков;
- создан `two_column_rows()` для стабильной двухколоночной раскладки на Android и desktop;
- исправлены archive, public archive, manager archive, characters, stories, publication, analytics, quality, backup, Supervisor, Error Center, notifications и owner navigation;
- перегруженные строки Backup и Supervisor разделены без удаления действий;
- унифицирован переход владельца как `🏠 Главная`;
- callback data, callback actions и slash-команды не изменялись;
- generated inventory хранится в `docs/generated/telegram_navigation_inventory.md` и проверяется тестом на актуальность;
- временный применитель и служебный workflow удалены из итогового diff.

### Миграции и совместимость

Миграции не требуются. Callback data, callback actions и slash-команды сохранены. Изменены только подписи, раскладка строк и безопасное отображение динамического текста.

### Проверки

- generated navigation scanner: 509 кнопок, 0 нарушений;
- generated inventory freshness test: success;
- локальная компиляция production, scripts и tests: success;
- full GitHub suite: 1019 тестов, success;
- PostgreSQL integration tests: success;
- strict type check: success;
- Docker build: success;
- project notes contract: success.

### PR и commit

PR #270: `Audit and standardize Telegram navigation`.

### Незавершённое

В этом срезе не создавался визуальный screenshot-тест Telegram-клиентов: Telegram сам отвечает за конкретный рендеринг шрифтов и ширины. Структурные ограничения, длина текста, число кнопок в строке и callback limit теперь проверяются автоматически.

### Следующий шаг

После слияния обновить локальный `main`, перезапустить Velvet через Supervisor и выполнить короткий live smoke основных owner/public экранов на Android и desktop Telegram.
