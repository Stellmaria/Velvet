# Сессия: Фаза 18U, PostgreSQL-граница калибровки качества

- Дата: 2026-07-17
- ID: `2026-07-17-phase18u-quality-calibration-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18U
- Статус: в работе
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
