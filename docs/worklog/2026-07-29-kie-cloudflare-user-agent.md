# 2026-07-29 — Kie Cloudflare User-Agent

- Дата: 2026-07-29
- ID: kie-cloudflare-user-agent
- Линия/фаза: Линия B — Velvet AI / media generation
- Статус: `завершено`
- Ветка: `agent/kie-cloudflare-user-agent`
- Базовый commit: `815aabb3a9f1c2134c4b3dec84a384b0e4020f6c`

## Перед началом

### Цель

Устранить HTTP 403 Cloudflare Error 1010 `browser_signature_banned` при загрузке Telegram-референсов в Kie File Upload API.

### Исходный контекст

Live-задача `a1465907-0701-4b27-a6f8-150d071ebd76` завершилась до создания provider task на POST `https://kieai.redpandaai.co/api/file-base64-upload`. Ответ Cloudflare сообщил, что клиент заблокирован по сигнатуре браузера. Kie transport использовал стандартный `urllib.request` и не задавал собственный `User-Agent`, поэтому запрос получал библиотечную сигнатуру `Python-urllib/3.14`.

### Планируемый объём

- добавить явный совместимый `User-Agent` в единый набор заголовков Kie client;
- применять его к file upload, createTask и recordInfo;
- разрешить явную замену User-Agent через параметр конструктора для тестов и будущей совместимости;
- запретить пустой User-Agent;
- добавить unit-тест на все три типа Kie-запросов.

### Критерии готовности

- Kie upload больше не отправляет стандартную сигнатуру `Python-urllib`;
- каждый provider request содержит непустой browser-compatible `User-Agent`;
- Authorization и JSON headers сохраняются без изменений;
- unit-тесты, type check, Docker build и project notes contract проходят.

### Риски и ограничения

- live Kie вызовы в CI не выполняются;
- если провайдер дополнительно блокирует IP или TLS fingerprint, потребуется обращение в поддержку Kie, но зафиксированный ответ 1010 указывает именно на сигнатуру клиента;
- существующая неудачная queue-задача уже terminal и автоматически не восстановится после обновления, потребуется новая генерация.

## После завершения

### Фактически сделано

- в `KieClient` добавлен browser-compatible User-Agent по умолчанию;
- User-Agent включён в общий `_headers()`, поэтому используется для upload, createTask и polling;
- конструктор принимает override `user_agent` и отклоняет пустое значение;
- добавлен отдельный unit-тест, подтверждающий отсутствие `Python-urllib` во всех Kie-запросах.

### Миграции и совместимость

Миграции базы и изменения `.env` не требуются. Существующие вызовы `KieClient` совместимы, поскольку новый параметр имеет безопасное значение по умолчанию.

### Проверки

Ожидаются GitHub Actions: tests, type check, Docker build и project notes contract. Реальные Kie-запросы и списания не выполняются.

### PR и commit

- PR: будет создан после завершения кода;
- ветка: `agent/kie-cloudflare-user-agent`;
- базовый commit: `815aabb3a9f1c2134c4b3dec84a384b0e4020f6c`.

### Незавершённое

- после слияния обновить локальный `main`, перезапустить бота и повторить генерацию с референсом;
- при повторном 1010 сохранить Ray ID и передать его поддержке Kie.

### Следующий шаг

Создать PR, дождаться всех зелёных проверок, слить в `main` и провести live smoke загрузки одного референса.
