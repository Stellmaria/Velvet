# Codex rate-limit probe repair

- Дата: 2026-08-06
- ID: codex-rate-limit-probe-20260806
- Линия/фаза: Hermes Coder / subscription observability repair
- Статус: завершено
- Ветка: fix/codex-rate-limit-probe
- Базовый commit: 0022b7404b9419ed73869f4a4e9c6a3d53bd8bd8
- Синхронизировано с main: 57ac75c4dc1681b360882c5d2a43089eb7414eff

## Перед началом

### Цель

Исправить `GET /v1/rate-limits`, который возвращал HTTP 500 во внутреннем Codex runner и преобразовывался orchestration router в HTTP 502 с бесполезным сообщением `Internal runner error: RuntimeError`.

### Исходный контекст

- GPT Image 2 generation через тот же Codex runtime продолжала работать;
- production diagnostics содержали только временные PostgreSQL DNS errors во время пересоздания Compose network и не содержали Hermes rate-limit traceback;
- probe запускал `codex app-server --stdio` и читал JSONL через `selectors` вместе с буферизованным `TextIOWrapper.readline()`;
- stderr app-server отбрасывался, поэтому реальная причина сбоя терялась;
- Codex может возвращать недельное окно в provider slot `primary` без отдельного короткого окна.

### Планируемый объём

- заменить text-mode reader на unbuffered binary JSONL reader;
- читать все готовые строки из userspace buffer до следующего `select()`;
- сохранять ограниченный stderr tail и редактировать секреты;
- возвращать осмысленную sanitized причину через HTTP 502;
- классифицировать короткое и недельное окна по длительности;
- добавить bounded retry и focused regression;
- не менять GPT Image generation, task routing, credentials или production database.

### Критерии готовности

- два JSONL-ответа, записанные app-server одним системным write, читаются без timeout;
- weekly-only bucket попадает в long-window slot;
- swapped provider slots сортируются по `windowDurationMins`;
- bearer material не появляется в ошибках;
- persistent probe failure преобразуется в `RunnerError` со статусом HTTP 502;
- focused tests, compilation и полный protected CI проходят до merge.

### Риски и ограничения

- live production probe невозможно подтвердить только fake app-server test;
- provider может изменить JSON-RPC schema, поэтому неизвестный формат остаётся fail-closed;
- stderr ограничивается хвостом и проходит redaction;
- production rollout требует отдельного Hermes coder release, обычный bot deploy недостаточен;
- текущая Codex authentication и image-generation route не изменяются.

## После завершения

### Фактически сделано

- pipe app-server переведён на `text=False`, `bufsize=0` и явный `bytearray` JSONL buffer;
- complete lines сначала извлекаются из уже накопленного buffer, затем вызывается selector;
- чтение stdout и stderr выполняется через `os.read`;
- stderr tail ограничен и проходит `redact_text`;
- JSON-RPC error сохраняет request name, code и sanitized message;
- bounded probe повторяется один раз после transient failure;
- provider windows классифицируются по длительности, а lone day-or-longer bucket публикуется как long window;
- `CodexManager.rate_limits()` преобразует persistent failure в HTTP 502 `RunnerError` с полезной sanitized причиной;
- README документирует transport, semantic mapping и failure contract.

### Миграции и совместимость

- database migrations отсутствуют;
- HTTP success payload сохраняет существующие поля `plan_type`, `primary`, `secondary` и `rate_limit_reached_type`;
- bot-side consumer и GPT Image task payload не изменяются;
- short window может быть `null`, когда provider возвращает только недельный bucket;
- branch синхронизирована с current main `57ac75c4dc1681b360882c5d2a43089eb7414eff` без конфликтов.

### Проверки

- fake Codex app-server отдаёт `account/read` и `account/rateLimits/read` одним `os.write`;
- `python -m unittest tests.test_codex_runner_rate_limits`: 4 tests passed;
- проверены weekly-only normalization, duration ordering, secret redaction и HTTP 502 mapping;
- `python -m compileall -q deploy/hermes-coders/codex_runner.py tests/test_codex_runner_rate_limits.py` прошёл;
- temporary patch workflow удалён из итогового дерева;
- итоговый diff против current main содержит только runner, README, regression test и эту worklog entry;
- полный protected CI является последним merge gate PR #660.

### PR и commit

- PR: #660 `Fix Codex subscription rate-limit probe`;
- ветка: `fix/codex-rate-limit-probe`;
- проверенный implementation commit: `aeafba96f2ec52b748d7e7e998a3591b06bad142`;
- current-main merge commit: `bc6c96004c2a0e077464f6e0a2e99ac18ea09115`;
- итоговый exact head и squash merge commit фиксируются GitHub после зелёных required checks.

### Незавершённое

- production Hermes coder release;
- live authenticated `GET /v1/rate-limits` smoke через orchestration router;
- подтверждение отображения доступного короткого и недельного окна в следующей GPT Image 2 task card.

### Следующий шаг

Дождаться полного exact-head CI, выполнить squash merge PR #660, затем развернуть Hermes coder release и проверить live rate-limit endpoint без вывода credentials.
