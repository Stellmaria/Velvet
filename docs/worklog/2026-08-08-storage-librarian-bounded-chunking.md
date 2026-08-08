# Storage Librarian bounded hierarchical chunking

- Дата: 2026-08-08
- ID: `2026-08-08-storage-librarian-bounded-chunking`
- Линия/фаза: Storage Librarian / production oversized-text hardening
- Статус: `частично`
- Ветка: `fix/storage-librarian-bounded-chunking`
- Базовый commit: `c01c5d697200edc308061ed3744dfefd99808b60`
- PR: `#736 Add bounded hierarchical Storage Librarian chunking`

## Перед началом

### Цель

Снять terminal failure для текстовых Storage объектов, которые лишь или существенно превышают single-shot prompt envelope, не вводя silent truncation, cloud fallback или неограниченную CPU-нагрузку на локальный Ollama.

### Исходный контекст

После production rollout stale-running recovery и full-archive scheduler локальный Ollama pipeline успешно завершал новые analyses, но oversized text оставался намеренно terminal: `Storage Librarian text input exceeds the configured bounded source limit`.

Production text runtime использует `text_context_length=12288`, `text_max_output_tokens=768` и effective `max_text_chars=18944`. Из известных terminal failures:

- Storage `#39` `codex-1c43fb8dd374.zip`: extracted text около 19514 chars, то есть лишь примерно на 570 chars больше single-shot limit;
- Storage `#41` `supervisor.log`: около 202467 chars;
- Storage `#42` `velvet.log`: около 3932555 chars.

Многомегабайтные diagnostics нельзя безусловно прогонять через десятки или сотни локальных inference calls: это превратило бы архивный scheduler в CPU-нагрузочный тест, что едва ли достойная карьера для библиотекаря.

### Планируемый объём

- сохранить существующий single-shot path для источников, помещающихся в bounded prompt envelope;
- извлекать oversized text без silent source truncation до отдельного hard chunk-plan cap;
- делить source на deterministic contiguous chunks с полной и проверяемой реконструкцией исходного текста;
- анализировать chunks последовательно через существующий local Ollama analysis client;
- после chunk summaries делать один bounded final synthesis;
- ограничить число chunks, общий chunkable source объём и общее число inference calls;
- terminally reject source до inference, если hard chunk-plan budget превышен;
- не добавлять cloud fallback и terminally reject analysis result не от Ollama;
- не менять retry/enqueue policy для historical failed jobs и не сбрасывать attempts/history;
- не менять Arthur auto-enqueue policy;
- оставить `done_reason=length`, deploy/full-archive config drift и manual target-claim race отдельными follow-up задачами.

### Критерии готовности

- объект чуть больше single-shot limit проходит через несколько ordered chunks без потери хвоста source;
- large diagnostics порядка 200k chars укладывается в bounded hierarchical plan;
- multi-megabyte diagnostics получает deterministic terminal hard-cap failure до model inference;
- каждый chunk source envelope помещается в текущий bounded prompt budget;
- final synthesis также bounded;
- chunk ordering deterministic и `join(chunks) == source`;
- общий inference budget конечен и проверяется до первого chunk call;
- analysis path использует только analyzer `ollama`, без fallback;
- required GitHub CI зелёный до squash merge в protected `main`.

### Риски и ограничения

Hierarchical synthesis неизбежно работает по bounded summaries отдельных chunks, поэтому качество итоговой сводки зависит от того, насколько chunk summaries сохраняют material facts. Original source при chunk planning не обрезается: bounded reduction применяется только на промежуточном summary layer перед final synthesis.

Default hard limits намеренно консервативны: 12 chunks, максимум 220000 source chars и максимум 13 inference calls включая final synthesis. При production envelope `18944` chunk payload дополнительно резервирует 512 chars под chunk metadata, поэтому theoretical 12-chunk capacity остаётся bounded.

Historical jobs, уже имеющие status `failed`, этот PR автоматически не пере-enqueue. Analyzer version намеренно не повышается только ради принудительного historical replay. Отдельная migration/retry policy потребуется, если владелец решит повторно обработать такие объекты после production acceptance.

Arthur остаётся manual-first; этот PR не меняет `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` для Arthur и не добавляет отдельного archive worker.

## После завершения

### Фактически сделано

- существующий single-shot analysis path сохранён для source, который помещается в `max_text_chars`;
- oversized source получает deterministic contiguous chunk plan без silent truncation исходного текста;
- ZIP extraction больше не режет поддерживаемый текст по single-shot char limit: превышение entry/uncompressed bounds становится явной terminal ошибкой вместо тихого пропуска;
- введены bounded defaults: максимум 12 chunks, 220000 source chars и 13 inference calls с final synthesis;
- chunk analysis выполняется строго последовательно через существующий analysis client;
- перед каждым analysis result проверяется `analyzer == "ollama"`; иной analyzer приводит к terminal failure без fallback;
- final synthesis строится из ordered bounded chunk summaries и также помещается в текущий source envelope;
- hierarchical run агрегирует prompt/completion usage, число chunks и число inference calls;
- analyzer version намеренно оставлен прежним, чтобы этот PR сам по себе не инициировал historical replay;
- добавлены regression tests для slightly-oversized Codex ZIP, большого diagnostics source, hard-cap rejection, deterministic lossless ordering, inference budget и local-Ollama-only contract.

### Миграции и совместимость

SQL migration не требуется. Схема `telegram_storage_analysis_jobs` и `telegram_storage_analysis` не меняется, attempts/history не сбрасываются и persistence semantics остаются прежними.

Historical jobs со status `failed` автоматически не пере-enqueue. Повторный запуск таких объектов после production acceptance требует отдельной явной retry/migration policy.

Arthur configuration и scheduler ownership не меняются. В частности, этот PR не включает Arthur auto-enqueue и не меняет требование `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` для Arthur.

Новые chunk limits имеют безопасные defaults и могут быть ограничены env-переменными; existing single-shot env contract остаётся совместимым.

### Проверки

- Python syntax compile изменённых production modules и нового regression test пройден локально;
- production prompt-envelope arithmetic проверена для `12288/768`: chunk prompt с wrapper остаётся ниже Ollama hard guard;
- source порядка `202467` chars раскладывается в 11 ordered chunks и требует 12 inference calls включая synthesis, то есть укладывается в defaults;
- final synthesis с worst-case bounded chunk summaries проверен на размер не больше `18944` chars;
- project-notes contract после заполнения worklog прошёл;
- type check на implementation head прошёл;
- GitHub Python 3.13 runner сгенерировал canonical package architecture inventory для первоначальной ветки и не выявил новых architecture violations;
- все четыре full test shards на inventory probe head прошли успешно;
- после продвижения `main` до `3a08f99ab725a0190a0ef980cb013f577495a0c4` изменения PR #735 были влиты в feature branch обычным merge commit без force-push;
- combined canonical package architecture inventory после sync с `main`: `production_loc=145945`, `violation_count=523`;
- PR снова mergeable и синхронизирован с `main`; generated inventory и package architecture contract соответствуют объединённому дереву;
- временные CI probe/sync-helper workflow-файлы удалены; итоговый PR diff содержит только восемь ожидаемых production/test/docs/inventory файлов;
- полный required GitHub CI должен пройти на точном финальном head после этой записи до squash merge.

### PR и commit

PR: `#736 Add bounded hierarchical Storage Librarian chunking`.

Ветка: `fix/storage-librarian-bounded-chunking`.

Первый implementation commit: `a13df7b994dc2e223abe9a3711c27dad39d2a961` (`Add bounded Storage Librarian chunking`). Main sync merge commit: `2ba551787b47073899c130b99eaeb9c819be09d3`, второй родитель `3a08f99ab725a0190a0ef980cb013f577495a0c4`. Combined canonical architecture inventory после sync сохранён GitHub runner commit `29413322dd5d870f6ee79ca3f1ab4de977cefb40`. Финальный PR head и squash merge SHA фиксируются после required CI.

### Незавершённое

- дождаться всех required GitHub CI checks на точном финальном PR head;
- выполнить squash merge обычным protected workflow без bypass/force-push;
- после merge отдельно зафиксировать canonical source SHA, immutable GHCR image digest и OCI revision;
- выполнить production acceptance на oversized object, не переименовывая historical failure в success задним числом;
- `done_reason=length`, deploy/full-archive config drift и manual `/storage_analyze ID` target-claim race остаются отдельными follow-up defects.

### Следующий шаг

Прогнать required CI на финальном PR head, исправить только доказанные проверки, затем squash-merge PR #736 в protected `main`. Production state и historical failed objects не считать исправленными до exact-image rollout и runtime acceptance.
