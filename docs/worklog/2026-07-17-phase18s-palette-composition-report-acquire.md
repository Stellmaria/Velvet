# Сессия: Фаза 18S, PostgreSQL-граница отчёта палитры и композиции

- Дата: 2026-07-17
- ID: `2026-07-17-phase18s-palette-composition-report-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18S
- Статус: частично
- Ветка: `agent/phase18s-palette-composition-report-acquire`
- Базовый commit: `08c514842b8e113dbf7062799def723e4e366e8f`

## Перед началом

### Цель

Перевести `PaletteCompositionReportRepository` на публичный `Database.acquire()` и уменьшить private pool baseline с 115 до 114 обращений без изменения сохранения отчёта палитры и композиции.

### Исходный контекст

Фаза 18R закрыла repository отчёта «промт против результата». Следующий минимальный срез сохраняет размеры изображения, palette metrics, семь оценок композиции/света/гармонии, confidence, verdict и полный JSON report.

Изменение улучшает существующую AI-функцию: устраняет приватную связь с pool и делает persistence boundary единообразной. Нового пользовательского сценария и новой предметной области нет.

### Планируемый объём

- заменить единственный private pool access на `self._database.acquire()`;
- сохранить SQL, analysis version, порядок 18 параметров и `RETURNING id`;
- сохранить provider/model limits, width/height, `metrics.as_dict()` и оба JSON payload;
- сохранить оценки, confidence, verdict и created_by;
- добавить source/runtime regression-тест;
- уменьшить baseline до 114 обращений в 29 production-файлах;
- обновить inventory, project memory, development status и changelog;
- назначить следующий срез для Velvet formatting report;
- прогнать полный CI и слить отдельный PR.

### Критерии готовности

- repository не содержит `._require_pool()`;
- `save()` использует публичную границу;
- SQL и порядок 18 параметров сохранены;
- metrics/report JSON сериализуются с `ensure_ascii=False`;
- baseline равен 114/29;
- tests, Docker build и project notes contract проходят;
- worklog закрыт точными run и следующим шагом.

### Риски и ограничения

- нельзя менять таблицу, analysis version, метрики или оценки;
- нельзя включать formatting repository в этот PR;
- нельзя менять AI palette/composition бизнес-логику;
- нельзя ослаблять baseline;
- миграции и схема базы не изменяются.

## После завершения

### Фактически сделано

- `PaletteCompositionReportRepository.save()` переведён на `Database.acquire()`;
- SQL, `analysis_version = 1`, `RETURNING id` и порядок 18 параметров сохранены;
- provider/model limits, width/height и `metrics.as_dict()` не менялись;
- composition, balance, framing, hierarchy, depth, lighting, palette harmony, confidence и verdict сохранены;
- оба JSON payload продолжают использовать `ensure_ascii=False`;
- добавлен source/runtime regression-тест публичной границы, metrics, оценок и кириллического JSON;
- private pool baseline уменьшен с 115/30 до 114/29;
- следующим срезом назначена Фаза 18T: `VelvetFormattingReportRepository`;
- inventory, project memory, development status и changelog обновлены.

### Миграции и совместимость

Миграции и схема базы не изменялись. Таблица, analysis version, SQL, типы параметров и публичный метод `save()` сохранены.

### Проверки

Полный CI ещё не запущен. Добавленные тесты должны подтвердить одну public acquire boundary, SQL, 18 параметров, metrics/report JSON и ограничения provider/model.

### PR и commit

Draft PR ещё не открыт. Head будет зафиксирован после открытия PR и первого CI.

### Незавершённое

- открыть draft PR;
- получить tests, Docker build и project notes contract;
- исправить только фактические регрессии;
- закрыть worklog точными run;
- слить Фазу 18S.

### Следующий шаг

Открыть PR и прогнать полный CI. После merge начать Фазу 18T отдельной сессией.
