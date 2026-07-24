# Сессия: раннее подтверждение workspace callbacks

- Дата: 2026-07-24
- ID: `2026-07-24-p2-workspace-callback-ack`
- Линия/фаза: P2 workspace callback cleanup
- Статус: `завершено в коде`
- Ветка: `agent/p2-workspace-callback-ack`
- Базовый commit: `c2d98464218c279dd1d5e5e8f8f7efa4cf2ba151`

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
- P2 inventory обновлён скриптом.

## Инварианты

- callback prefixes и packed data не менялись;
- роли workspace и проверки доступа сохранены;
- SQL, migrations и repository layout не менялись;
- порядок регистрации routers не менялся.

## Проверки

- `python -m compileall` для изменённых модулей;
- `python -m unittest tests.test_p2_stability_inventory`;
- полный CI запускается на pull request.

## Незавершённое

- дождаться полного CI;
- после merge выполнить workspace smoke test в Telegram.

## Следующий шаг

Перенести SQL настроек workspace из Telegram controller в repository/service boundary отдельным PR.
