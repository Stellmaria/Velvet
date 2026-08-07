# Сессия: Hermes AppArmor и Pillow mmap

- Дата: 2026-08-07
- ID: `2026-08-07-hermes-apparmor-pillow-mmap`
- Линия/фаза: Hermes / GPT Image 2 / production activation hotfix
- Статус: `частично`
- Ветка: `fix/hermes-apparmor-pillow-mmap`
- Базовый commit: `c4656fd792a29ea76094d337214b6baf96df5cf1`

## Перед началом

### Цель

Устранить production crash-loop обоих Hermes coder containers после добавления Pillow для 2K/4K image export, не расширяя AppArmor доступ за пределы Hermes virtualenv.

### Исходный контекст

Production успешно обновлён до `c4656fd792a29ea76094d337214b6baf96df5cf1`. Host-side runtime source guard, config reconciliation, coder preflight, sandbox preflight и Compose config/start проходят.

Оба coder container затем уходят в restart loop. Live logs показывают одинаковый traceback при импорте `PIL.Image`: нативный модуль `/opt/hermes/.venv/lib/python3.13/site-packages/PIL/_imaging...so` не может mmap executable segment и возвращает `failed to map segment from shared object`.

Контрольный запуск того же built image без runner AppArmor успешно импортирует системный Pillow из `/usr/lib/python3/dist-packages`, поэтому package/image исправны. Runner profile разрешает `mr` для `/usr/**`, `/lib/**`, `/lib64/**`, но для Hermes venv имеет только общий read rule `/** r`.

### Планируемый объём

- добавить только `mr` для `/opt/hermes/.venv/**` в `hermes-codex-runner`;
- не разрешать write или `ix` для Hermes venv;
- не добавлять широкий `/opt/** mr` или `/opt/hermes/** mr`;
- добавить regression contract на узкий mmap boundary;
- пройти protected CI до merge;
- после merge обновить production и повторить orchestration install.

### Критерии готовности

- AppArmor разрешает native extension mmap только внутри `/opt/hermes/.venv/**`;
- профиль сохраняет запрет записи и произвольного `ix` в venv;
- protected CI зелёный;
- production coder containers перестают restart-loop;
- `runtime_smoke.py`, provider smoke и router activation проходят.

### Риски и ограничения

Правило `m` разрешает memory-map файлов внутри Hermes venv как executable code, что необходимо CPython native extensions. Изменение не даёт write или execute-by-path (`ix`) и не распространяется на весь `/opt`.

## После завершения

### Фактически сделано

В `apparmor-hermes-codex-runner` добавлен узкий rule `/opt/hermes/.venv/** mr,`. Существующие `/usr/** mr`, `/lib/** mr`, `/lib64/** mr` сохранены. Другие `/opt` paths не получают mmap permission.

`tests/test_hermes_systemd_apparmor_contract.py` теперь требует exact venv rule и отдельно запрещает широкий `/opt/** mr`, `/opt/hermes/** mr`, write и `ix` для venv.

### Миграции и совместимость

SQL/config migrations нет. Изменяется только host AppArmor profile, который canonical sandbox launcher installer уже устанавливает через `apparmor_parser -r` перед activation coder services.

### Проверки

Protected CI требуется на финальном head. Production повторно не активируется до terminal green CI и merge exact reviewed head.

### PR и commit

- Ветка: `fix/hermes-apparmor-pillow-mmap`.
- AppArmor commit: `6da3aa1c1587806af8366863625e695633ef47f4`.
- Regression-test commit: `60c6b4465be2b90135994e606062a8f9be19fe98`.
- Документирующий commit создаётся этим изменением.

### Следующий шаг

После terminal green CI проверить `behind_by=0`, слить exact PR head, выполнить штатный `velvet update`, затем `sudo bash deploy/hermes-orchestration/install.sh`. Подтвердить active coders/router, provider smoke и bot-to-router DNS до включения Byesu image fallback.

### Незавершённое

- открыть PR;
- дождаться terminal protected CI;
- merge exact green head;
- rollout production;
- подтвердить live Pillow import под AppArmor и полный coder/router health;
- только затем включать Byesu image fallback и выполнять 1K/2K/4K GPT Image 2 smoke.
