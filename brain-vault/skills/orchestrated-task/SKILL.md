---
name: orchestrated-task
description: Выполнить одну tier-aware задачу Каэля в правильном repository и вернуть schema-bound инженерный результат.
version: 1.1.0
author: Velvet
---

# Orchestrated task

1. Проверь task ID, target repository, acceptance criteria, запреты и routing metadata: `task_type`, `requested_tier`, `risk`, `mutation_policy`.
2. Не переклассифицируй tier после handoff и не понижай его ради доступной модели. `Terra → Luna` для standard/complex запрещён.
3. Прочитай global и repository AGENTS, актуальные project notes и `git status`.
4. Если repository не совпадает с compiled Entity ID, остановись как `blocked`.
5. Если `mutation_policy=read_only`, не меняй Git, файлы и workspace. Любая обнаруженная mutation делает результат недействительным.
6. Для `workspace_pr` создай одну feature branch, внеси минимальное изменение, обнови обязательные project notes и запусти релевантные проверки.
7. При `degraded_execution=true` или `review_required=true` явно перечисли риски, дополнительные проверки и ограничения решения.
8. Проверь diff и secrets, создай не более одного PR. Не merge, не deploy и не обращайся к live production.
9. Верни только JSON по установленной output schema; пустые branch/PR/blocker обозначай пустой строкой.
