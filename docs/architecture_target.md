# Целевая архитектура Velvet Archive

Документ фиксирует направление постепенного разнесения проекта по доменам без массовой переписи и остановки работающего бота.

## Основные правила

1. `main.py` содержит только настройку логирования и запуск приложения.
2. Сборка зависимостей, middleware, workers и жизненный цикл находятся в `velvet_bot/app`.
3. Telegram transport находится в `velvet_bot/presentation/telegram`.
4. Бизнес-правила группируются по доменам в `velvet_bot/domains`.
5. SQL находится только в repositories или специализированных query-модулях.
6. Сервисы не импортируют Telegram-типы.
7. Handlers не выполняют SQL и не содержат длинную бизнес-логику.
8. Старые импорты сохраняются через тонкие compatibility-модули до завершения переноса.
9. Каждый архитектурный срез проходит полный CI до слияния.

## Целевая структура

```text
velvet_bot/
  app/
    bootstrap.py
    commands.py
    dispatcher.py
    workers.py

  core/
    access/
    config/
    database/
    errors/
    logging/
    security/
    time/

  domains/
    analytics/
    archive/
    backups/
    characters/
    discussions/
    media/
    publication/
    references/
    system/

  infrastructure/
    postgres/
    telegram/
    filesystem/

  presentation/
    telegram/
      callbacks/
      formatters/
      keyboards/
      middleware/
      routers/
      compat.py
      router.py

  shared/
    pagination.py
    result.py
    text.py
    types.py

  workers/
    manager.py
    registry.py
```

Каждый домен постепенно получает собственные `models.py`, `repositories.py`, `services.py` и при необходимости `queries.py`.

## Порядок переноса

### Срез A. Application и Telegram composition root

- облегчить `main.py`;
- вынести команды, middleware, workers и lifecycle;
- вынести сборку корневого роутера;
- убрать побочные эффекты из `handlers/__init__.py`.

### Срез B. Media quality

- `MediaQualityRepository`;
- `MediaQualityService`;
- отдельные models/query objects;
- handlers только управляют карточками и кнопками.

### Срез C. Publication

- разделить draft validation, scheduling, delivery и event log;
- transport не меняет статусы напрямую;
- единый `PublicationService`.

### Срез D. Characters, stories и references

- объединить разрозненные операции персонажей;
- отдельные каталоги, алиасы, истории и референсы;
- убрать runtime monkey-patching.

### Срез E. Archive и previews

- единая модель отображения медиа;
- preview resolver как инфраструктурный адаптер;
- публичный и административный архив используют общий application service.

### Срез F. Analytics и discussions

- query services для отчётов;
- repositories для SQL;
- Telegram formatters отдельно от расчётов.

### Срез G. Infrastructure и deployment

- Docker Compose;
- healthcheck;
- единая конфигурация окружений;
- release versioning;
- проверка восстановления backup в тестовую базу.

## Критерий завершения

Перенос считается завершённым, когда корень `velvet_bot` содержит только compatibility-фасады и общие точки входа, а новые функции добавляются внутри конкретного домена, не увеличивая монолитные файлы старой структуры.
