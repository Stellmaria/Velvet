# Сессия: workspace owner controls retirement

- Дата: 2026-07-26
- ID: `2026-07-26-workspace-owner-controls-retirement`
- Линия/фаза: workspace architecture cleanup
- Статус: `в работе`
- Ветка: `agent/workspace-owner-controls-retirement`
- База: `main`

## Цель

Физически вывести из runtime и затем удалить исторический `workspace_owner_controls.py` после завершённых срезов workspace home, archive dashboard, reference dashboard, workspace deletion, media policy, archive navigation, social actions, media mutations, delivery и media deletion.

## Подтверждённое состояние

- Все известные действия callback-префикса `wpa` уже покрыты каноническими bundle-level controllers.
- Legacy personal archive handler остаётся недостижимым в runtime, но физически занимает более 2200 строк.
- `archive_and_public.py` всё ещё подключает `workspace_owner_controls_router`.
- `workspace_watermark.py` и `workspace_reference_buttons.py` всё ещё импортируют compatibility helpers из legacy-модуля.

## Срезы

1. Перевести `workspace_watermark.py` на публичный callback contract и общий workspace/archive access boundary.
2. Перевести `workspace_reference_buttons.py` на отдельный reference presentation/access contract.
3. Удалить подключение `workspace_owner_controls_router` из archive bundle.
4. Заменить legacy-модуль временным compatibility shim либо удалить его после очистки всех импортов.
5. Удалить устаревшие source-level tests и заменить их regressions на отсутствие legacy runtime registration.
6. Запустить type check, targeted workspace tests, полный test suite и Docker build.

## Ограничение текущего среза

Удалять файл целиком до отвязки `workspace_watermark.py` и `workspace_reference_buttons.py` нельзя: эти модули ещё импортируют из него callback/helper symbols. Сначала устраняются зависимости, затем удаляется router. Это предотвращает декоративный рефакторинг, который просто переносит ImportError в запуск бота.
