from __future__ import annotations

from shared_contract_inventory import (
    build_inventory,
    main,
    render_markdown,
    validate_inventory,
)

__all__ = (
    "build_inventory",
    "main",
    "render_markdown",
    "validate_inventory",
)


if __name__ == "__main__":
    raise SystemExit(main())
