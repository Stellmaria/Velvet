# Инвентаризация repository layout Velvet

Машинный baseline P3E для постепенного выравнивания persistence и корневых модулей без изменения поведения.

## Сводка

- repository-модулей: **31**;
- внутри доменов: **27**;
- в `velvet_bot/repositories`: **1**;
- корневых `*_repository.py`: **3**;
- infrastructure repositories: **0**;
- прочих repository paths: **0**;
- repository-модулей с production consumers: **27**;
- repository-модулей с package exports: **25**;
- repository-модулей без runtime consumers: **4**;
- repository-модулей без любых references: **0**;
- корневых Python-модулей: **113**.

## Категории корневых модулей

- other: **100**;
- report: **4**;
- repository: **3**;
- runtime: **4**;
- service: **1**;
- worker: **1**;

## Кандидаты для первых P3E-срезов

| Module | Layout | Production | Tests | Package exports | References |
|---|---:|---:|---:|---:|---:|
| `velvet_bot.reference_comparison_repository` | root | 1 | 1 | 0 | 2 |
| `velvet_bot.media_set_actions_repository` | root | 1 | 1 | 0 | 3 |
| `velvet_bot.media_set_ai_repository` | root | 1 | 1 | 0 | 3 |
| `velvet_bot.repositories.system_repository` | central | 2 | 2 | 1 | 5 |

## Repository modules

### domain

- `velvet_bot.domains.archive.preview_repository` · domain `archive`: production 4, tests 1, exports 1, refs 6.
- `velvet_bot.domains.archive.repository` · domain `archive`: production 1, tests 1, exports 1, refs 3.
- `velvet_bot.domains.characters.repository` · domain `characters`: production 1, tests 0, exports 1, refs 2.
- `velvet_bot.domains.discussions.activity_repository` · domain `discussions`: production 2, tests 0, exports 1, refs 3.
- `velvet_bot.domains.discussions.ingest_repository` · domain `discussions`: production 1, tests 0, exports 1, refs 2.
- `velvet_bot.domains.discussions.insight_repository` · domain `discussions`: production 2, tests 0, exports 1, refs 3.
- `velvet_bot.domains.discussions.post_insight_repository` · domain `discussions`: production 2, tests 0, exports 1, refs 3.
- `velvet_bot.domains.discussions.ranking_repository` · domain `discussions`: production 2, tests 0, exports 1, refs 3.
- `velvet_bot.domains.discussions.relink_repository` · domain `discussions`: production 2, tests 0, exports 1, refs 3.
- `velvet_bot.domains.discussions.repository` · domain `discussions`: production 1, tests 0, exports 1, refs 2.
- `velvet_bot.domains.media_quality.repository` · domain `media_quality`: production 2, tests 0, exports 1, refs 3.
- `velvet_bot.domains.media_quality.reset_repository` · domain `media_quality`: production 1, tests 1, exports 0, refs 2.
- `velvet_bot.domains.media_rework.repository` · domain `media_rework`: production 0, tests 0, exports 1, refs 1.
- `velvet_bot.domains.media_sets.ai_repository` · domain `media_sets`: production 1, tests 1, exports 1, refs 3.
- `velvet_bot.domains.media_sets.duplicate_actions_repository` · domain `media_sets`: production 0, tests 1, exports 1, refs 2.
- `velvet_bot.domains.media_sets.quality_repository` · domain `media_sets`: production 1, tests 1, exports 0, refs 2.
- `velvet_bot.domains.media_sets.repository` · domain `media_sets`: production 0, tests 0, exports 1, refs 1.
- `velvet_bot.domains.public_archive.repository` · domain `public_archive`: production 1, tests 0, exports 1, refs 2.
- `velvet_bot.domains.public_archive.watermark_repository` · domain `public_archive`: production 4, tests 1, exports 0, refs 5.
- `velvet_bot.domains.publication.draft_repository` · domain `publication`: production 2, tests 1, exports 1, refs 4.
- `velvet_bot.domains.publication.repository` · domain `publication`: production 6, tests 1, exports 1, refs 8.
- `velvet_bot.domains.publication.validation_repository` · domain `publication`: production 2, tests 1, exports 1, refs 4.
- `velvet_bot.domains.references.repository` · domain `references`: production 1, tests 0, exports 1, refs 2.
- `velvet_bot.domains.stories.repository` · domain `stories`: production 1, tests 0, exports 1, refs 2.
- `velvet_bot.domains.telegram_storage.backup_repository` · domain `telegram_storage`: production 0, tests 1, exports 1, refs 2.
- `velvet_bot.domains.telegram_storage.repository` · domain `telegram_storage`: production 3, tests 0, exports 1, refs 4.
- `velvet_bot.domains.watermark.repository` · domain `watermark`: production 5, tests 1, exports 1, refs 7.

### central

- `velvet_bot.repositories.system_repository`: production 2, tests 2, exports 1, refs 5.

### root

- `velvet_bot.media_set_actions_repository`: production 1, tests 1, exports 0, refs 3.
- `velvet_bot.media_set_ai_repository`: production 1, tests 1, exports 0, refs 3.
- `velvet_bot.reference_comparison_repository`: production 1, tests 1, exports 0, refs 2.

## Следующий срез

- фаза: **P3E**;
- цель: **migrate the first low-coupling repository module**;
- первый кандидат: `velvet_bot.reference_comparison_repository`;
- стратегия: move one reviewed module to its domain or infrastructure boundary, keep the old path as a temporary facade, and migrate consumers before deletion.

## Правило обновления

```bash
python scripts/inventory_repository_layout.py --write --label <phase>
python scripts/inventory_repository_layout.py --check --label <phase>
```
