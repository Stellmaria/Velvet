# Сессия: крупные файлы для managers и быстрые теги персонажей

- Дата: 2026-07-19
- ID: `2026-07-19-manager-large-files-character-tags`
- Линия/фаза: Velvet Archive, функциональное улучшение после P3C
- Статус: `завершено`
- Ветка: `agent/manager-large-files-character-tags`
- Базовый commit: `01158e01c0af36326ff0eb098e08065811c20985`

## Перед началом

### Цель

Разрешить владельцам и настроенным модераторам открывать крупные архивные изображения исходным Telegram-файлом, когда облачный Bot API не может построить photo preview, и добавить персонажам быстрые теги, используемые вместо полного имени в `/save`, референсах и карточках.

### Исходный контекст

Админский архив уже умел отправлять документы-изображения больше 20 МБ файлом, но public manager viewer, которым пользуются владельцы и модераторы, продолжал пытаться строить полноразмерное photo preview и показывал alert. В проекте уже существовала таблица `character_aliases`, однако ручные алиасы использовались в основном аналитикой и не участвовали в разрешении целей `/save` и команд референсов.

### Планируемый объём

- включить file fallback в manager viewer для владельца и модератора;
- использовать исходный Telegram `file_id`, не скачивая файл через cloud Bot API;
- сохранить прежний photo pipeline для обычных публичных зрителей;
- добавить общий resolver персонажа по точному имени или алиасу;
- подключить resolver к `/save`, `/character`, topic binding и основным reference flows;
- добавить кнопку `🏷 Быстрые теги` в карточку `/characters`;
- добавить кнопочный add/delete flow и команды `/tagadd`, `/tags`, `/tagdel`;
- разрешить tag callbacks и ForceReply настроенным модераторам;
- переиспользовать существующую таблицу aliases без новой миграции;
- добавить regression-тесты manager file fallback, tag resolution, callback length и access policy.

### Критерии готовности

- изображение больше 20 МБ открывается владельцу и модератору как документ;
- неизвестный старый `file_size` также получает document fallback при ошибке preview;
- обычный пользователь не получает manager-only file fallback;
- тег `Кроу`, привязанный к `Макс Кроу`, разрешается в `/save Кроу` и `/refs Кроу`;
- в карточке персонажа доступна кнопка управления тегами;
- модератор может открыть tag menu и ответить на ForceReply;
- callback data не превышает лимит Telegram 64 байта;
- tests, Docker build и project notes contract зелёные.

### Риски и ограничения

Ручные алиасы глобально идентифицируют персонажа; конфликтующий тег отклоняется существующим уникальным ограничением. Публичным пользователям исходный крупный документ автоматически не раскрывается: fallback доступен только manager-доступу. Команда `/save` сохраняет существующую матрицу ролей; этот срез меняет разрешение имени, а не расширяет право сохранения.

## После завершения

### Фактически сделано

- `public_preview_overrides` отправляет крупный image-document владельцам и модераторам исходным файлом;
- добавлен fallback для старых записей без надёжного `file_size`, если preview resolver завершился ошибкой или не вернул фото;
- добавлен `character_resolution.resolve_character` с exact-name-first и alias fallback;
- `/save`, profile/topic flows и основные reference commands используют общий resolver;
- в карточке персонажа добавлена кнопка `🏷 Быстрые теги`;
- добавлены кнопочный список, добавление, удаление и ForceReply flow;
- добавлены команды `/tagadd`, `/tags`, `/tagdel`, `/tagreindex` с legacy-синонимами `/aliasadd`, `/aliases`, `/aliasdel`, `/aliasreindex`;
- tag permissions вынесены в отдельные moderator contracts, не расширяющие legacy `MODERATOR_COMMANDS`;
- policy и middleware разрешают tag commands, `ctag` callbacks и tag reply marker модераторам;
- P2 callback baseline сохранён через явную регистрацию callback handler;
- обновлены command coverage и architecture inventory;
- добавлены regression-тесты для manager file fallback и character quick tags.

### Миграции и совместимость

Новая миграция не требуется. Используется существующая таблица `character_aliases`, нормализация aliases и ограничения уникальности. Полные имена продолжают разрешаться первыми. Старые alias-команды и analytics alias management сохраняются. Публичный просмотр, file IDs, captions, keyboard state и `protect_content` не изменены.

### Проверки

- первый CI: Docker build #566 и project notes contract #417 прошли; tests #1030 выявил пять устаревших inventory/access/command contracts;
- callback registration переведена на явную без изменения runtime behavior;
- moderator tag permissions отделены от legacy editor contract;
- command coverage и architecture inventory обновлены;
- повторный CI: tests #1039, Docker build #575, project notes contract #426 — success;
- manager/public split, alias SQL lookup, кнопка карточки, callback length и moderator access подтверждены.

### PR и commit

- PR: #209 `Allow manager file fallback and character quick tags`;
- рабочая ветка: `agent/manager-large-files-character-tags`;
- первый manager fallback commit: `806fc4fe100cff59fcd1ef3dde9d6d84b21c19af`;
- общий resolver commit: `d93bdd18230fe924457ce270fb2e80e909103083`;
- кнопочный tag controller commit: `93bef6b64db377ad26faa2af2fc07b9193748c58`;
- проверенный runtime head: `c816d3222dd68cebb5a82167a340b863bb5b619e`.

### Незавершённое

Функциональный срез завершён. После развёртывания остаётся живая проверка на реальном Telegram-документе больше 20 МБ и создание тестового тега через карточку. Это эксплуатационная проверка, а не блокировка merge.

### Следующий шаг

Слить PR #209 после зелёного CI финального documentation head. Затем продолжить P3D: классификацию пяти standalone handler implementations и контролируемое удаление временных aliases.
