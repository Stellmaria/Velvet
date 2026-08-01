# Сессия: фиксированный reconcile Hermes-инфраструктуры

- Дата: 2026-08-02
- ID: `hermes-fixed-reconcile-20260802`
- Линия/фаза: Hermes operator / production lifecycle
- Статус: `частично`
- Базовый commit: `0ad3e39e0607c55dc06fe4bdbb90ca3fdcaa779a`

## Перед началом

### Цель

Закрыть разрыв между обычным `opsctl velvet update` и обязательной переустановкой host/systemd частей Hermes после merge. Каэль должен уметь после отдельного разрешения владельца применить только заранее определённые installers для coder runtime, сущностей и Storage Librarian, не получая root, Docker socket, systemd API или произвольный shell.

### Исходный контекст

1 августа 2026 года GitHub `main` получил изменения сущностей, Librarian и runtime smoke кодеров. Обычный deployment Velvet не гарантирует переустановку этих host units. Поэтому код мог быть слит, а production продолжал работать на старой конфигурации.

Ручной SSH остаётся необходимым для каждого такого изменения. Это создаёт незамкнутый операторский цикл:

```text
merge → Velvet update → ручной sudo installer → ручной systemctl → smoke
```

Существующий `hermes-operator-host.service` намеренно имеет только непривилегированный fixed start и не должен расширяться до root/systemd.

### Границы

- не менять существующий start bridge;
- не передавать Каэлю root, sudo, Docker socket или systemd socket;
- не принимать shell, пути, service names, target SHA или произвольный payload;
- не выполнять Git fetch/checkout/reset/merge из reconcile;
- не считать `accepted` подтверждением успеха;
- не конфликтовать с параллельным PR #541, который меняет installers Storage Librarian и entities.

### План

- добавить отдельный root host bridge с фиксированным allowlist;
- добавить непривилегированный internal-only HTTP gateway;
- добавить `reconcilectl.py` в data directory Каэля;
- сделать задачи асинхронными, чтобы self-restart Каэля не прерывал host-операцию;
- хранить очищенный lifecycle последних задач;
- проверять clean `main` и совпадение `HEAD` с уже fetched `origin/main`;
- добавить installer, systemd units, документацию и contract tests.

## Выполнено

- создан `deploy/hermes-reconcile/host_reconcile.py`;
- разрешены только цели `coders`, `entities`, `librarian`, `all`;
- `all` выполняет фиксированный порядок `coders → librarian → entities`;
- submit возвращает `task_id` до начала installers;
- добавлены `status`, `wait` и `list`;
- состояние последних 100 задач хранится root-only и обновляется атомарно;
- queued/running задача после restart host bridge маркируется failed, а не выдаётся за продолжающуюся;
- добавлен отдельный HTTP gateway без published ports, Docker socket, production checkout и supervisor network;
- добавлен отдельный root systemd unit с hardening и фиксированным `/usr/local/libexec` entrypoint;
- добавлен installer, который сохраняет существующий operator token и создаёт отдельный reconcile token без вывода;
- обновлён операционный контракт Каэля;
- добавлены runtime и static contract tests.

## Проверки до PR

```text
python -m py_compile deploy/hermes-reconcile/host_reconcile.py
python -m py_compile deploy/hermes-reconcile/gateway.py
python -m py_compile deploy/hermes-reconcile/reconcilectl.py
bash -n deploy/hermes-reconcile/install.sh
python -m unittest tests/test_hermes_reconcile_contract.py -v
```

Локальный результат focused suite:

```text
13 passed
```

## Остаток

- создать PR и дождаться полного GitHub Actions CI;
- после merge вручную один раз выполнить `sudo bash deploy/hermes-reconcile/install.sh`;
- выполнить live smoke `submit coders`, проверить `AUTH_OK, PUSH_OK`;
- выполнить live smoke `submit entities` и подтвердить восстановление Каэля после self-restart;
- выполнить `submit librarian` и проверить manual-first команды;
- только после этого изменить статус с `частично` на production-ready.
