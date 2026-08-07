# Сессия: Hermes credential rotation precedence

- Дата: 2026-08-07
- ID: `2026-08-07-hermes-credential-rotation`
- Линия/фаза: Hermes / production credential rotation hardening
- Статус: `частично`
- Ветка: `hotfix/hermes-credential-rotation-v3`
- Базовый commit: `99fb1cb3d61fd5787179014e3b1659e2a0276e26`

## Перед началом

### Цель

Исправить канонический Hermes installer так, чтобы намеренная ротация Byesu credential в operator env действительно обновляла project-scoped secret env для Velvet и Max, не стирая существующий project credential, когда новый operator credential отсутствует.

### Исходный контекст

Production capability audit показал, что текущий Hermes credential видит только часть требуемых моделей и должен быть заменён на media-capable token group. Проверка `deploy/hermes-coders/install.sh` выявила, что installer при синхронизации project secret env предпочитает уже существующий `BYESU_HERMES_CODEX_API_KEY` новому значению из operator env. Поэтому штатная ротация через `/srv/velvet/.env.hermes` не могла распространиться в `/srv/hermes-coders/secrets/velvet.env` и `max.env`.

Первый смысловой head прошёл полный CI без failure/cancelled, но `main` несколько раз продвигался независимыми Arthur rollout hotfix-ами до merge, и strict branch protection корректно отклонял устаревшие базы. Текущая ветка создана заново непосредственно от main `99fb1cb3d61fd5787179014e3b1659e2a0276e26`; последние Arthur изменения затрагивают только rollout workflow/worklog и не пересекаются с Hermes installer или rotation test.

### Планируемый объём

- поменять precedence только для Byesu model credential: непустой canonical operator value должен быть авторитетным;
- сохранить существующий project credential, если operator env не предоставляет новый model credential;
- не менять project-scoped Telegram, GitHub, API server, runner, router и sandbox launcher credentials;
- не ослаблять provider capability smoke;
- добавить regression tests, которые исполняют фактический secret-sync heredoc из installer;
- не менять production credentials в рамках GitHub hotfix.

### Критерии готовности

- новый operator Byesu credential заменяет старые значения одновременно в Velvet и Max project env;
- отсутствие operator model credential не очищает существующие project keys;
- legacy operator alias продолжает поддерживать штатную ротацию;
- project-scoped credentials и mode `0600` сохраняются;
- обязательный CI проходит полностью на неизменном и up-to-date PR head;
- branch protection принимает merge без bypass;
- merge не считается production activation.

### Риски и ограничения

Hotfix меняет precedence чувствительной конфигурации, поэтому ошибка могла бы непреднамеренно стереть или заменить project-scoped credentials. Изменение ограничено одной model credential и покрыто исполнением реального installer heredoc в temporary files. Значения production credentials в репозиторий и worklog не добавляются.

Отдельный внешний blocker остаётся: production всё ещё требует новый media-capable Byesu token group с доступом к Sol, Terra, Luna и обеим image-моделям. Этот PR такой credential не создаёт и image fallback автоматически не включает.

## После завершения

### Фактически сделано

В `deploy/hermes-coders/install.sh` precedence для `BYESU_HERMES_CODEX_API_KEY` изменён так, чтобы непустой canonical operator value использовался первым, а существующее project value оставалось fallback только при отсутствии нового operator credential.

Добавлен `tests/test_hermes_coder_secret_rotation.py`. Тест извлекает и исполняет фактический Python heredoc синхронизации secrets из installer, а не дублирует его алгоритм отдельной тестовой реализацией.

### Миграции и совместимость

Формат env-файлов не меняется. Существующие project-scoped Telegram, GitHub, API server, runner, router и sandbox launcher credentials сохраняют прежнюю семантику. Поддержка `BYESU_HERMES_API_KEY` как operator alias остаётся. Если новый model credential не задан, существующий project credential сохраняется, поэтому upgrade без ротации обратно совместим.

### Проверки

Regression cases покрывают:

- ротацию старых Velvet/Max Byesu project credentials новым canonical operator credential;
- сохранение старых project credentials при отсутствии operator model credential;
- ротацию через legacy operator alias;
- сохранение остальных project-scoped значений и mode `0600`.

Предыдущий смысловой head уже проходил unit-tests, preflight, targeted-contracts, notes, mypy и security checks без failure/cancelled. Для текущей свежей базы требуется новый полный CI; старые результаты не используются как основание merge.

### PR и commit

Текущая ветка создана от main `99fb1cb3d61fd5787179014e3b1659e2a0276e26`. PR #672, #674 и #676 являются superseded попытками того же bounded hotfix на базах, которые устарели во время параллельных Arthur rollout merge. Каноническим считается новый PR этой ветки; merge допускается только при неизменном, up-to-date и полностью зелёном head.

### Незавершённое

- создать канонический PR текущей ветки и закрыть superseded PR;
- дождаться полного CI на актуальной базе;
- объединить PR только если GitHub branch protection принимает merge без обхода;
- отдельно обновить production checkout;
- получить и установить новый media-capable Byesu credential без публикации его значения;
- capability-check нового credential выполнить до включения image fallback;
- только после успешной capability проверки включить production image routing и штатно активировать Hermes.

### Следующий шаг

Создать канонический PR из `hotfix/hermes-credential-rotation-v3` в `main`, дождаться полного CI и объединить его только при неизменном up-to-date head. Production activation продолжить отдельной операторской процедурой после появления подходящего Byesu credential.
