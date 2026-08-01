# Сессия: read-only мониторинг host для Каэля

- Дата: 2026-08-02
- ID: `hermes-readonly-monitor-20260802`
- Линия/фаза: Hermes operator / host observability
- Статус: `частично`
- Ветка: `feat/hermes-readonly-monitor`
- Базовый commit: `056ea79c3fa4dcb66d574e206fea4d5f6b14565a`

## Перед началом

### Цель

Дать главному Каэлю полную безопасную картину состояния сервера, процессов, Docker runtime и локальных нейросервисов без permanent command allowlist, root, Docker socket, systemd API, process cmdline или произвольного shell.

### Исходный контекст

В постоянном `command_allowlist` Каэля обнаружены `script execution via -e/-c flag` и `git reset --hard`. Эти записи не подходят для серверного наблюдателя: первая практически универсальна внутри доступных прав, вторая уничтожает незакоммиченные изменения.

У Каэля уже есть фиксированные изменяющие контуры `opsctl` и `reconcilectl`, но нет общего read-only представления host ресурсов, всех контейнеров, systemd units, GPU, локальных моделей, процессов и warning/error journal.

### Планируемый объём

- создать отдельный root host bridge только для фиксированных read-only представлений;
- создать internal-only HTTP gateway без published ports и Docker socket;
- добавить `monitorctl.py` для Каэля;
- вернуть CPU, RAM, swap, disk, inode и uptime;
- вернуть безопасный Docker lifecycle без env, mounts, labels и command;
- вернуть фиксированный список важных systemd units;
- вернуть GPU/VRAM при наличии `nvidia-smi`;
- вернуть host Ollama status и обнаруженные Ollama containers;
- вернуть top processes без command line;
- вернуть ограниченный и очищенный warning journal;
- добавить installer, units, документацию и contract tests.

### Критерии готовности

- `monitorctl` принимает только восемь фиксированных view;
- HTTP gateway разрешает только GET;
- gateway не имеет Docker socket, host ports и capabilities;
- root bridge не принимает команды, пути, PID, unit/container names или дополнительные поля;
- process cmdline, Docker env/mounts/command и secret-like journal values не возвращаются;
- installer проверяет `monitorctl summary` из runtime Каэля;
- focused tests и GitHub CI проходят;
- production smoke подтверждает все восемь view.

### Риски и ограничения

`models` видит host Ollama CLI, если он установлен, и Ollama containers по безопасным Docker metadata. Модели внутри container-only Ollama без host CLI могут быть представлены только фактом работающего контейнера, пока не будет отдельного authenticated model-status API.

`incidents` возвращает системный warning journal и применяет redaction, но любой текстовый фильтр не является абсолютной защитой от нестандартного секрета. Поэтому объём ограничен 30 минутами, 100 событиями и 500 символами на сообщение.

## После завершения

### Фактически сделано

- добавлен fixed-view host collector;
- добавлен internal read-only gateway;
- добавлен `monitorctl.py`;
- добавлены installer, systemd units, документация и CI;
- операционный контракт Каэля дополнен правилами monitor.

### Миграции и совместимость

SQL-миграций нет. Application containers и базы данных не меняются. Новый контур использует отдельный host token и порт 8879 только внутри `velvet_backend`.

### Проверки

До PR выполнены `compileall`, `bash -n` и 14 focused unit/contract tests. Compose validation и Docker image build выполняет отдельный GitHub Actions workflow.

### PR и commit

- PR: ожидается;
- ветка: `feat/hermes-readonly-monitor`;
- head: ожидается после публикации;
- merge commit: ожидается после review и зелёного CI.

### Незавершённое

- открыть draft PR;
- дождаться полного CI;
- после merge выполнить installer на production;
- очистить permanent `command_allowlist` Каэля и подтвердить `approvals.mode=manual`;
- выполнить live smoke восьми monitor views.

### Следующий шаг

После зелёного CI слить PR отдельным разрешением, обновить `/srv/velvet`, запустить `deploy/hermes-monitor/install.sh` и проверить вывод `monitorctl summary`, `containers`, `services`, `models` и `incidents`.
