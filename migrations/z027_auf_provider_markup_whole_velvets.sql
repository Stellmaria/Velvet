-- Price new Auf generations at provider cost plus 20 percent and charge whole velvets.

ALTER TABLE auf_economy_settings
    ADD COLUMN IF NOT EXISTS billing_usd_to_byn NUMERIC(18, 8) NOT NULL DEFAULT 2.92661000;
ALTER TABLE auf_economy_settings
    ADD COLUMN IF NOT EXISTS retail_markup_percent NUMERIC(8, 4) NOT NULL DEFAULT 20.0000;

ALTER TABLE auf_economy_settings
    DROP CONSTRAINT IF EXISTS auf_economy_settings_billing_usd_to_byn_check;
ALTER TABLE auf_economy_settings
    ADD CONSTRAINT auf_economy_settings_billing_usd_to_byn_check
    CHECK (billing_usd_to_byn > 0);
ALTER TABLE auf_economy_settings
    DROP CONSTRAINT IF EXISTS auf_economy_settings_retail_markup_percent_check;
ALTER TABLE auf_economy_settings
    ADD CONSTRAINT auf_economy_settings_retail_markup_percent_check
    CHECK (retail_markup_percent >= 0 AND retail_markup_percent <= 1000);

UPDATE auf_economy_settings
SET billing_usd_to_rub = 79.72570000,
    billing_usd_to_byn = 2.92661000,
    retail_markup_percent = 20.0000,
    updated_at = NOW()
WHERE singleton_id = 1;

-- Historical retail values remain in migrations and completed task records. New quotes
-- are calculated dynamically from provider cost, the 20 percent markup and the least
-- expensive active package. Clearing these fields prevents two competing price sources.
UPDATE auf_price_versions
SET retail_units = NULL,
    extra_reference_retail_units = 0,
    source = 'Provider cost plus 20 percent; rounded up to whole velvets'
WHERE effective_from <= NOW()
  AND (effective_to IS NULL OR effective_to > NOW())
  AND operation = 'media.generate';
