# 2026-08-06 — hotfix callback пропорций GPT Image 2

- Дата: 2026-08-06
- ID: `gpt-image-ratio-callback-hotfix`
- Линия/фаза: Ауф · GPT Image 2 · production hotfix
- Статус: частично
- Ветка: `fix/gpt-image-ratio-callback`
- Базовый commit: `2b43562f67ea167e47a4167432bb9c07e484580d`

## Перед началом

### Цель

Устранить production-ошибку aiogram при открытии выбора соотношения сторон GPT Image 2.

### Исходный контекст

Ошибка #100 показала `ValueError: Separator symbol ':' can not be used in value value='1:1'`. GPT Image 2 передавал `1:1`, `9:16` и другие пропорции напрямую в поле `AufCallback.value`, хотя стандартный separator aiogram для CallbackData тоже равен `:`.

### Планируемый объём

- переиспользовать существующее callback-безопасное кодирование пропорций;
- кодировать только `gpt2_ratio` при построении кнопок;
- декодировать значение до передачи обработчику GPT Image 2;
- добавить регрессию для всей клавиатуры GPT Image 2.

### Критерии готовности

- клавиатура пропорций GPT Image 2 строится без `ValueError`;
- callback payload не содержит исходную пропорцию с двоеточием;
- обработчик получает исходные значения `1:1`, `9:16`, `21:9`;
- полный CI зелёный.

### Риски и ограничения

- изменение затрагивает глобальный `AufCallback.unpack`, поэтому ограничено только действием `gpt2_ratio`;
- callback prefix и separator не меняются, чтобы не сломать уже отправленные Telegram-кнопки;
- live provider generation не выполняется в CI и остаётся production acceptance после доставки;
- отдельная неисправность `hermes-coders.service` с pinned sandbox image не относится к этому UI hotfix.

## После завершения

### Фактически сделано

- существующий `auf_photo_ratio_callback_fix` расширен на действие `gpt2_ratio`;
- GPT Image 2 использует кодирование `1:1 → 1x1` при упаковке;
- `AufCallback.unpack` восстанавливает provider-facing значение до обработки;
- добавлен async regression test, который строит реальную клавиатуру, распаковывает все callbacks и сверяет полный набор пропорций;
- reviewed architecture fingerprints и generated package inventory синхронизированы;
- временный inventory workflow удалён из итоговой ветки.

### Миграции и совместимость

Миграций базы нет. Prefix, separator и общая структура `AufCallback` не меняются. Старые callback других действий не затрагиваются.

### Проверки

- type check на промежуточном head: PASS;
- четыре PostgreSQL test shards на промежуточном head: PASS;
- focused package architecture inventory contract после регенерации: PASS;
- focused GPT Image ratio regression входит в зелёный test shard;
- полный обязательный CI перезапущен на финальном пользовательском commit после generated inventory commit.

### PR и commit

- PR: `#650 Fix GPT Image 2 ratio callback packing`;
- ветка: `fix/gpt-image-ratio-callback`;
- generated inventory head: `c54d295382d297e003a00e3c2c01451f5649390b`;
- итоговый merge commit будет записан после зелёного CI и merge.

### Незавершённое

- дождаться полного CI на финальном head;
- слить PR #650;
- развернуть обновлённый `main` на production;
- повторить живой путь GPT Image 2 до выбора пропорции.

### Следующий шаг

Дождаться зелёных обязательных проверок, слить PR #650 и выполнить штатный server deploy без ручного изменения production checkout.
