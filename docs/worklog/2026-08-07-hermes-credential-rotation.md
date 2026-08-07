# Сессия: Hermes credential rotation precedence

- Дата: 2026-08-07
- ID: `2026-08-07-hermes-credential-rotation`
- Линия/фаза: Hermes / production credential rotation hardening
- Статус: `частично`
- Ветка: `hotfix/hermes-credential-rotation`
- Базовый commit: `48b6026fa452195369c0d1b0d04a408fd0022dfd`

## Перед началом

### Цель

Исправить канонический Hermes installer так, чтобы намеренная ротация Byesu credential в operator env действительно обновляла project-scoped secret env для Velvet и Max, не стирая существующий project credential, когда новый operator credential отсутствует.

### Исходный контекст

Production capability audit показал, что текущий Hermes credential видит только часть требуемых моделей и должен быть заменён на media-capable token group. Проверка `deploy/hermes-coders/install.sh` выявила, что installer при синхронизации project secret env предпочитает уже существующий `BYESU_HERMES_CODEX_API_KEY` новому значению из operator env. Поэтому штатная ротация через `/srv/velvet/.env.hermes` не могла распространиться в `/srv/hermes-coders/secrets/velvet.env` и `max.env`.

Первый CI PR #672 был полностью зелёным на head `688c246ba004490d2fada67661ec33f49352f820`, но за время проверки `main` продвинулся через независимый Arthur rollout PR #671. Branch protection корректно отказал в merge устаревшей базы. Ветка была перепроиграна поверх `48b6026fa452195369c0d1b0d04a408fd0022dfd`; изменения #671 ограничены Arthur workflow/worklog и не пересекаются с Hermes hotfix.

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

Первый CI head `688c246ba004490d2fada67661ec33f49352f820` завершился без failure/cancelled, включая unit-tests, preflight, targeted-contracts, notes и security checks. Merge не выполнялся из-за требования up-to-date branch после независимого продвижения `main`; после replay требуется новый полный CI на свежем head.

### PR и commit

PR: #672. Исходный head `688c246ba004490d2fada67661ec33f49352f820` был перепроигран поверх свежего main `48b6026fa452195369c0d1b0d04a408fd0022dfd` без изменения смыслового hotfix. Merge допускается только при неизменном, up-to-date и полностью зелёном новом head.

### Незавершённое

- дождаться нового полного CI после replay на свежий main;
- объединить PR #672 только если GitHub branch protection принимает merge без обхода;
- отдельно обновить production checkout;
- получить и установить новый media-capable Byesu credential без публикации его значения;
- capability-check нового credential выполнить до включения image fallback;
- только после успешной capability проверки включить production image routing и штатно активировать Hermes.

### Следующий шаг

Дождаться полного CI нового head PR #672 и объединить его в `main`, если head остаётся up-to-date и mergeable. Production activation продолжить отдельной операторской процедурой после появления подходящего Byesu credential.
