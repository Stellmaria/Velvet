# Сессия: Фаза 18F, PostgreSQL-граница обсуждений

- Дата: 2026-07-17
- ID: `2026-07-17-phase18f-discussion-database-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18F
- Статус: в работе
- Ветка: `agent/phase18f-discussion-database-acquire`
- Базовый commit: `3ced5abb1782ede34526eed31b89e466b3c88eef`

## Перед началом

### Цель

Перевести `DiscussionRepository` на публичный `Database.acquire()` без изменения аналитики обсуждений архивного канала, реакции пользователей и связи discussion chat с родительским каналом.

### Исходный контекст

Фаза 18E завершила publication repository и закрепила предметную изоляцию Velvet Archive от аукционного бота. Следующий записанный срез `DiscussionRepository` содержит шесть точек получения соединения: проверку tracked discussion, parent channel lookup, полную замену реакций, транзакционный reaction delta, общий отчёт и статистику участников.

Этот домен относится к аналитике комментариев под публикациями архива. Он не является чатом аукциона и не должен получать ставки, лоты, валюты или аукционные роли.

### Планируемый объём

- перевести все точки соединения `DiscussionRepository` на `self._database.acquire()`;
- сохранить tracked-channel фильтры и parent-channel lookup;
- сохранить транзакцию и `FOR UPDATE` в `apply_reaction_delta`;
- сохранить нормализацию reaction breakdown и защиту от отрицательных значений;
- сохранить агрегаты overview и participant stats;
- расширить regression-тест Фазы 18;
- добавить runtime-тест public acquire, transaction и locked reaction delta;
- обновить project memory, development status и changelog;
- определить следующий изолированный repository-срез.

### Критерии готовности

- repository не содержит `._require_pool()`;
- все соединения открываются через `Database.acquire()`;
- reaction delta остаётся атомарным и использует `FOR UPDATE`;
- tracked discussion и parent channel contracts не меняются;
- overview и participant stats сохраняют SQL и модели;
- полный tests workflow с PostgreSQL 16, Docker build и project notes contract проходят;
- дневник закрыт точными run, PR/commit и следующим шагом.

### Риски и ограничения

- нельзя расширять этот срез на ingest, analytics или rankings repositories;
- нельзя смешивать discussion analytics с аукционными чатами;
- нельзя менять схему reaction JSON, агрегаты и старые миграции;
- возвраты изнутри transaction context должны корректно освобождать соединение;
- найденные несвязанные проблемы фиксируются отдельно.

## После завершения

### Фактически сделано

Заполняется после реализации.

### Миграции и совместимость

Заполняется после реализации.

### Проверки

Заполняется после реализации.

### PR и commit

Заполняется после реализации.

### Незавершённое

Заполняется после реализации.

### Следующий шаг

Заполняется после реализации.
