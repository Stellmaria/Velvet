# Сессия: раннее подтверждение workspace callbacks

- Дата: 2026-07-24
- ID: `2026-07-24-p2-workspace-callback-ack`
- Линия/фаза: P2 workspace callback cleanup
- Статус: `завершено в коде`
- Ветка: `agent/p2-workspace-callback-ack`
- Базовый commit: `3a35ff676a43b8fea60eb40c40d9b6c37fcc879e`

## Цель

Убрать три late callback acknowledgment, появившиеся после расширения личных пространств, не меняя callback data, порядок routers и бизнес-операции.

## Сделано

- быстрые действия подтверждают callback после проверки доступа, но до очистки FSM и загрузки модулей;
- входы создания категории, вселенной и истории подтверждают callback до FSM/database операций;
- управление референсами подтверждает callback до загрузки списков, страниц, Telegram media и mutation operations;
- повторные callback answers после раннего подтверждения удалены;
- поздние уведомления управления референсами отправляются обычным сообщением;
- helper редактирования карточки референса поддерживает уже подтверждённый callback;
- добавлен regression-test порядка acknowledgment;
- P2 inventory обновлён скриптом: 130 callbacks, 0 late/missing, 44 guarded, 11 delegated.

## Инварианты

- callback prefixes и packed data не менялись;
- роли workspace и проверки доступа сохранены;
- SQL, migrations и repository layout не менялись;
- порядок регистрации routers не менялся.

## Проверки

- `python -m compileall` для изменённых модулей: success;
- `python -m unittest tests.test_p2_stability_inventory`: success;
- полный CI запущен на pull request.

## Незавершённое

- дождаться полного CI;
- после merge выполнить workspace smoke test в Telegram.

## Следующий шаг

Перенести SQL настроек workspace из Telegram controller в repository/service boundary отдельным PR.
