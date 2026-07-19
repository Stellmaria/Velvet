# Сессия: возврат из карточки персонажа и первый P3D cleanup

- Дата: 2026-07-19
- ID: `2026-07-19-directory-back-navigation-p3d`
- Линия/фаза: Velvet Archive, runtime hotfix + P3D
- Статус: `завершено`
- Ветка: `agent/fix-directory-back-navigation-p3d`
- Базовый commit: `61964ad71dd0485142d28bcc3b4a4a9d08eaf41b`

## Перед началом

### Цель

Исправить `ValueError: Неизвестная категория архива` при нажатии кнопки `↩️ К списку` в карточке персонажа и начать безопасный перевод внутренних consumers с legacy `velvet_bot.handlers.admin_directory` на canonical presentation import.

### Исходный контекст

Последний hotfix нормализовал человекочитаемые категории, но callback карточки всё ещё мог сохранить пустое либо устаревшее значение категории. Кнопка возврата передавала это значение в `list_character_directory`, после чего service закономерно отклонял его. Ошибка особенно вероятна для карточек, открытых не из обычного списка, а из аудита, тегов, истории или старого Telegram-сообщения.

### Планируемый объём

- канонизировать категорию при построении кнопок карточки;
- передавать `character_id` в callback возврата;
- восстанавливать категорию из текущей карточки при пустом или устаревшем callback;
- для старых callbacks без `character_id` безопасно возвращать меню категорий вместо ERROR;
- добавить regression-тесты;
- перевести затронутые production imports на canonical directory module;
- пройти целевые и полные проверки CI.

### Критерии готовности

- пустая, русская и устаревшая категория не вызывают ERROR при возврате;
- новая кнопка `К списку` содержит каноническую категорию и `character_id`;
- старое Telegram-сообщение с некорректным callback деградирует в меню категорий;
- существующие категории и uncategorized flow не меняют поведение;
- production consumers в выбранном P3D-срезе не импортируют `handlers.admin_directory`;
- tests, Docker build и project notes contract зелёные.

### Риски и ограничения

Массовое удаление всех 68 handler aliases в этот срез не входит. Alias `handlers.admin_directory` остаётся для внешних imports и ещё не переведённых тестов до отдельного подтверждённого retirement-среза.

## После завершения

### Фактически сделано

- добавлен canonical helper `resolve_directory_category`;
- callback-категория нормализуется, затем используется актуальная категория персонажа, затем `uncategorized`;
- кнопка `↩️ К списку` содержит canonical category, page и `character_id`;
- старые menu callbacks с пустой либо неизвестной категорией перехватываются существующим character rename router и возвращают список категорий вместо ERROR;
- rename ForceReply marker больше не сохраняет сырую callback-категорию;
- KR profile controller переведён с `velvet_bot.handlers.admin_directory` и `velvet_bot.handlers.admin_stories` на canonical presentation imports;
- отдельный recovery router и новый compatibility component не добавлялись;
- добавлены regression-тесты resolver, callback payload, stale filter и canonical imports.

### Миграции и совместимость

Миграции PostgreSQL не требуются. Callback prefix `adir`, команды и таблицы не изменены. Старые валидные callbacks работают как раньше; старые невалидные callbacks безопасно возвращают меню категорий.

### Проверки

- первый PR head запустил tests #1057 и Docker #592;
- project notes #441 выявил незавершённый статус worklog, документ приведён к обязательному завершённому формату;
- финальный CI запускается повторно на обновлённом head.

### PR и commit

- PR: #212 `Fix character directory back navigation and start P3D cleanup`;
- ветка: `agent/fix-directory-back-navigation-p3d`;
- основной runtime commit: `2766304d142b49c361c1946eeab3a56be7da6bbd`;
- regression tests commit: `f426058e57039628268a00972d06f8073b3d4eae`.

### Незавершённое

- остальные production consumers legacy `handlers.admin_directory` будут переводиться отдельными P3D-группами;
- 68 compatibility aliases не удаляются массово;
- staging, Windows Supervisor checks, repository layout, typing и Heavy Runtime остаются отдельными линиями.

### Следующий шаг

Дождаться зелёного финального CI, слить PR #212 и продолжить P3D canonical import cleanup следующей связной группой consumers без изменения пользовательского поведения.
