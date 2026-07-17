# Сессия: Фаза 18T, PostgreSQL-граница отчёта оформления Velvet

- Дата: 2026-07-17
- ID: `2026-07-17-phase18t-velvet-formatting-report-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18T
- Статус: завершено
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
- private pool baseline уменьшен с 114 обращений в 29 файлах до 113 обращений в 28 файлах;
- одиночные report repositories полностью удалены из baseline;
- следующим срезом назначена Фаза 18U: `QualityCalibrationRepository`, 3 connection points;
- inventory, project memory, development status и changelog обновлены.

### Миграции и совместимость

Миграции и схема базы не изменялись. Таблица, analysis version, SQL, типы параметров и публичный метод `save()` сохранены.

### Проверки

На head `e7ed7bbbe85feb8f25b54d91fa95da03fcf502f3` успешно завершены:

- `project notes contract #59`;
- `docker build #177`;
- полный workflow `tests #583` с PostgreSQL 16.

После этой итоговой записи CI запускается повторно на финальном head перед merge.

### PR и commit

- PR: #116 `Фаза 18T: VelvetFormattingReportRepository и Database.acquire`;
- зелёный промежуточный head: `e7ed7bbbe85feb8f25b54d91fa95da03fcf502f3`;
- финальный squash commit фиксируется GitHub при слиянии PR #116.

### Незавершённое

Обязательных пунктов Фазы 18T не осталось. Живые эксплуатационные проверки Supervisor, staging и независимый backup/restore drill остаются отдельными стабилизационными воротами.

### Следующий шаг

Начать Фазу 18U: перевести `QualityCalibrationRepository` на `Database.acquire()` отдельным worklog/PR и уменьшить baseline с 113 до 110 обращений.
