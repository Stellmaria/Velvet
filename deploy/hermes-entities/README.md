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

Основные сущности:

- Каэль — серверный оператор;
- Velvet Librarian — отдельный internal-only архивный runtime;
- Velvet Coder — изолированный кодер Velvet;
- Макс — изолированный кодер Romatic Club Max.

`hermes-entities-reconcile.service` повторно устанавливает canonical SOUL/AGENTS и права до запуска основных Compose/coder units после reboot.
