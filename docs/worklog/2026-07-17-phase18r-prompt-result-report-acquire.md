# Сессия: Фаза 18R, PostgreSQL-граница отчёта промт/результат

- Дата: 2026-07-17
- ID: `2026-07-17-phase18r-prompt-result-report-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18R
- Статус: в работе
- Ветка: `agent/phase18r-prompt-result-report-acquire`
- Базовый commit: `10a1392ecc4aec5b45fa4751d2a7d95b6d9c5a9c`

## Перед началом

### Цель

Перевести `PromptResultReportRepository` на публичный `Database.acquire()` и уменьшить private pool baseline с 116 до 115 обращений без изменения сохранения отчёта «промт против результата».

### Исходный контекст

Фаза 18Q закрыла отдельный `SystemRepository`. Следующий минимальный repository-срез содержит одну операцию сохранения AI-отчёта с 17 параметрами, нормализацией provider/model и JSON payload.

Изменение улучшает существующую AI-функцию: устраняет приватную связь repository с pool и делает persistence boundary единообразной. Новая предметная область и новый пользовательский сценарий не добавляются.

### Планируемый объём

- заменить единственный private pool access на `self._database.acquire()`;
- сохранить SQL, analysis version, порядок 17 параметров и `RETURNING id`;
- сохранить ограничения provider/model, числовые оценки, verdict, JSON и created_by;
- добавить source/runtime regression-тест;
- уменьшить baseline до 115 обращений в 30 production-файлах;
- обновить inventory, project memory, development status и changelog;
- назначить следующий срез для palette composition report;
- прогнать полный CI и слить отдельный PR.

### Критерии готовности

- repository не содержит `._require_pool()`;
- `save()` использует публичную границу;
- SQL и порядок параметров сохранены;
- JSON сериализуется с `ensure_ascii=False`;
- baseline равен 115/30;
- полный tests workflow, Docker build и project notes contract проходят;
- worklog закрыт точными run и следующим шагом.

### Риски и ограничения

- нельзя менять таблицу, analysis version или набор оценок;
- нельзя объединять три report repositories в один PR;
- нельзя менять AI prompt/result бизнес-логику;
- нельзя ослаблять baseline;
- миграции и схема базы не изменяются.

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
