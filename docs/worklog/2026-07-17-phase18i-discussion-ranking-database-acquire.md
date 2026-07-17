# Сессия: Фаза 18I, PostgreSQL-граница рейтингов обсуждений

- Дата: 2026-07-17
- ID: `2026-07-17-phase18i-discussion-ranking-database-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18I
- Статус: в работе
- Ветка: `agent/phase18i-discussion-ranking-database-acquire`
- Базовый commit: `8860ca54d7ebca9d786a12f4579c09ba84f27bb6`

## Перед началом

### Цель

Перевести `DiscussionRankingRepository` на публичный `Database.acquire()` без изменения рейтингов участников и метаданных публикаций архивного канала.

### Исходный контекст

Фазы 18F–18H завершили основной discussion repository, live ingest и сводную аналитику. `DiscussionRankingRepository` формирует пагинированные таблицы рейтингов через общий `_rank_page`: считает общее число строк, нормализует страницу, получает элементы и возвращает `DashboardPage`.

Этот домен оценивает активность в архивных обсуждениях и публикациях. Аукционные места, ставки, победители и валюты к нему не относятся.

### Планируемый объём

- изучить общий `_rank_page` и публичные ranking methods;
- заменить private pool access в общей точке на `self._database.acquire()`;
- сохранить count SQL, row SQL, параметры и page normalization;
- сохранить преобразование строк в `DashboardRankItem` и `DashboardPage`;
- добавить source/runtime regression-тест public boundary и пагинации;
- обновить project memory, development status и changelog;
- определить следующий отдельный discussion repository.

### Критерии готовности

- repository не содержит `._require_pool()`;
- общий ranking query использует публичный API базы;
- пагинация, порядок и поля dashboard items не меняются;
- полный tests workflow с PostgreSQL 16, Docker build и project notes contract проходят;
- дневник закрыт точными run, PR/commit и следующим шагом.

### Риски и ограничения

- нельзя включать activity, post insight или relink repositories;
- нельзя добавлять аукционные ranking types;
- нельзя менять SQL рейтингов и определения score;
- нельзя менять общий presentation contract `DashboardPage`;
- старые миграции не редактируются.

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
