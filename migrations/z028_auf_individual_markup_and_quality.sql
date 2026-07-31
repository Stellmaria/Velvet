-- Individual user markup, 30 percent global default, and whole-VL quality surcharges.

UPDATE auf_economy_settings
SET retail_markup_percent = 30.0000,
    updated_at = NOW()
WHERE singleton_id = 1;

CREATE TABLE IF NOT EXISTS auf_user_markup_overrides (
    user_id BIGINT PRIMARY KEY REFERENCES telegram_users(user_id) ON DELETE CASCADE,
    markup_percent NUMERIC(8, 2) NOT NULL,
    updated_by_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (markup_percent >= 0 AND markup_percent <= 1000)
);

ALTER TABLE auf_price_versions
    ADD COLUMN IF NOT EXISTS quality_surcharge_velvets INTEGER NOT NULL DEFAULT 0;

ALTER TABLE auf_price_versions
    DROP CONSTRAINT IF EXISTS auf_price_versions_quality_surcharge_check;
ALTER TABLE auf_price_versions
    ADD CONSTRAINT auf_price_versions_quality_surcharge_check
    CHECK (quality_surcharge_velvets >= 0);

-- Banana quality is charged in whole VL steps on top of provider cost plus markup:
-- 1K +0 VL, 2K +1 VL, 4K +2 VL.
UPDATE auf_price_versions
SET quality_surcharge_velvets = CASE UPPER(COALESCE(resolution, ''))
    WHEN '2K' THEN 1
    WHEN '4K' THEN 2
    ELSE 0
END,
source = 'Provider cost plus effective user markup; Banana quality surcharge; rounded to whole VL'
WHERE effective_from <= NOW()
  AND (effective_to IS NULL OR effective_to > NOW())
  AND operation = 'media.generate'
  AND model_alias IN ('nano_banana_2', 'nano_banana_pro');

UPDATE auf_price_versions
SET quality_surcharge_velvets = 0,
    source = 'Provider cost plus effective user markup; rounded to whole VL'
WHERE effective_from <= NOW()
  AND (effective_to IS NULL OR effective_to > NOW())
  AND operation = 'media.generate'
  AND model_alias NOT IN ('nano_banana_2', 'nano_banana_pro');
