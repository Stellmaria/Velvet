# Сессия: Фаза 18T, PostgreSQL-граница отчёта оформления Velvet

- Дата: 2026-07-17
- ID: `2026-07-17-phase18t-velvet-formatting-report-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18T
- Статус: частично
- Ветка: `agent/phase18t-velvet-formatting-report-acquire`
- Базовый commit: `3c6cf97e11cb39b76435e379eb6c501a212f2d2f`

## Перед началом

### Цель

Перевести `VelvetFormattingReportRepository` на публичный `Database.acquire()` и уменьшить private pool baseline с 114 до 113 обращений без изменения сохранения отчёта оформления Velvet.

### Исходный контекст

Фазы 18R–18S перевели report repositories промт/результат и палитра/композиция. Третий одиночный report repository сохраняет режим оформления, исходный текст, provider/model, JSON payload, итоговый текст и автора.

Изменение улучшает существующую функцию оформления: устраняет приватную связь repository с pool и делает persistence boundary единообразной. Нового пользовательского сценария и новой предметной области нет.

### Планируемый объём

- заменить единственный private pool access на `self._database.acquire()`;
- сохранить SQL, analysis version, порядок 7 параметров и `RETURNING id`;
- сохранить `FormattingMode`, source/rendered text, provider/model limits, JSON payload и created_by;
- добавить source/runtime regression-тест;
- уменьшить baseline до 113 обращений в 28 production-файлах;
- обновить inventory, project memory, development status и changelog;
- выбрать следующий repository-срез после анализа remaining baseline;
- прогнать полный CI и слить отдельный PR.

### Критерии готовности

- repository не содержит `._require_pool()`;
- `save()` использует публичную границу;
- SQL и порядок 7 параметров сохранены;
- payload JSON сериализуется с `ensure_ascii=False`;
- baseline равен 113/28;
- tests, Docker build и project notes contract проходят;
- worklog закрыт точными run и следующим шагом.

### Риски и ограничения

- нельзя менять таблицу, analysis version или FormattingMode contract;
- нельзя включать более крупный AI/quality repository в этот PR;
- нельзя менять оформление или рендеринг текста;
- нельзя ослаблять baseline;
- миграции и схема базы не изменяются.

## После завершения

### Фактически сделано

- `VelvetFormattingReportRepository.save()` переведён на `Database.acquire()`;
- SQL, `analysis_version = 1`, `RETURNING id` и порядок 7 параметров сохранены;
- `FormattingMode`, исходный и отрендеренный текст не менялись;
- provider/model limits, JSON payload и `created_by` сохранены;
- добавлен source/runtime regression-тест публичной границы, параметров и кириллического JSON;
- private pool baseline уменьшен с 114/29 до 113/28;
- одиночные report repositories полностью удалены из baseline;
- следующим срезом назначена Фаза 18U: `QualityCalibrationRepository`, 3 connection points;
- inventory, project memory, development status и changelog обновлены.

### Миграции и совместимость

Миграции и схема базы не изменялись. Таблица, analysis version, SQL, типы параметров и публичный метод `save()` сохранены.

### Проверки

Полный CI ещё не запущен. Добавленные тесты должны подтвердить одну public acquire boundary, SQL, 7 параметров, FormattingMode, text fields, JSON и provider/model limits.

### PR и commit

Draft PR ещё не открыт. Head будет зафиксирован после открытия PR и первого CI.

### Незавершённое

- открыть draft PR;
- получить tests, Docker build и project notes contract;
- исправить только фактические регрессии;
- закрыть worklog точными run;
- слить Фазу 18T.

### Следующий шаг

Открыть PR и прогнать полный CI. После merge начать Фазу 18U отдельной сессией.
