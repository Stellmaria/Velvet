---
name: orchestrated-task
description: Выполнить одну задачу Каэля в правильном repository и вернуть schema-bound инженерный результат.
version: 1.0.0
author: Velvet
---

# Orchestrated task

1. Проверь task ID, target repository, acceptance criteria и запреты.
2. Прочитай global и repository AGENTS, актуальные project notes и `git status`.
3. Если repository не совпадает с compiled Entity ID, остановись как `blocked`.
4. Создай одну feature branch, внеси минимальное изменение, обнови обязательные
   project notes и запусти релевантные проверки.
5. Проверь diff и secrets, создай не более одного PR. Не merge и не deploy.
6. Верни только JSON по установленной output schema; пустые branch/PR/blocker
   обозначай пустой строкой.
