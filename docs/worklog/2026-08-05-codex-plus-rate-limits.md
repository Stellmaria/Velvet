# Сессия

- Дата: 2026-08-05
- ID: `codex-plus-rate-limits-20260805`
- Статус: `завершено`
- Ветка: `feat-codex-plus-rate-limits`
- Базовый commit: `cc22b85068127327cda87ca7315a5470d0e76b9c`
- Линия/фаза: `owner provider balances / Codex subscription observability`

## Перед началом

### Цель

Добавить на служебный экран балансов лимиты Codex, относящиеся к действующей ChatGPT-подписке coder-профиля Velvet, с остатком по каждому возвращённому окну и временем до сброса.

### Исходный контекст

Coder Velvet уже авторизован в Codex через ChatGPT OAuth и хранит `auth.json` только внутри защищённого `/srv/hermes-coders/codex/velvet`. Codex app-server предоставляет стабильные read-only методы `account/read` и `account/rateLimits/read`. Бот не должен получать OAuth-файл, email аккаунта, refresh token или сырой ответ app-server.

Между production-сетью Velvet и изолированной coder-сетью уже существует аутентифицированный `hermes-coder-router`, подключённый к обеим сетям. Поэтому лимиты можно передавать через узкий read-only endpoint без расширения доступа bot-контейнера.

### Планируемый объём

- получить plan type и окна лимитов через локальный Codex app-server;
- нормализовать только проценты использования, длительность окна и Unix-время сброса;
- добавить read-only endpoint coder runner и прокси-маршрут router;
- передать существующий router client token в `.env.server` через orchestration installer;
- показать в Telegram процент остатка и относительное время до сброса;
- добавить regression-тесты нормализации, маршрута, форматирования и отсутствующей конфигурации.

### Вне объёма

- чтение общего ChatGPT billing или API billing;
- передача OAuth-файлов в bot-контейнер;
- расходование earned reset credits;
- отображение email, account id, access token или refresh token;
- ручное назначение лимитов, отсутствующих в ответе Codex.

### Критерии готовности

- plan `plus` отображается как `Codex Plus`;
- окно 300 минут отображается как `5 ч`, 10080 минут как `7 дн.`;
- `usedPercent=27` отображается как `73% осталось`;
- reset time отображается относительным безопасным текстом;
- Telegram и router не выводят идентификаторы аккаунта и секреты;
- все обязательные CI-проверки проходят.

### Риски и ограничения

- backend может вернуть только одно окно, поэтому UI отображает только фактически полученные окна;
- запуск app-server добавляет несколько секунд к ручному обновлению служебного экрана;
- Codex CLI и runner release должны обновляться совместно;
- production требует повторного orchestration install/reconcile для передачи endpoint и токена в `.env.server`.

## После завершения

### Фактически сделано

- runner выполняет обязательный initialize/initialized handshake Codex app-server;
- account и rate-limit ответы сокращаются до безопасного DTO без email и токенов;
- добавлен аутентифицированный `GET /v1/rate-limits` и router proxy для проекта Velvet;
- orchestration installer сохраняет router endpoint и существующий client token в `.env.server`;
- служебный экран показывает каждое доступное окно подписки, процент остатка и время до сброса;
- добавлены focused regression-тесты.

### Миграции и совместимость

Миграций базы данных нет. Новые переменные `CODEX_LIMITS_BASE_URL` и `CODEX_LIMITS_API_KEY` записываются installer-ом без раскрытия значения. При отсутствии переменных экран деградирует в безопасное сообщение `интеграция не настроена`.

### Проверки

- Python sources компилируются;
- focused unit-тесты покрывают Plus, два окна, безопасное DTO и отсутствующую конфигурацию;
- package architecture inventory регенерирован штатным скриптом;
- обязательные CI-проверки запускаются на PR.

### Решения и компромиссы

- используется официальный app-server, а не частные ChatGPT backend endpoints;
- бот обращается к coder runner только через существующий аутентифицированный router;
- email и прочие account fields отбрасываются на стороне runner;
- остаток вычисляется как `100 - usedPercent`, без попытки переводить подписку в деньги или токены;
- UI не предполагает, что primary всегда означает 5 часов, а secondary всегда неделю, и подписывает окно по фактической длительности.

### PR и commit

- PR: будет создан после публикации ветки;
- commit: будет зафиксирован после применения изменений.

### Незавершённое

- дождаться обязательного CI;
- слить PR;
- выпустить Hermes coder runtime и обновить production bot/orchestration;
- подтвердить реальные значения Plus в Telegram.

### Следующий шаг

После merge выполнить штатный server deploy, затем штатный Hermes coder release/orchestration reconcile и нажать `Обновить балансы`.
