# Безопасное ограничение HTML Error Center

- Дата: 2026-08-05
- ID: `error-center-html-limit`
- Линия/фаза: Production stabilization / Error Center
- Статус: `завершено`
- Issue: `#624`
- Ветка: `fix/error-center-html-limit`
- Базовый commit: `73f7ef51d51f10cb2c8cd5181c9da74465864207`

## Перед началом

### Цель

Устранить вторичный production-дефект Error Center, при котором готовый HTML произвольно обрезался по позиции 4090 и мог завершиться внутри тега или HTML entity.

### Исходный контекст

При обработке production-инцидента кошелька Error Center зарегистрировал исключение, но обновление сообщения могло завершиться `TelegramBadRequest: can't parse entities`. В `velvet_bot/error_center.py` использовались два небезопасных среза готового HTML:

- `return text[:4090]` для карточки инцидента;
- `text="\n".join(lines)[:4090]` для owner digest.

### Планируемый объём

- ограничивать динамический текст по длине экранированного представления до добавления HTML-тегов;
- сохранять хвост traceback;
- гарантировать закрытые `<code>` и `<pre>`;
- применить единый контракт к incident и owner digest;
- добавить regression-тесты максимальной длины, специальных символов и acknowledgement.

### Критерии готовности

- готовый HTML не режется произвольным slice;
- результат не превышает безопасный Telegram budget 4090 символов;
- динамические данные экранированы;
- длинный traceback сохраняет полезный хвост;
- XML-совместимая проверка подтверждает закрытые теги и entities;
- focused tests и полный required CI зелёные.

### Риски и ограничения

Изменение не затрагивает PostgreSQL schema, fingerprinting, redaction, acknowledgement storage, callback data или маршрутизацию сообщений. Production rollout требует пересборки только `bot`.

## После завершения

### Фактически сделано

- добавлен `_escape_limited()`, вычисляющий допустимый prefix или tail по длине уже экранированного текста;
- `_render_incident()` теперь заранее резервирует HTML-обёртки и acknowledgement metadata;
- summary получает bounded prefix, traceback получает bounded tail;
- owner digest распределяет доступный budget между пятью последними инцидентами;
- произвольные срезы готового HTML удалены;
- добавлены тесты на `<`, `>`, `&`, кавычки, Unicode, длинные summary/traceback и пять длинных digest rows.

### Миграции и совместимость

Миграции отсутствуют. Короткие сообщения сохраняют прежнюю структуру. Ack callbacks и incident storage не меняются.

### Проверки

- `tests/test_error_center.py` расширен focused regression-тестами;
- XML parser используется как независимая проверка закрытых тегов и entities;
- полный required CI запускается на PR.

### PR и commit

PR и итоговый merge SHA фиксируются после создания PR и прохождения required checks.

### Незавершённое

- package architecture inventory может потребовать штатной регенерации из-за изменения LOC/AST метрик;
- production rollout и `/test_error_alert` выполняются отдельно после merge;
- synthetic long-message smoke остаётся rollout-only проверкой.

### Следующий шаг

Создать PR, получить полный зелёный CI, затем принять отдельное решение о merge и controlled rollout только `bot`.
