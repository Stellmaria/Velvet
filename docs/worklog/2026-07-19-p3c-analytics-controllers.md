# Сессия: перенос analytics presentation controllers

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-analytics-controllers`
- Линия/фаза: Velvet Archive, P3C
- Статус: `частично`
- Ветка: `agent/p3c-analytics-controllers`
- Базовый commit: `d9d812fc7b35e04d5e1a36b6a6a4d03e6eabdbe0`

## Перед началом

### Цель

Перенести активные Telegram-контроллеры аналитики из legacy `velvet_bot/handlers` в канонический presentation-пакет без изменения команд, callback contracts, порядка регистрации, SQL, use cases и пользовательского поведения.

### Исходный контекст

После слияния PR #201 архитектурный inventory содержал 35 активных legacy implementations, 33 временных module aliases и 56 активных router imports. Следующим P3C-срезом были назначены analytics presentation controllers. Незавершённая ветка прошлого рабочего сеанса уже содержала физический перенос, но отставала от `main`, не имела отдельного worklog и не была оформлена в PR.

### Планируемый объём

- перенести `channel_analytics`, `analytics_dashboard`, `analytics_dashboard_overrides`, `analytics_discussion_overrides` и `analytics_management` в `presentation/telegram/routers/analytics_controllers/`;
- заменить старые handler-файлы aliases того же module object;
- перевести analytics bundle на canonical imports в прежнем порядке;
- сохранить команды `/analytics`, `/analyticsmenu`, `/channelstats`, `/stats`, `/promptstats`, `/hashtagstats`, `/tagstats` и `/characterstats`;
- сохранить callback schemas `AnalyticsCallback`, `DashboardLinkCallback`, `DiscussionInsightCallback` и `AnalyticsManageCallback`;
- синхронизировать ветку с PR #201;
- обновить связанные architecture и phase contracts;
- добавить regression-тесты module identity, alias size, canonical ownership и bundle composition;
- обновить layout inventory и следующий P3C-срез.

### Критерии готовности

- canonical analytics modules содержат реальные implementations;
- пять legacy paths возвращают те же module objects и не содержат decorators;
- analytics bundle импортирует только canonical controllers и сохраняет пять router registrations;
- команды и callback prefixes остаются прежними;
- active legacy implementations уменьшаются с 35 до 30;
- aliases увеличиваются с 33 до 38;
- ветка не отстаёт от `main`;
- полный tests, Docker build и project notes contract зелёные.

### Риски и ограничения

`analytics_dashboard_overrides` и `analytics_discussion_overrides` должны оставаться перед основным dashboard router, иначе более общий callback handler может перехватить специализированные действия. Внутренние helper-модули `analytics_management_aliases`, `analytics_management_common`, `analytics_management_publications` и `analytics_management_tags` в этот срез не входят: они не регистрируют отдельные routers и будут разбираться отдельным structural slice, если их перенос действительно уменьшит связанность.

## После завершения

### Фактически сделано

- пять analytics controllers перенесены в `presentation/telegram/routers/analytics_controllers/`;
- implementations сохранены без изменения прикладного поведения;
- старые paths заменены aliases через `importlib` и `sys.modules`;
- analytics bundle использует canonical imports в прежней последовательности;
- ветка синхронизирована с актуальным `main`, включая PR #201;
- Phase 9, Phase 12, Phase 14 и P3 architecture contracts переведены на canonical paths;
- добавлен отдельный P3C regression-тест identity, alias size, ownership и bundle composition;
- layout inventory обновлён до 30 implementations и 38 aliases;
- следующим срезом назначены core operations presentation controllers.

### Миграции и совместимость

Миграции PostgreSQL не требуются и не изменялись. Команды, callback data, callback prefixes, порядок analytics routers, analytics repositories, discussion insights, classification workflows и тексты интерфейса сохранены. Старые import paths и patch targets продолжают работать как aliases того же module object.

### Проверки

- layout inventory согласован с текущим деревом: 0 прямых handler imports в root, 56 активных routers, 0 дублей, 30 implementations, 38 aliases;
- целевые regression-контракты добавлены;
- полный CI будет зафиксирован после создания PR.

### PR и commit

- рабочая ветка: `agent/p3c-analytics-controllers`;
- синхронизация с `main` выполнена через технический PR #203;
- основной PR будет создан после фиксации worklog;
- финальные CI run и head commit будут добавлены после проверки.

### Незавершённое

До зелёного полного CI срез считается частично завершённым. Временные legacy aliases остаются контролируемым остатком P3D. Четыре analytics management helper-модуля физически остаются в `velvet_bot/handlers`, поскольку они не являются router controllers и не должны расширять текущий diff без отдельной причины.

### Следующий шаг

Создать основной PR, дождаться полного CI, зафиксировать результаты в этом worklog и после слияния продолжить P3C переносом core operations presentation controllers.
