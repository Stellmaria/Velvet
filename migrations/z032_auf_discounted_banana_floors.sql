-- Add a separate product floor for users on the minimum 15 percent markup.
-- Standard users keep the existing Banana tiering; discounted users receive the
-- same 1/2/3 VL ladder for Banana 2 and Banana Pro.

ALTER TABLE auf_price_versions
    ADD COLUMN IF NOT EXISTS minimum_discounted_velvets INTEGER;

ALTER TABLE auf_price_versions
    DROP CONSTRAINT IF EXISTS auf_price_versions_minimum_discounted_velvets_check;
ALTER TABLE auf_price_versions
    ADD CONSTRAINT auf_price_versions_minimum_discounted_velvets_check
    CHECK (
        minimum_discounted_velvets IS NULL
        OR minimum_discounted_velvets > 0
    );

UPDATE auf_price_versions
SET minimum_discounted_velvets = CASE UPPER(COALESCE(resolution, ''))
        WHEN '1K' THEN 1
        WHEN '2K' THEN 2
        WHEN '4K' THEN 3
        ELSE minimum_discounted_velvets
    END,
    source = source || '; minimum-markup Banana floor'
WHERE effective_from <= NOW()
  AND (effective_to IS NULL OR effective_to > NOW())
  AND operation = 'media.generate'
  AND model_alias IN ('nano_banana_2', 'nano_banana_pro')
  AND UPPER(COALESCE(resolution, '')) IN ('1K', '2K', '4K');
