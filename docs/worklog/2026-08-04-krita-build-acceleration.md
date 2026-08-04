# Ускорение Docker-сборки Krita

- Дата: 2026-08-04
- ID: `krita-build-acceleration-2026-08-04`
- Линия/фаза: CI и supply-chain reliability
- Статус: `частично`
- Ветка: `ci/597-accelerate-krita-builds`
- Базовый commit: `5b8b47293213b7ad63b47114368e002e0eb7c7bf`

## Перед началом

### Цель

Сократить время обязательного Docker CI для реальных изменений Krita. После #596 unrelated PR больше не собирает Krita, но Krita-related PR по-прежнему может выполнять холодный `apt-get install krita` из `ubuntu:24.04` и занимать до 40 минут.

### Подтверждённая причина

`Dockerfile.krita-server` объединяет два слоя с разной частотой изменений:

1. тяжёлый системный runtime: Ubuntu, Krita, Qt/PyQt, Xvfb, Mesa и шрифты;
2. часто меняемый слой Velvet: plugin, desktop manifest, entrypoint и healthcheck.

GHA layer cache ускоряет повторный run в доступной cache scope, но не является надёжной общей основой для нового PR. Поэтому первый Krita build в другой ветке может снова устанавливать весь графический стек.

### Планируемый объём

1. Выделить воспроизводимый `Dockerfile.krita-base` только с системными пакетами и runtime user/layout.
2. Публиковать versioned base image в GHCR только из доверенного `main`/manual workflow.
3. Закрепить runtime Dockerfile на явном base reference с digest или immutable version contract.
4. В PR собирать только тонкий runtime/plugin слой поверх опубликованной базы.
5. Сохранить GHA cache как дополнительное ускорение, а не единственную опору.
6. Добавить changed-surface разделение `krita_base` и `krita_runtime`.
7. Сохранить полный Krita smoke для runtime и base изменений.
8. Добавить контракты, запрещающие плавающий `latest`, непинованный action и бессмысленную холодную установку Krita в обычном PR build.

### Критерии готовности

- изменение plugin/entrypoint/healthcheck не выполняет `apt-get install krita`;
- изменение base Dockerfile или package manifest запускает base build contract;
- base image публикуется только из доверенного контекста с минимальными permissions;
- PR не получает package write permissions;
- runtime image остаётся локально загружаемым для smoke;
- Krita smoke не пропускается при изменениях Krita;
- workflow concurrency и timeout сохраняются;
- CI проходит на актуальном `main`.

### Ограничения

- production rollout и замена `KRITA_SERVER_IMAGE` не входят в этот PR;
- опубликованный base должен иметь явную политику обновления и rollback;
- нельзя использовать плавающий `latest` как production или CI dependency;
- нельзя ослаблять container/security checks ради сокращения времени.

## После завершения

Заполняется после реализации и полного CI.
