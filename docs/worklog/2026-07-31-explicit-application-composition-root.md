# 2026-07-31 — Explicit application composition root

- Дата: 2026-07-31
- ID: `explicit-application-composition-root`
- Issue: #455
- Линия/фаза: P0 correctness-risk architecture
- Статус: `первый bounded slice реализован`
- Ветка: `agent/p0-explicit-application-composition`
- Базовый commit: `2cb9a96ec5ce5066436c83323279855047cb67a7`

## Перед началом

### Цель

Убрать неявную package-level точку входа через `velvet_bot.app.__getattr__` и выразить текущий startup order typed composition contract, не меняя фактическое поведение 27 runtime installation stages.

### Ограниченный объём

- добавить `CompositionStage` и `ApplicationComposition`;
- зафиксировать отдельно bootstrap stages и feature stages;
- сохранить точный порядок всех 27 текущих installers;
- сохранить ленивые imports, чтобы runtime stability и datetime compatibility выполнялись до импорта bootstrap;
- экспортировать обычную `run_application` из `velvet_bot.app`;
- добавить regression tests порядка и explicit package export;
- пересчитать package-wide architecture inventory exact-head workflow.

### Не входит в этот срез

- удаление самих installers и `_INSTALLED` sentinels;
- перенос provider/delivery/UI implementations в factories;
- удаление foreign assignments;
- durable delivery #457;
- provider adapters #459;
- Auf presentation/application migration #458.

## После реализации

### Фактически сделано

- добавлен `velvet_bot/app/composition.py` с typed startup model;
- bootstrap phases выполняются до загрузки `velvet_bot.app.bootstrap.run_application`;
- feature installer modules загружаются только после bootstrap phases и runner import;
- `velvet_bot/app/__init__.py` стал обычным explicit export без `__getattr__` и package import side effects;
- default composition перечисляет все 27 stages и делает фактический порядок читаемым без анализа import history;
- runtime guard блокирует расхождение declared и actual feature stage order;
- добавлены unit tests полного order contract, phase boundary, drift guard и package export;
- временный exact-head workflow пересчитывает generated inventory и удаляет себя в generated commit.

### Риски и совместимость

Installer implementations, их feature flags, patched symbols и relative order не изменены. Новый composition contract пока оборачивает legacy stages, а не объявляет их целевой архитектурой. Это создаёт явную точку дальнейшего burn-down: последующие PR заменяют отдельные `CompositionStage` typed registrations/factories и уменьшают package fingerprints.

### Проверки

- `tests/test_application_composition.py`;
- полный unit test suite;
- package architecture inventory `--check`;
- bounded type check;
- Docker build;
- project notes contract.

### Следующий срез #455

Перенести первую bounded family, которая не меняет provider/delivery behavior, из side-effect installer в explicit registration. Приоритет отдаётся infrastructure/model routing или isolated worker registration; delivery recovery/hotfix layers остаются до #457.
