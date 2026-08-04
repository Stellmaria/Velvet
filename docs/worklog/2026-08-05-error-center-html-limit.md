# Безопасное ограничение HTML Error Center

- Дата: 2026-08-05
- ID: `error-center-html-limit`
- Линия/фаза: Production stabilization / Error Center
- Статус: `завершено и выкачено`
- Issue: `#624`
- PR: `#628`
- Ветка: `fix/error-center-html-limit`
- Базовый commit: `73f7ef51d51f10cb2c8cd5181c9da74465864207`
- Merge commit: `224f34d31ea583319a6e25e32cdcf95c7a6a291f`

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

### Проверки до merge

- `tests/test_error_center.py` расширен focused regression-тестами;
- XML parser проверяет закрытые теги и entities;
- required CI прошёл перед merge;
- PR `#628` слит squash-commit `224f34d31ea583319a6e25e32cdcf95c7a6a291f`;
- issue `#624` закрыт после merge.

### Production rollout

Controlled rollout выполнен 2026-08-05 на commit `224f34d31ea583319a6e25e32cdcf95c7a6a291f`.

Подтверждено на production:

- checkout и восемь изменённых application-файлов совпали с target Git blobs;
- `scripts/server_smoke.py` завершился успешно: база `velvet`, 92 миграции, `active_ai_tasks=0`, Telegram bot `@dominusVelvetbot`;
- контейнер `bot` остался `running/healthy`, restart count `0`;
- `/test_error_alert` создал incident `#470`, сообщение в лог-чате и acknowledgement владельцем `7221553045`;
- synthetic long-message smoke создал incident `#471` и сообщение `13592`;
- parsed Telegram text для длинного incident составил 3006 символов из допустимых 4096;
- хвост traceback сохранился, HTML и entities прошли XML-проверку;
- acknowledgement длинного incident записан владельцем `7221553045`;
- в логах отсутствовали `can't parse entities`, `Unclosed start tag` и ошибки обновления acknowledgement.

### Сопутствующее наблюдение rollout

Во время rollout обнаружено, что ручной запуск `deploy/server/deploy.sh` от `root` вместе с глобальным `umask 077` способен оставить tracked-файлы checkout владельцем `root` и режимом `0600`. Содержимое файлов совпадало с target; владельцы и индекс были восстановлены без изменения кода или данных. Durable follow-up запрещает запуск deploy не владельцем checkout и выполняет `git reset --hard` в изолированном `umask 022`.

### Итог

Дефект произвольного обрезания готового HTML устранён, merge и production rollout завершены, ручной и synthetic smoke подтверждают корректную публикацию и acknowledgement длинных Error Center сообщений.
