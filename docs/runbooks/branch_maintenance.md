# Runbook: безопасное обслуживание feature-веток

## Назначение

Workflow `branch maintenance` применяет один уже проверенный single-parent commit к существующей непротектированной ветке. Он не заменяет обычный pull request и не используется для изменения `main`.

Подход нужен только для детерминированного обслуживания ветки, когда изменение уже существует отдельным commit и повторное создание giant runner-PR не добавляет review value.

## Когда использовать

Используйте maintenance workflow, если одновременно выполняются условия:

- source commit уже проверен отдельно и содержит один ограниченный change;
- target является существующей веткой с префиксом `agent/`, `feature/`, `fix/`, `chore/` или `maintenance/`;
- известен точный текущий SHA target-ветки;
- source является обычным single-parent commit, а не merge commit;
- требуется обычный fast-forward push после полного test suite.

Для нового source change, изменения `main`, разрешения конфликтов или объединения нескольких commits создаётся обычный pull request.

## Входные параметры

- `action`: только `cherry-pick`;
- `target_branch`: allowlisted непротектированная ветка;
- `expected_target_sha`: полный 40-символьный SHA target до запуска;
- `source_commit_sha`: полный 40-символьный SHA проверенного commit.

SHA нельзя брать из старого сообщения или локального cache. Перед запуском нужно открыть target-ветку в GitHub и сверить её текущий head.

## Что делает workflow

1. Проверяет action, формат ветки и оба SHA.
2. Запрещает `main`, `master`, path traversal и неоднозначные branch names.
3. Проверяет, что target всё ещё указывает на `expected_target_sha`.
4. Проверяет, что source является single-parent commit.
5. Выполняет `cherry-pick --no-commit` как dry-run.
6. Публикует changed files и diff stat в workflow summary.
7. Запускает полный `python -m unittest discover -s tests -v` с PostgreSQL 16.
8. Повторно проверяет target SHA непосредственно перед записью.
9. Создаёт audit commit с source SHA и workflow run ID.
10. Выполняет обычный push без force и сохраняет evidence artifact на семь дней.

## Идемпотентность

Повторный запуск не создаёт duplicate commit, если source уже является предком target или его patch уже присутствует. В этом случае workflow завершится как no-op и зафиксирует причину в summary.

Если target изменился во время запуска, workflow завершится без push. Запускать его повторно можно только после повторной проверки нового target SHA.

## Конфликты и ошибки

Workflow не разрешает конфликты автоматически. При конфликте cherry-pick, падении тестов, неверном SHA или сетевом сбое target не изменяется.

После неуспешного запуска:

1. прочитайте workflow summary и test artifact;
2. не повторяйте запуск со старым `expected_target_sha` вслепую;
3. исправьте source change обычным PR или новым reviewed commit;
4. повторно проверьте target head;
5. создайте новый maintenance run с актуальными SHA.

## Запрещённые сценарии

- PR с пометкой «не сливать», созданный только ради mutation другой ветки;
- direct mutation `main` или `master`;
- force-push и `--force-with-lease`;
- merge/rebase target с автоматическим разрешением конфликтов;
- hard-coded workflow для одной временной feature-ветки;
- source merge commit или диапазон commits;
- запуск без owner-visible target SHA, source SHA, diff plan и resulting commit.

## Audit trail

В одном workflow run должны быть видны:

- action и target branch;
- expected и фактический target SHA;
- source commit и subject;
- changed files и diff stat;
- результат полного test suite;
- resulting commit либо явный no-op;
- evidence artifact для диагностики.
