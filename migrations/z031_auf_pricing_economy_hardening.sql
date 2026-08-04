-- Harden AUF pricing so generation quotes no longer depend on package marketing.
-- Keep the global 42.86 percent markup, add a small operating-cost reserve,
-- enforce a safe minimum for individual markup overrides, and persist SKU floors.

ALTER TABLE auf_economy_settings
    ADD COLUMN IF NOT EXISTS quote_rub_per_vl NUMERIC(18, 8) NOT NULL DEFAULT 4.00000000;
ALTER TABLE auf_economy_settings
    ADD COLUMN IF NOT EXISTS operational_cost_buffer_percent NUMERIC(8, 4) NOT NULL DEFAULT 5.0000;
ALTER TABLE auf_economy_settings
    ADD COLUMN IF NOT EXISTS minimum_user_markup_percent NUMERIC(8, 4) NOT NULL DEFAULT 15.0000;

ALTER TABLE auf_economy_settings
    DROP CONSTRAINT IF EXISTS auf_economy_settings_quote_rub_per_vl_check;
ALTER TABLE auf_economy_settings
    ADD CONSTRAINT auf_economy_settings_quote_rub_per_vl_check
    CHECK (quote_rub_per_vl > 0);

ALTER TABLE auf_economy_settings
    DROP CONSTRAINT IF EXISTS auf_economy_settings_operational_cost_buffer_percent_check;
ALTER TABLE auf_economy_settings
    ADD CONSTRAINT auf_economy_settings_operational_cost_buffer_percent_check
    CHECK (
        operational_cost_buffer_percent >= 0
        AND operational_cost_buffer_percent <= 1000
    );

ALTER TABLE auf_economy_settings
    DROP CONSTRAINT IF EXISTS auf_economy_settings_minimum_user_markup_percent_check;
ALTER TABLE auf_economy_settings
    ADD CONSTRAINT auf_economy_settings_minimum_user_markup_percent_check
    CHECK (
        minimum_user_markup_percent >= 0
        AND minimum_user_markup_percent <= 1000
    );

UPDATE auf_economy_settings
SET quote_rub_per_vl = 4.00000000,
    operational_cost_buffer_percent = 5.0000,
    minimum_user_markup_percent = 15.0000,
    updated_at = NOW()
WHERE singleton_id = 1;

-- Existing individual overrides below the new safety floor are raised in place.
-- This preserves the override itself while preventing quotes below the approved floor.
UPDATE auf_user_markup_overrides
SET markup_percent = 15.00,
    updated_at = NOW()
WHERE markup_percent < 15.00;

ALTER TABLE auf_price_versions
    ADD COLUMN IF NOT EXISTS minimum_velvets INTEGER NOT NULL DEFAULT 1;

ALTER TABLE auf_price_versions
    DROP CONSTRAINT IF EXISTS auf_price_versions_minimum_velvets_check;
ALTER TABLE auf_price_versions
    ADD CONSTRAINT auf_price_versions_minimum_velvets_check
    CHECK (minimum_velvets > 0);

-- Retire image routes that are no longer offered for new generations.
UPDATE auf_price_versions
SET effective_to = GREATEST(NOW(), effective_from + INTERVAL '1 microsecond'),
    source = source || '; retired from active AUF image catalog'
WHERE effective_to IS NULL
  AND operation = 'media.generate'
  AND model_alias IN ('qwen2_image_edit', 'flux_2_pro_image', 'wan_27_image');

-- Publish separate standard and Pro Wan 2.7 price versions. Provider pricing is
-- flat per result; VL floors keep product quality tiers explicit and profitable.
INSERT INTO auf_price_versions (
    version_key, provider, model_alias, resolution, audio,
    pricing_basis, unit_cost_usd, extra_reference_cost_usd,
    retail_units, extra_reference_retail_units, minimum_velvets, source
)
VALUES
    ('2026-08-04:wan-2-7-image:1k', 'kie', 'wan_27_image', '1K', NULL,
     'fixed', 0.03000000, 0, 10000, 0, 1, 'Wan 2.7 standard active catalog'),
    ('2026-08-04:wan-2-7-image:2k', 'kie', 'wan_27_image', '2K', NULL,
     'fixed', 0.03000000, 0, 20000, 0, 2, 'Wan 2.7 standard active catalog'),
    ('2026-08-04:wan-2-7-image-pro:1k', 'kie', 'wan_27_image_pro', '1K', NULL,
     'fixed', 0.07500000, 0, 30000, 0, 3, 'Wan 2.7 Pro active catalog'),
    ('2026-08-04:wan-2-7-image-pro:2k', 'kie', 'wan_27_image_pro', '2K', NULL,
     'fixed', 0.07500000, 0, 40000, 0, 4, 'Wan 2.7 Pro active catalog'),
    ('2026-08-04:wan-2-7-image-pro:4k', 'kie', 'wan_27_image_pro', '4K', NULL,
     'fixed', 0.07500000, 0, 50000, 0, 5, 'Wan 2.7 Pro text-to-image only')
ON CONFLICT (version_key) DO UPDATE
SET effective_to = NULL,
    unit_cost_usd = EXCLUDED.unit_cost_usd,
    retail_units = EXCLUDED.retail_units,
    extra_reference_cost_usd = EXCLUDED.extra_reference_cost_usd,
    extra_reference_retail_units = EXCLUDED.extra_reference_retail_units,
    minimum_velvets = EXCLUDED.minimum_velvets,
    source = EXCLUDED.source;

-- Product floors preserve meaningful quality tiers after integer-VL rounding.
UPDATE auf_price_versions
SET minimum_velvets = CASE
    WHEN model_alias = 'nano_banana_2' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 1
    WHEN model_alias = 'nano_banana_2' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 2
    WHEN model_alias = 'nano_banana_2' AND UPPER(COALESCE(resolution, '')) = '4K' THEN 3
    WHEN model_alias = 'nano_banana_pro' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 2
    WHEN model_alias = 'nano_banana_pro' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 3
    WHEN model_alias = 'nano_banana_pro' AND UPPER(COALESCE(resolution, '')) = '4K' THEN 4
    WHEN model_alias = 'seedream_5_pro' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 2
    WHEN model_alias = 'seedream_5_pro' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 4
    WHEN model_alias = 'wan_27_image' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 1
    WHEN model_alias = 'wan_27_image' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 2
    WHEN model_alias = 'wan_27_image_pro' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 3
    WHEN model_alias = 'wan_27_image_pro' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 4
    WHEN model_alias = 'wan_27_image_pro' AND UPPER(COALESCE(resolution, '')) = '4K' THEN 5
    ELSE 1
END,
source = source || '; stable quote reference and SKU floor'
WHERE effective_from <= NOW()
  AND (effective_to IS NULL OR effective_to > NOW())
  AND operation = 'media.generate';
