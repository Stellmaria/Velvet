# Инвентаризация приватной PostgreSQL-границы

Дата закрытия: 18 июля 2026 года.

## Результат

AST-сканирование production package `velvet_bot/` фиксирует:

- 0 внешних обращений к `Database._require_pool()`;
- 0 production-файлов в baseline;
- внутреннее использование внутри класса `Database` остаётся разрешённой реализационной деталью;
- новые внешние обращения по-прежнему блокируются CI.

Фаза 18 завершена. Legacy query-модули, application services, Telegram handlers и активные compatibility-фасады больше не используют приватную PostgreSQL-границу.

## Архитектурный итог

- media-set AI, prompt actions и duplicate actions используют repository boundaries;
- SQL медиасетной AI-проверки и сравнения референсов вынесен из Telegram handlers;
- старый discussion dashboard делегирует каноническому query;
- quality-set compatibility использует публичный `Database.acquire()`;
- baseline равен `0/0`.

## Контроль

```bash
python scripts/inventory_private_pool.py --check-baseline
```

Фаза 18 закрыта. Дальнейшие задачи относятся к общему P2/P3, а не к private-pool debt.
