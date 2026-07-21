# Сессия: Workspace archive isolation

- Дата: 2026-07-21
- ID: `2026-07-21-workspace-archive-isolation`
- Линия/фаза: multi-workspace archive isolation
- Статус: `выполняется`
- Ветка: `agent/workspace-archive-isolation`
- Базовый commit: `157ddb7dcfd1513455649eea5bdfe81eb3c413b3`

## Перед началом

### Цель

Продолжить multi-workspace реализацию после PR #275: изолировать приватный и публичный архив по `workspace_id`, добавить безопасный выбор активного пространства и подготовить базовый мастер подключения пользовательских Telegram-каналов.

### Исходный контекст

Workspace foundation уже хранит пространства, участников, настройки и каналы, а персонажи ограничены `workspace_id`. Архивные, публичные и Telegram application boundaries всё ещё используют только `character_id` либо глобальные настройки, поэтому внешний пользовательский интерфейс пока намеренно отключён.

### Планируемый объём

- workspace scope для archive repository/service;
- workspace scope для public archive repository/service;
- проверка принадлежности персонажа до чтения и изменения медиа;
- активное пространство пользователя без доступа к чужим workspace;
- базовый channel connection service с проверкой роли владельца/администратора;
- regression и PostgreSQL isolation tests;
- сохранение текущего Velvet поведения через workspace `1` по умолчанию.

### Критерии готовности

- пользователь не может открыть архив персонажа другого workspace по известному `character_id`;
- public archive выдаёт категории, персонажей и медиа только активного workspace;
- owner/admin может менять каналы только своего workspace;
- текущие команды Стэл продолжают работать без изменения интерфейса;
- tests, restore drill, type-check, Docker и project notes зелёные.

### Риски и ограничения

Эта фаза не должна включать внешний интерфейс раньше завершения всех read/write guards. Stories, references, publications, Qwen и analytics могут остаться отдельными следующими срезами, но архивные маршруты не должны иметь обхода через прямой ID.

## После завершения

Заполняется после реализации и проверок.
