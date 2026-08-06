# Сессия: retirement legacy media delivery installers

- Дата: `2026-08-06`
- ID: `p1-package-architecture-baseline-installers`
- Линия: `P0 media delivery / architecture retirement`
- Статус: `repository implementation complete; live acceptance pending`
- Базовый commit: `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f`
- Связанные issue: `#457`, `#410`, `#412`, `#455`, `#458`, `#514`

## Цель

Удалить четыре neutralized runtime installer, которые продолжали числиться в startup graph после перехода на durable media delivery PR #488.

## Сделано

- удалены image/video delivery hotfix layers;
- удалены Auf result recovery и active-worker delivery fix layers;
- удалены четыре composition stages;
- удалён runtime `install_delivery_handler` mutation hook;
- active Friendly worker явно отключает inherited best-effort transport phase;
- canonical durable repository/resolver/delivery/redelivery и canonical UI сохранены;
- legacy UI tests перенесены на `media_delivery_ui_install`;
- architecture, stability, shared-contract, repository-layout и navigation inventories пересобраны.

## Гарантии

- provider submit и charging не доступны redelivery path;
- provider success сохраняется до Telegram delivery;
- active worker не выполняет второй legacy transport send;
- UI использует `redeliver_owned_task` и durable state;
- runtime behavior больше не зависит от четырёх retired installer stages.

## Проверки

Branch maintenance выполняет focused unit contracts, generated inventory checks, project preflight и `git diff --check`. Полная required CI матрица выполняется на PR exact head до merge.

## Не выполнено без production access

Live provider/Telegram matrix, restart/CDN/expired URL scenarios и no-double-charge evidence остаются в #410/#412. Issue #457 после merge остаётся открытой только для этой внешней приёмки.
