# 2026-07-31: изолированные Hermes Coder для Velvet и Max

## Цель

Разделить работу кодирующих агентов по двум проектам после инцидента, когда общий Hermes продолжил старую задачу Velvet вместо изменения объекта Max.

## Реализация

Добавлен отдельный Compose-стек `deploy/hermes-coders/compose.yaml`:

- `hermes-coder-velvet` получает только отдельный checkout Velvet;
- `hermes-coder-max` получает только отдельный checkout Romatic Club Max;
- у каждого собственные Hermes data, Telegram token, fine-grained GitHub token и read-only DB env;
- production checkout, production `.env`, Docker socket и PostgreSQL volumes не монтируются;
- coder-контейнеры не подключаются к production Docker networks напрямую;
- минимальные TCP-прокси соединяют только PostgreSQL `5432` с внутренними DB-сетями кодеров.

## Модельный маршрут

После реальных Telegram smoke-тестов зафиксированы:

```text
gpt-5.4-mini -> gpt-5.6-terra -> gpt-5.6-luna
```

`gpt-5.3-codex-spark` исключён: два разных API-токена стабильно получили `403 Insufficient account balance` при положительном балансе.

## База данных

Preflight требует production read-only identities:

```text
Velvet: hermes_velvet_ro@postgres/velvet
Max:    hermes_max_ro@postgres/card_hunter
```

Широкая production-запись не выдаётся. Миграции и контролируемые изменения данных остаются отдельным этапом с проверкой и явным разрешением.

## Эксплуатация

Добавлены:

- derived Hermes image с `gh` и PostgreSQL client;
- отдельные `SOUL.md` с жёсткой границей проекта;
- model aliases `mini`, `terra`, `luna`;
- идемпотентный installer;
- preflight секретов, checkout и read-only ролей;
- `hermes-coders.service` для systemd;
- regression-контракт `tests/test_hermes_coders_contract.py`;
- подробный runbook `deploy/hermes-coders/README.md`.

Installer намеренно не запускает gateway, пока не заполнены два разных Telegram bot token и два разных fine-grained GitHub token.
