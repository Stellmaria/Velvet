# Ауф: публичный edit-or-answer contract

## Причина

Ауф routers и runtime installers импортировали и переназначали private `_edit_or_answer` из `workspace_auf`. Из-за этого callback editing, media fallback и GRS sanitization зависели от скрытого cross-module contract и порядка runtime patches.

## Что изменено

- добавлен общий callback edit-or-answer helper в `presentation.telegram.shared.editing`;
- добавлен публичный Ауф adapter с text-transform hook;
- Ауф photo/GRS routers и installers переведены с private `_edit_or_answer` на публичный contract;
- сохранены callback acknowledgement, fallback для media-сообщений, обработка `message is not modified` и GRS text sanitization;
- добавлен AST regression, запрещающий возврат внешних private `_edit_or_answer` imports и assignments;
- feature-срез перенесён поверх актуального `main` без отката исправлений рекурсии, пользовательской валюты и списаний.

## Проверки

- shared contract inventory и navigation inventory обновлены;
- focused tests для Ауф editing, shared helpers и GRS delegation входят в PR;
- полный GitHub Actions CI обязателен перед merge.

## Связанные задачи

- #419
- #213
