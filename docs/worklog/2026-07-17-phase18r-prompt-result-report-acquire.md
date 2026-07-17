# Сессия: Фаза 18R, PostgreSQL-граница отчёта промт/результат

- Дата: 2026-07-17
- ID: `2026-07-17-phase18r-prompt-result-report-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18R
- Статус: завершено
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

- `PromptResultReportRepository.save()` переведён на `Database.acquire()`;
- SQL, `analysis_version = 1`, `RETURNING id` и порядок 17 параметров сохранены;
- ограничения provider до 64 символов и model до 160 символов сохранены;
- оценки, verdict, `created_by` и JSON payload не менялись;
- добавлен source/runtime regression-тест публичной границы, аргументов и кириллического JSON;
- private pool baseline уменьшен с 116 обращений в 31 файле до 115 обращений в 30 файлах;
- следующим срезом назначена Фаза 18S: `PaletteCompositionReportRepository`;
- inventory, project memory, development status и changelog обновлены.

### Миграции и совместимость

Миграции и схема базы не изменялись. Таблица, analysis version, SQL, типы параметров и публичный метод `save()` сохранены.

### Проверки

На head `6c6277d7350a83cb76ad8c004f6015cf9614879d` успешно завершены:

- `project notes contract #55`;
- `docker build #171`;
- полный workflow `tests #577` с PostgreSQL 16.

После этой итоговой записи CI запускается повторно на финальном head перед merge.

### PR и commit

- PR: #114 `Фаза 18R: PromptResultReportRepository и Database.acquire`;
- зелёный промежуточный head: `6c6277d7350a83cb76ad8c004f6015cf9614879d`;
- финальный squash commit фиксируется GitHub при слиянии PR #114.

### Незавершённое

Обязательных пунктов Фазы 18R не осталось. Живые эксплуатационные проверки Supervisor, staging и независимый backup/restore drill остаются отдельными стабилизационными воротами.

### Следующий шаг

Начать Фазу 18S: перевести `PaletteCompositionReportRepository` на `Database.acquire()` отдельным worklog/PR и уменьшить baseline с 115 до 114 обращений.
