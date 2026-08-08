# Storage Librarian bounded hierarchical chunking

- Дата: 2026-08-08
- ID: `2026-08-08-storage-librarian-bounded-chunking`
- Линия/фаза: Storage Librarian / production oversized-text hardening
- Статус: `в работе`
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

Заполняется после required CI, squash merge и production acceptance. До этого статусы oversized historical objects нельзя считать исправленными в production только потому, что код PR существует.
