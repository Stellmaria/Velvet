# Сессия: единый Hermes Brain Vault

- Дата: `2026-08-02`
- ID: `hermes-brain-vault-20260802`
- Линия/фаза: `server operations / Hermes cognition and entity coordination`
- Статус: `частично`
- Ветка: `feat/hermes-brain-vault`
- Базовый commit: `a564e0c05d0f8ddef82f8346d13cd14a5eaa0113`

## Перед началом

### Цель

Связать личности, операционные правила, короткую и долговременную память,
skills и выбранный проектный контекст Каэля, Velvet Librarian, Velvet Coder и
Макса через единый Obsidian-compatible Markdown Vault. Каэль остаётся главным
диспетчером, а каждая подчинённая сущность получает только собственный
изолированный context pack.

### Исходный контекст

- Hermes загружает `SOUL.md` только из `HERMES_HOME`, а проектный контекст —
  относительно рабочего каталога.
- runtime Каэля устанавливает `/opt/data/AGENTS.md`, но source config не
  закрепляет `terminal.cwd: /opt/data`, поэтому загрузка контракта не доказана.
- legacy Hermes coder получает generated `.hermes.md`, но активный Codex runner
  использует отдельные `CODEX_HOME`/workspace и не получает `SOUL.*.md` либо
  `AGENTS.*.md` из Hermes-профиля.
- репозиторий Max не содержит собственного корневого `AGENTS.md`, поэтому его
  активный Codex особенно зависит от отдельного controller-managed контракта.
- Velvet Librarian намеренно имеет deny-all tool contract; свободный file write
  ему выдавать нельзя.
- встроенная Hermes memory ограничена и является frozen snapshot одной сессии,
  поэтому полная база знаний не должна инжектироваться в prompt или храниться
  только в `MEMORY.md`.

### Планируемый объём

- добавить versioned Obsidian-compatible `brain-vault` без секретов и runtime
  state;
- определить entity registry, access matrix, memory/context/cache policies,
  task handoff и memory proposal contracts;
- реализовать детерминированную проверку и компиляцию entity context packs;
- устанавливать Каэлю `SOUL.md`, `AGENTS.md`, bounded memory seeds, skills и
  `context-manifest.json`;
- устанавливать отдельные global `AGENTS.md` и skills активным Codex-профилям
  Velvet и Max;
- сохранить legacy Hermes chat coder и Librarian isolation;
- добавить runtime smoke, который проверяет не только наличие файлов, но и
  role/project sentinels и manifest hashes;
- закрепить `/opt/data` как cwd Каэля и включить безопасные compression/loop
  guardrails без расширения инструментов;
- обновить документацию и tests.

### Критерии готовности

- Vault проходит schema, path, size, secret-pattern и cross-project validation;
- compilation дважды даёт одинаковый результат и content hashes;
- Каэль получает только `kael` profile, Velvet/Max — только свои profile packs;
- Max Codex имеет полный controller-managed `AGENTS.md`, даже если upstream repo
  не содержит корневой инструкции;
- Librarian не получает terminal/file/memory/skills либо произвольный writer;
- существующие Docker/systemd/DB/secret isolation contracts не ослаблены;
- focused tests, Bash syntax, Python compilation, project notes contract и
  доступный полный CI проходят;
- PR слит только после зелёных обязательных checks.

### Риски и ограничения

- Obsidian является редактором и долговременной Markdown-базой, но не runtime
  очередью или secrets store.
- memory seeds создаются только при отсутствии существующей runtime memory и не
  должны уничтожать уже накопленные записи.
- context compilation не даёт Каэлю root, Docker socket, systemd API,
  production `.env` либо право direct push/merge.
- live доказательство реальной prompt assembly и server rollout выполняется
  после merge через отдельный разрешённый reconcile; CI проверяет создаваемые
  context packs и runtime manifests.

### Допуск в режиме стабилизации

1. Изменение улучшает существующий Hermes operator/coder/Librarian контур.
2. Контекст становится воспроизводимым, изолированным и проверяемым по hash.
3. Новая пользовательская предметная область не создаётся.
4. Улучшение измеряется compiler tests, manifest checks и runtime smoke.
5. Границы проектов, read-only БД, deny-all Librarian и fixed-action operator
   сохраняются.

## После завершения

### Фактически сделано

- создан Obsidian-compatible `brain-vault` с четырьмя autonomous entity
  profiles и отдельным registry неагентных AI services;
- описаны context window, compression, stable-prefix cache, working/short/long
  memory, access matrix, handoff и memory proposal lifecycle;
- добавлены JSON schemas task handoff, Codex result и memory proposal;
- добавлены scoped skills Каэля и двух кодеров;
- реализован offline deterministic compiler с frontmatter/path/symlink/size/
  secret checks, 128 KB entity budget, cross-project validation и SHA-256
  manifests;
- реализованы безопасная установка и проверка активных Hermes/Codex packs;
- compiled и installed context закрыт owner-only режимами `0600/0700`, а
  verifier отклоняет group/other access;
- Codex global AGENTS теперь содержит SOUL, project rules и bounded memory,
  skills устанавливаются в отдельный HOME каждого проекта;
- Codex runner использует `--output-schema`, сохраняет structured result и
  возвращает legacy summary существующим клиентам;
- task handoff стал schema-shaped, memory candidates сохраняются в ledger;
- Каэль, chat coders и Librarian получают compression/loop guardrails;
- Librarian остаётся local-only deny-all и может только предложить memory;
- installer/preflight/live smoke расширены role/project/hash проверками;
- основной coder reconcile теперь устанавливает Hermes и существующие Codex
  context packs до обязательного preflight;
- обновлены README, canonical project memory/status и changelog.

### Миграции и совместимость

- SQL migrations и production data не менялись.
- Existing Codex auth/config/workspaces и Hermes task ledger сохраняются.
- Live `MEMORY.md`/`USER.md` не перезаписываются; seed создаётся только при
  отсутствии/пустом файле.
- Legacy `output` со строками STATUS/BRANCH/PR/TESTS/BLOCKER сохранён, а новый
  `structured_output` добавлен рядом.
- Velvet/Max GitHub, DB и network isolation не расширены.
- Server rollout намеренно не выполнялся из feature branch.

### Проверки

- `python deploy/hermes-brain/context_compiler.py validate` — OK, 4 entities,
  28 Vault files;
- compile/verify/install/installed-verify всех профилей в temporary directories
  — OK;
- `python -m py_compile deploy/hermes-brain/*.py deploy/hermes-coders/*.py
  deploy/hermes-librarian/prepare_profile.py deploy/hermes-operator/coder_router.py
  deploy/hermes-operator/coderctl.py` — OK;
- `bash -n deploy/hermes-entities/reconcile.sh
  deploy/hermes-coders/install-codex.sh deploy/hermes-librarian/install.sh` — OK;
- selected Hermes/Brain/runtime/orchestration/project-notes suite: 141 tests —
  OK;
- Bandit (`-lll -iii`), repository secrets/container/actions/locks/exceptions
  gates, `pip-audit --strict` и bounded mypy (11 files) — OK;
- test-shard plan для 415 test modules, `compileall`, `git diff --check` и project
  notes contract — OK;
- полный suite под доступным Python 3.12: 2162 tests, 2 failures, 6 errors,
  123 skipped. Изменённые Hermes tests прошли; оставшиеся результаты относятся к
  sandbox-запрету Unix sockets/chown/read-only home и к Python 3.13-specific AST
  fingerprints. Канонический CI использует Python 3.13 и ожидается до merge.

### PR и commit

- ветка: `feat/hermes-brain-vault`;
- PR: `#566` — `Unify Hermes entities with an Obsidian Brain Vault`;
- implementation commit на GitHub: `fb58679f7f4d14a3a733839dd577dc198197142f`;
- merge: только после зелёных обязательных checks.

### Незавершённое

- GitHub Python 3.13 full shards, ShellCheck, Docker builds и остальные
  обязательные PR checks;
- GitHub PR review/checks и merge;
- server pull/reconcile/restart;
- live Kael/chat/Codex/Librarian context/auth/health smoke.

### Следующий шаг

Дождаться обязательного GitHub CI и слить PR только при зелёном exact head.
После merge отдельным разрешённым rollout выполнить `reconcilectl all` и live
verification manifests без раскрытия credentials.
