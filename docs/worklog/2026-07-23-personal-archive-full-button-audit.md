# Сессия: полный аудит кнопок пользовательского архива

- Дата: 2026-07-23
- ID: `2026-07-23-personal-archive-full-button-audit`
- Линия/фаза: personal workspace product audit
- Статус: `частично`
- Ветка: `codex/personal-archive-full-audit`
- Базовый commit: `f12219fd223595b5aaea8824f843a0c8a7bfde57`

## Перед началом

### Цель

Проверить полный пользовательский путь личного архива: главное меню, роли, персонажей, карточку материала, референсы, публичную видимость, скачивание, watermark, подписки, доработку и Qwen. Каждая видимая кнопка должна иметь достижимый обработчик, корректную проверку роли и workspace boundary.

### Исходный контекст

Основной Qwen-продукт и изоляция доработки уже были слиты в PR `#307`. При полном проходе обнаружились два ранее подготовленных, но не слитых исправления: доставка подписок личных публичных пространств в PR `#306` и fallback быстрого watermark в PR `#305`. PR `#306` был зелёным, но оставался draft. PR `#305` конфликтовал с новым Qwen/rework router.

### Планируемый объём

- довести подписку персонажа до фактической workspace-scoped доставки;
- объединить watermark fallback с новым ранним Qwen/rework router;
- перехватить настройки скачивания до устаревшего generic handler;
- убрать ложное требование отдельного назначения `Watermark-копии`;
- заменить устаревшую подсказку сохранения на реальный button-first путь;
- скрыть Qwen-кнопку карточки у роли без доступа;
- проверить матрицу главного меню владельца и участника;
- проверить все действия карточки материала и порядок routers;
- проверить add/replace/delete/compare для референсов;
- проверить workspace scope подписок, доработки, public и Qwen;
- добавить единый регрессионный контракт полного пользовательского архива.

### Критерии готовности

- все видимые кнопки главного меню ведут в существующие scoped handlers;
- owner image card содержит полную ожидаемую матрицу действий;
- viewer не получает owner/Qwen actions;
- Qwen не предлагается для видео и анимации;
- `Что делают кнопки` находится внизу и описывает только текущую карточку;
- watermark запускается при наличии модуля и asset без отдельного storage destination;
- subscriber download всё ещё требует канал проверки;
- подписки личных публичных архивов обрабатываются worker и открывают точный workspace/media;
- rework/public/Qwen/watermark/download policy проходят через ранний scoped router;
- reference card имеет add/replace/delete/compare/back/close;
- tests, type check, Docker build, backup restore drill и project notes contract проходят.

### Риски и ограничения

GitHub Actions проверяет маршрутизацию, роли, схему, PostgreSQL и контейнер, но не может нажать реальные Telegram-кнопки, запустить desktop Krita или локальную Ollama на пользовательской видеокарте. После merge требуется отдельный живой smoke test.

## После завершения

### Фактически сделано

- зелёный PR `#306` переведён из draft и слит в `main`; merge commit `f12219fd223595b5aaea8824f843a0c8a7bfde57`;
- worker подписок теперь сканирует system и все публичные personal workspaces;
- кнопка уведомления содержит точные `workspace_id`, `character_id`, `media_id`;
- текущая audit-ветка основана уже на merged subscription delivery;
- watermark fallback из конфликтующего PR `#305` вручную объединён с Qwen/rework/public router;
- быстрый watermark требует только разрешённый модуль и загруженный asset;
- без destination `Watermark-копии` подтверждённый PNG возвращается в текущий чат;
- download policy watermark-версии больше не требует отдельное storage destination;
- subscriber policy сохраняет обязательный канал `Проверка скачивания`;
- dashboard-help теперь указывает реальный путь `Быстрые действия → Сохранить → Завершить загрузку` и учитывает роль;
- Qwen-кнопка больше не добавляется на read-only viewer card и не показывается для видео/анимации;
- справка карточки обновлена под фактические действия и fallback watermark;
- добавлен единый регрессионный аудит owner/reviewer menus, media card actions, references, router order, policies и notifications.

### Миграции и совместимость

Новых миграций в этом аудите нет. Используются ранее добавленные `z002_workspace_media_rework_isolation.sql` и `z003_workspace_qwen_product.sql`. Callback formats и таблицы архива не меняются. Старый generic handler остаётся совместимым fallback, но опасные personal actions перехватываются точным ранним router.

### Проверки

GitHub Actions будут запущены после открытия draft PR. Финальные run numbers и количество тестов будут внесены после зелёного head.

### PR и commit

Draft PR будет открыт из `codex/personal-archive-full-audit` в `main`. Финальный head и merge commit будут записаны после CI.

### Незавершённое

- дождаться полного CI и исправить возможные type/test/inventory failures;
- слить audit PR в `main`;
- закрыть конфликтующий PR `#305` как перенесённый в общий аудит;
- выполнить `Supervisor → Update`;
- пройти живой Telegram smoke test владельцем, reviewer и обычным читателем;
- отдельно проверить Krita approve/fallback и одну реальную Qwen-задачу через Ollama.

### Следующий шаг

Открыть draft PR, получить зелёный CI, затем проверить в Telegram цепочку: создать персонажа → пакетно сохранить материалы → открыть карточку → пройти каждую кнопку → включить public → подписаться вторым аккаунтом → получить уведомление → проверить watermark fallback → Qwen → rework → возврат в public.
