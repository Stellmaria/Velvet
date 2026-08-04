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
    WHEN model_alias = 'qwen2_image_edit' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 1
    WHEN model_alias = 'wan_27_image' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 2
    WHEN model_alias = 'wan_27_image' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 3
    WHEN model_alias = 'flux_2_pro_image' AND UPPER(COALESCE(resolution, '')) = '1K' THEN 2
    WHEN model_alias = 'flux_2_pro_image' AND UPPER(COALESCE(resolution, '')) = '2K' THEN 3
    ELSE 1
END,
source = source || '; stable quote reference and SKU floor'
WHERE effective_from <= NOW()
  AND (effective_to IS NULL OR effective_to > NOW())
  AND operation = 'media.generate';
