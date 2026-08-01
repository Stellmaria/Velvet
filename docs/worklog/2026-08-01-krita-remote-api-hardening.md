# Рабочая запись: защита Krita Remote API

## Статус

- Дата: 2026-08-01
- Issue: #510
- PR: #537
- Статус: реализация завершена, ожидается полный CI и merge
- Ветка: `fix/issue-510-krita-loopback-security-v2`

## Запрос

Сделать optional Krita Remote API fail-closed по сетевому bind, аутентификации и загрузке результата, сохранив рабочий container deployment через host-loopback publish.

## Что было не так

Runtime по умолчанию слушал `0.0.0.0`, bearer token не имел ограничителя повторных отказов, upload проверял только PNG signature и использовал общий staging filename. Compose публиковал порт на host loopback, но runtime и server preflight не запрещали случайный публичный bind.

## Анализ

Безопасный runtime default должен быть loopback. Контейнерный wildcard bind допустим только как отдельное явное исключение, когда Docker публикует порт исключительно на `127.0.0.1`. Решение не должно журналировать токены, доверять одному Content-Type или оставлять частично записанные результаты после ошибки.

## Что сделано

- runtime default изменён на `127.0.0.1`;
- non-loopback bind требует `KRITA_REMOTE_ALLOW_UNSAFE_PUBLIC_BIND=true`;
- Compose использует внутренний wildcard только за host-loopback publish;
- server preflight проверяет отдельный worker token и bind policy;
- health требует bearer auth при non-loopback режиме;
- auth и lease failures получают bounded fingerprint-based cooldown;
- upload ограничен по Content-Type, Content-Length, размеру, timeout и concurrency;
- PNG проходит проверку signature, IHDR, dimensions, IDAT, IEND и CRC;
- output и response записываются через уникальный atomic staging с cleanup;
- конкурентная загрузка одной revision отклоняется;
- добавлены security, deployment и worker-protocol regression tests;
- production feature остаётся выключенной по умолчанию.

## Проверки

Запланированы и обязательны перед merge:

- targeted Krita security tests;
- полный tests workflow со всеми shard’ами;
- package/shared inventory contracts;
- bounded type check;
- project notes contract;
- Docker Compose/build и Krita plugin smoke.

## Риски и замечания

Контейнеру нужен explicit wildcard bind, поскольку host loopback находится вне container network namespace. Live SSH tunnel, controlled invalid-token test и Windows worker result upload не выполняются в CI и остаются эксплуатационной acceptance-проверкой #411.

## Ветка и интеграция

Старая ветка PR #537 отстала от `main` на 110 коммитов и конфликтовала. Функциональный diff пересобран поверх актуального `main` без переноса устаревших generated inventories и без merge-коммита со старой историей.

## Что осталось сделать

- синхронизировать generated package/shared inventories на актуальной базе;
- исправить только выявленные текущим CI контракты;
- получить полностью зелёный merge gate;
- слить PR #537 в `main`.

## Блокеры

Внешних блокеров нет. Production enablement и live Windows-worker smoke намеренно не входят в merge gate этого code-slice.

## Следующий шаг

После merge выполнить отдельный SSH-tunnel и Windows-worker smoke в рамках #411 без открытия публичного порта VPS.

## Продолжение работы

Issue #510 закрывается этим code-slice после зелёного CI. Дальнейшие эксплуатационные проверки и включение сервиса ведутся отдельно, чтобы зелёный unit CI не изображал из себя сетевую инфраструктуру.