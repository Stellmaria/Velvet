# Hermes entities

Этот слой применяется после базовой установки Hermes orchestration.

```bash
sudo bash /srv/velvet/deploy/hermes-entities/install.sh
sudo bash /srv/velvet/deploy/hermes-librarian/install.sh
```

Он разделяет:

- `SOUL.md` — личность;
- `AGENTS.md`/`.hermes.md` — проектные и операционные правила;
- runtime credentials и tool permissions — конфигурация/Compose.
- `brain-vault/manifest.json` — versioned registry разрешённого контекста;
- `context-manifest.json` — hash-доказательство установленного context pack.

Основные сущности:

- Каэль — серверный оператор;
- Velvet Librarian — отдельный internal-only архивный runtime;
- Velvet Coder — изолированный кодер Velvet;
- Макс — изолированный кодер Romatic Club Max.

`hermes-entities-reconcile.service` компилирует отдельные packs, проверяет их
hashes, повторно устанавливает canonical SOUL/AGENTS/skills и права до запуска
основных Compose/coder units после reboot. Живые `MEMORY.md`/`USER.md` не
перезаписываются; seed применяется только при отсутствии файла.

Каэль получает `terminal.cwd=/opt/data`, включённое context compression и
hard-stop circuit breaker. Это обеспечивает загрузку его project instructions,
не выдавая root, Docker socket или произвольный shell.
