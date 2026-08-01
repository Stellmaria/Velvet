# Sensitive VL policy и versioned profile

- Дата: 2026-08-02
- ID: #505
- Линия/фаза: Hybrid AI / PR C
- Статус: завершено
- Ветка: `feat/505-sensitive-vision-policy-v2`
- Базовый commit: `3405353041bf5a9a1a79c47084209c519db0656e`

## Перед началом

### Цель

Закрыть следующий безопасный code-slice local-first VL после provider contract и
internal runtime/gateway: разделить standard и sensitive анализ, запретить
неявный переход во взрослый маршрут и ввести versioned structured profile.

### Исходный контекст

PR #506 добавил trusted local provider, а PR #519 добавил internal-only runtime и
gateway. При этом текущий каскад позволял после provider refusal автоматически
перейти из standard в sensitive, sensitive-вызов не требовал явного подтверждения
взрослого режима, а обе ветви использовали общий legacy prompt/profile contract.

### Планируемый объём

- отдельные режимы `standard` и `sensitive`;
- обязательный внешний `adult_confirmed=true` для sensitive-вызова;
- запрет автоматического Flash/Pro → Sensitive fallback;
- отдельные prompts и строгие JSON schemas;
- versioned structured profile и route-aware cache namespace;
- ручная проверка low-confidence sensitive результата;
- fail-closed cloud sensitive feature flag;
- regression tests и актуальная env-документация.

### Критерии готовности

- sensitive provider не вызывается без `adult_confirmed=true`;
- standard отказ не становится разрешением на sensitive-анализ;
- standard и sensitive не разделяют несовместимый cache result;
- неверные schema/prompt version, route и content mode отклоняются;
- structured profile содержит все обязательные поля;
- cloud sensitive остаётся выключенным без отдельного явного флага;
- production AI-флаги не включаются;
- CI и обязательные repository contracts проходят.

### Риски и ограничения

`adult_confirmed` является внешним application decision, а не результатом модели.
Этот срез не определяет возраст по внешности и не реализует NSFW classifier.
Strict JSON schema может выявить несовместимость конкретного inference runtime;
она проверяется отдельно до production enablement. Live Q4/Q8 benchmark остаётся
обязательным серверным этапом.

## После завершения

### Фактически сделано

- добавлены режимы `standard` и `sensitive`;
- sensitive-вызов требует явного `adult_confirmed=true` до cache/provider call;
- отказ Flash или Pro больше не запускает sensitive-модель автоматически;
- standard fallback ограничен `Flash → optional Pro`;
- sensitive выполняет ровно один configured sensitive route;
- low-confidence sensitive результат помечается для ручной проверки;
- standard и sensitive используют разные cache namespaces и model sets;
- введены `schema_version=1` и route-aware `prompt_version`;
- standard и sensitive получают разные prompts и строгие JSON schemas;
- неверные route/version/content_mode и неполный structured profile отклоняются;
- structured profile сохраняет subjects, pose, camera, visibility, covering,
  environment, lighting, visible text, uncertainties и generation risks;
- облачный sensitive provider закрыт по умолчанию и требует отдельного
  `AI_VISION_ALLOW_CLOUD_SENSITIVE=true` для закрытого smoke-test;
- `.env.vision-local.example` закрепляет fail-closed sensitive policy;
- добавлены unit/regression tests всех новых границ.

### Миграции и совместимость

PostgreSQL migration отсутствует. Новый cache namespace содержит schema version и
режим, поэтому старые legacy cache rows не выдаются как новый structured profile.
Публичная сигнатура `analyze()` сохраняет `sensitive=False`; новый параметр
`adult_confirmed=False` делает прежние неявные sensitive-вызовы fail-closed.
`AI_VISION_ENABLED=false` и `AI_VISION_QUEUE_ENABLED=false` остаются без изменений.

### Проверки

- targeted contracts добавлены для router, metered client, profile contract и
  sensitive factory;
- ветка пересобрана поверх актуального `main`, чтобы исключить 36 устаревших
  коммитов и конфликт package architecture baseline;
- package architecture inventory пересобирается после переноса итогового diff;
- полный test workflow, architecture preflight, Docker build, type check и project
  notes contract выполняются на финальном head PR #543;
- live provider calls и production flags намеренно не используются в CI.

### PR и commit

- PR: #543;
- ветка: `feat/505-sensitive-vision-policy-v2`;
- рабочая rebase-ветка: `feat/505-sensitive-vision-policy-rebase-2`;
- финальный head фиксируется после завершения CI-синхронизации.

### Незавершённое

- локальный NSFW classifier и threshold calibration;
- owner correction маршрута и feedback dataset;
- автоматическое определение source adult mode;
- live Q4/Q8 benchmark и model digest pin на VPS;
- production enablement `AI_VISION_ENABLED=true`;
- пакетная очередь;
- калибровка Image-to-Prompt и Pose Extractor из #414.

### Следующий шаг

После зелёного merge gate PR #543 продолжить #505 отдельным classifier/routing
срезом: локальная классификация, threshold version, manual-review outcome и owner
correction без автоматического обучения или cloud sensitive fallback.
