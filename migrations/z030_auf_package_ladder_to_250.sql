-- Replace the wide package ladder with six purchase options capped at 250 VL.
-- The global 42.86 percent markup and all individual user overrides remain unchanged.
-- Prices are deliberately below the current competitor ladder while avoiding deep dumping.

UPDATE auf_package_prices
SET is_active = FALSE,
    effective_to = GREATEST(NOW(), effective_from + INTERVAL '1 microsecond')
WHERE package_auf NOT IN (20, 50, 75, 100, 150, 250)
  AND is_active = TRUE;

INSERT INTO auf_package_prices (
    package_auf, price_rub, version_key, is_active, source,
    effective_from, effective_to
)
VALUES
    (20,  100.00, '2026-08-04:competitive-ladder:20',  TRUE,
     'entry package; minimum purchase 100 RUB', NOW(), NULL),
    (50,  239.00, '2026-08-04:competitive-ladder:50',  TRUE,
     'competitive market ladder', NOW(), NULL),
    (75,  339.00, '2026-08-04:competitive-ladder:75',  TRUE,
     'competitive market ladder', NOW(), NULL),
    (100, 429.00, '2026-08-04:competitive-ladder:100', TRUE,
     'competitive market ladder', NOW(), NULL),
    (150, 619.00, '2026-08-04:competitive-ladder:150', TRUE,
     'competitive market ladder', NOW(), NULL),
    (250, 999.00, '2026-08-04:competitive-ladder:250', TRUE,
     'largest public package; capped at 250 VL', NOW(), NULL)
ON CONFLICT (package_auf) DO UPDATE
SET price_rub = EXCLUDED.price_rub,
    version_key = EXCLUDED.version_key,
    is_active = TRUE,
    source = EXCLUDED.source,
    effective_from = NOW(),
    effective_to = NULL;
