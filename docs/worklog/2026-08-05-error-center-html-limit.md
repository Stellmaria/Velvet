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

Telegram ограничивает сообщение 4096 символами после разбора entities. Существующий renderer уже ограничивал plain-text traceback до добавления `<pre>` и owner digest до пяти summary по 180 символов, поэтому дополнительный срез готового HTML не обеспечивал лимит, а только мог разрушить синтаксис.

### Планируемый объём

- удалить произвольные срезы уже собранного HTML;
- сохранить существующий plain-text budget и хвост traceback;
- проверить закрытые `<code>`/`<pre>` и escaped entities;
- проверить incident acknowledgement и owner digest;
- не менять storage, fingerprinting, redaction или callbacks.

### Критерии готовности

- готовый HTML не режется произвольным slice;
- parsed message text не превышает лимит Telegram;
- динамические данные остаются экранированными;
- длинный traceback сохраняет полезный хвост;
- XML-совместимая проверка подтверждает закрытые теги и entities;
- focused tests и полный required CI зелёные.

### Риски и ограничения

Изменение не затрагивает PostgreSQL schema, fingerprinting, redaction, acknowledgement storage, callback data или маршрутизацию сообщений. Production rollout требует пересборки только `bot`.

## После завершения

### Фактически сделано

- удалён `[:4090]` из `_render_incident()`;
- удалён `[:4090]` из текста owner digest;
- сохранён существующий расчёт budget до HTML-обёртки и сохранение хвоста traceback;
- добавлена XML-проверка HTML с `<`, `>`, `&`, кавычками и Unicode;
- добавлена проверка parsed message length, acknowledgement и пяти длинных digest rows;
- production-код изменён ровно в двух выражениях без новых функций, ветвлений и архитектурных зависимостей.

### Миграции и совместимость

Миграции отсутствуют. Короткие сообщения сохраняют прежнюю структуру. Ack callbacks и incident storage не меняются.

### Проверки

- `tests/test_error_center.py` расширен focused regression-тестами;
- XML parser проверяет закрытые теги и entities;
- полный required CI запускается на PR.

### PR и commit

PR: `#628`. Итоговый merge SHA фиксируется после прохождения required checks и отдельного разрешения владельца на merge.

### Незавершённое

- production rollout и `/test_error_alert` выполняются отдельно после merge;
- synthetic long-message smoke остаётся rollout-only проверкой.

### Следующий шаг

Получить полный зелёный CI, затем запросить отдельное решение о merge и controlled rollout только `bot`.
