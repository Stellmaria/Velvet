---
name: hermes-reconcile
description: Обновить фиксированные Hermes-компоненты после слитого PR через безопасный asynchronous reconcile gateway.
version: 1.0.0
author: Velvet
---

# Hermes reconcile

1. Убедись, что нужный PR слит, checks зелёные и владелец разрешил rollout.
2. Выбери только `coders`, `librarian`, `entities` либо `all`.
3. Вызови `reconcilectl.py submit TARGET`, сразу сообщи task ID.
4. Следи через `status`/`wait`; `accepted`, `queued` и `running` не являются
   успехом.
5. После `completed` выполни профильный health/smoke из операционного контракта.

Не меняй порядок `all`, payload, unit names или installer paths.
