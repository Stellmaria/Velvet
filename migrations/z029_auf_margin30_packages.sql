-- Apply a 30 percent gross-margin target as the global default.
-- A 30 percent margin equals a 42.86 percent markup on provider cost.
-- Individual user overrides remain intact and continue to take priority.
-- Package prices keep the cheapest active VL at 3.436 RUB, which covers
-- the current Nano Banana Pro 1K provider cost with at least 30 percent margin.

UPDATE auf_economy_settings
SET retail_markup_percent = 42.8600,
    retail_auf_usd = 0.04309777,
    updated_at = NOW()
WHERE singleton_id = 1;

-- Retire the former 40 VL entry. The new entry-level purchase is 20 VL for 100 RUB.
UPDATE auf_package_prices
SET is_active = FALSE,
    effective_to = GREATEST(NOW(), effective_from + INTERVAL '1 microsecond')
WHERE package_auf = 40
  AND is_active = TRUE;

INSERT INTO auf_package_prices (
    package_auf, price_rub, version_key, is_active, source,
    effective_from, effective_to
)
VALUES
    (20,    100.00, '2026-08-04:margin30-package:20',   TRUE,
     '30 percent gross-margin floor; minimum purchase 100 RUB', NOW(), NULL),
    (100,   429.00, '2026-08-04:margin30-package:100',  TRUE,
     '30 percent gross-margin floor', NOW(), NULL),
    (250,  1019.00, '2026-08-04:margin30-package:250',  TRUE,
     '30 percent gross-margin floor', NOW(), NULL),
    (500,  1890.00, '2026-08-04:margin30-package:500',  TRUE,
     '30 percent gross-margin floor', NOW(), NULL),
    (1000, 3590.00, '2026-08-04:margin30-package:1000', TRUE,
     '30 percent gross-margin floor', NOW(), NULL),
    (2500, 8590.00, '2026-08-04:margin30-package:2500', TRUE,
     '30 percent gross-margin floor', NOW(), NULL)
ON CONFLICT (package_auf) DO UPDATE
SET price_rub = EXCLUDED.price_rub,
    version_key = EXCLUDED.version_key,
    is_active = TRUE,
    source = EXCLUDED.source,
    effective_from = NOW(),
    effective_to = NULL;
