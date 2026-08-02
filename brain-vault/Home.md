---
id: velvet-brain-home
type: index
scope: shared
status: active
owner: kael
sensitivity: internal
version: 1
updated: 2026-08-02
---

# Velvet Brain

## Сущности

- [[brain-vault/entities/kael|Каэль]] — главный серверный оператор и диспетчер.
- [[brain-vault/entities/velvet-coder|Velvet Coder]] — инженер только Velvet.
- [[brain-vault/entities/max-coder|Макс]] — инженер только Romatic Club Max.
- [[brain-vault/entities/velvet-librarian|Velvet Librarian]] — local-only анализ и поиск.
- [[brain-vault/entities/ai-services|AI-сервисы]] — request-scoped модели без души и общей памяти.

## Общий протокол

- [[brain-vault/policies/context-lifecycle|Контекстное окно и сжатие]]
- [[brain-vault/policies/cache-policy|Кэш и стабильный префикс]]
- [[brain-vault/policies/memory-policy|Короткая и долговременная память]]
- [[brain-vault/policies/handoff-protocol|Передача задач и результатов]]
- [[brain-vault/policies/access-matrix|Границы доступа]]

## Проекты

- [[brain-vault/projects/velvet|Velvet]]
- [[brain-vault/projects/max|Romatic Club Max]]

## Принцип

Vault — долговременная память. Runtime prompt — ограниченная рабочая память.
Каэль маршрутизирует задачи и проверяет доказательства; кодеры изменяют код в
изолированных checkout; Librarian только анализирует переданный материал.
