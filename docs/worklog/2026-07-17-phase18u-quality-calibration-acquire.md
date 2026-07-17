# Сессия: Фаза 18U, PostgreSQL-граница калибровки качества

- Дата: 2026-07-17
- ID: `2026-07-17-phase18u-quality-calibration-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18U
- Статус: завершено
- Ветка: `agent/phase18u-quality-calibration-acquire`
- Базовый commit: `8384506bae9e23399dd540178728eca327805213`

## Перед началом

### Цель

Перевести `QualityCalibrationRepository` на публичный `Database.acquire()` и уменьшить private pool baseline с 113 до 110 обращений без изменения калибровки Qwen.

### Исходный контекст

Фазы 18R–18T закрыли три одиночных AI report repository. Следующий срез содержит три read-only connection point: построение calibration profile, пагинированный список feedback cases и получение одного случая.

Изменение улучшает существующую калибровку качества: устраняет приватную связь repository с pool и делает persistence boundary единообразной. Новая AI-механика, новые исходы и новый пользовательский сценарий не добавляются.

### Планируемый объём

- перевести `profile()`, `list_cases()` и `get_case()` на `self._database.acquire()`;
- сохранить provider/model filters и нормализацию limit 20..5000;
- сохранить outcome sections и ошибку неизвестного раздела;
- сохранить page size 1..10, count query, page clamp, offset и rows query;
- сохранить file name fallback, JSON decode и mapping `CalibrationCase`/`CalibrationCasePage`;
- добавить source/runtime regression-тесты трёх методов;
- уменьшить baseline до 110 обращений в 27 production-файлах;
- обновить inventory, project memory, development status и changelog;
- определить следующий AI/quality repository-срез;
- прогнать полный CI и слить отдельный PR.

### Критерии готовности

- repository не содержит `._require_pool()`;
- source-контракт фиксирует три `self._database.acquire()`;
- profile сохраняет limit clamp, filters и `build_calibration_profile()`;
- list_cases сохраняет count + rows, section filter и safe pagination;
- get_case сохраняет row mapping и `None` для отсутствующего случая;
- baseline равен 110/27;
- tests, Docker build и project notes contract проходят;
- worklog закрыт точными run и следующим шагом.

### Риски и ограничения

- нельзя менять формулы calibration profile и recommended decision;
- нельзя менять outcome groups или pagination UX;
- нельзя включать `ai_quality.py` в этот PR;
- нельзя ослаблять baseline;
- миграции и схема базы не изменяются.

## После завершения

### Фактически сделано

- `profile()`, `list_cases()` и `get_case()` переведены на `Database.acquire()`;
- provider/model filters и limit clamp 20..5000 сохранены;
- outcome sections и ошибка неизвестного раздела не менялись;
- count query, page size 1..10, page clamp, offset и rows query сохранены;
- file-name fallback, JSON decode и mapping `CalibrationCase`/`CalibrationCasePage` не менялись;
- формулы calibration profile и recommended decision не затрагивались;
- добавлены source/runtime regression-тесты трёх методов и отсутствующего случая;
- private pool baseline уменьшен с 113 обращений в 28 файлах до 110 обращений в 27 файлах;
- следующим срезом назначена Фаза 18V: repository-контур `ai_quality.py`, 8 connection points;
- inventory, project memory, development status и changelog обновлены.

### Миграции и совместимость

Миграции и схема базы не изменялись. SQL, фильтры, outcome groups, pagination и публичные модели сохранены.

### Проверки

На head `4d16125ef00d465862404282ca39a1ab6ba3f3fa` успешно завершены:

- `project notes contract #63`;
- `docker build #182`;
- полный workflow `tests #588` с PostgreSQL 16.

После этой итоговой записи CI запускается повторно на финальном head перед merge.

### PR и commit

- PR: #118 `Фаза 18U: QualityCalibrationRepository и Database.acquire`;
- зелёный промежуточный head: `4d16125ef00d465862404282ca39a1ab6ba3f3fa`;
- финальный squash commit фиксируется GitHub при слиянии PR #118.

### Незавершённое

Обязательных пунктов Фазы 18U не осталось. Живые эксплуатационные проверки Supervisor, staging и независимый backup/restore drill остаются отдельными стабилизационными воротами.

### Следующий шаг

Начать Фазу 18V: перевести repository-контур `ai_quality.py` на `Database.acquire()` отдельным worklog/PR и уменьшить baseline с 110 до 102 обращений.
