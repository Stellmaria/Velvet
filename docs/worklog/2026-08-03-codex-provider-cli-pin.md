# Сессия: безопасный pin Codex CLI для provider fallback

- Дата: 2026-08-03
- ID: 2026-08-03-codex-provider-cli-pin
- Линия/фаза: server operations / Codex-first provider fallback
- Статус: подготовлено к проверке
- Ветка: fix/codex-provider-cli-pin
- Базовый commit: 9106a71226140cb2ef2787635f3376e695b7bd81

## Перед началом

### Цель

Обеспечить работу custom model provider для Byesu fallback после исчерпания
или недоступности ChatGPT Codex subscription route.

### Исходный контекст

Codex-first runtime был слит в PR #572, но Docker image продолжал использовать
Codex CLI 0.144.4. Для версий 0.144.3 и 0.144.4 зарегистрирован regression,
при котором CLI не применяет custom model provider configuration. Версия
0.144.1 указана как рабочая.

Production rollout PR #572 был остановлен до переключения Git SHA. Старый
runtime восстановлен, а перед повторной попыткой создана консистентная резервная
копия обоих coder projects.

### Планируемый объём

- закрепить Codex CLI 0.144.1 в Docker image;
- синхронизировать runtime smoke и preflight с фактической версией;
- обновить regression contract;
- не менять маршрутизацию, secrets, модели или workspace policy.

### Критерии готовности

- Docker image устанавливает Codex CLI 0.144.1 с digest verification;
- runtime smoke проверяет именно 0.144.1;
- существующие Codex subscription routes остаются активны;
- Byesu custom provider configuration может быть прочитана CLI;
- tests, Docker build и security CI завершаются успешно.

### Риски и ограничения

Pin является временной совместимой мерой до подтверждённого исправления
регрессии в стабильной версии Codex CLI. Обновлять CLI автоматически запрещено.

## После завершения

### Фактически сделано

- Dockerfile pin изменён с 0.144.4 на 0.144.1;
- runtime smoke ожидает 0.144.1;
- preflight сообщает фактический image pin;
- contract tests обновлены под безопасную версию.

### Миграции и совместимость

Форматы Codex auth, Runs API, Brain context, Telegram gateways и Git workspaces
не меняются. Повторный device login не требуется.

### Проверки

- Python compile;
- focused Hermes coder contracts;
- полный GitHub CI;
- после merge требуется live capabilities smoke;
- provider route проверяется только в чистом test workspace.

### PR и commit

PR и итоговый commit заполняются после публикации ветки.

### Незавершённое

- открыть draft PR;
- дождаться полного CI;
- слить hotfix;
- выполнить контролируемый server rollout с проверенного merge SHA.

### Следующий шаг

Опубликовать ветку, открыть draft PR и дождаться зелёных обязательных checks.
