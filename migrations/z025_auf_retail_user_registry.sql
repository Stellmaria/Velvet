-- Retail pricing, fixed package offers and privacy-safe Telegram user observability.

CREATE TABLE IF NOT EXISTS telegram_users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(64),
    first_name VARCHAR(128),
    last_name VARCHAR(128),
    language_code VARCHAR(16),
    is_bot BOOLEAN NOT NULL DEFAULT FALSE,
    is_premium BOOLEAN,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_private_seen_at TIMESTAMPTZ,
    last_chat_id BIGINT,
    last_chat_type VARCHAR(24),
    last_workspace_id BIGINT REFERENCES workspaces(id) ON DELETE SET NULL,
    update_count BIGINT NOT NULL DEFAULT 0 CHECK (update_count >= 0),
    message_count BIGINT NOT NULL DEFAULT 0 CHECK (message_count >= 0),
    callback_count BIGINT NOT NULL DEFAULT 0 CHECK (callback_count >= 0),
    command_count BIGINT NOT NULL DEFAULT 0 CHECK (command_count >= 0),
    inline_count BIGINT NOT NULL DEFAULT 0 CHECK (inline_count >= 0),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS telegram_users_username_unique_idx
    ON telegram_users (LOWER(username))
    WHERE username IS NOT NULL AND username <> '';
CREATE INDEX IF NOT EXISTS telegram_users_last_seen_idx
    ON telegram_users (last_seen_at DESC, user_id);
CREATE INDEX IF NOT EXISTS telegram_users_workspace_idx
    ON telegram_users (last_workspace_id, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS telegram_user_events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES telegram_users(user_id) ON DELETE CASCADE,
    event_type VARCHAR(32) NOT NULL,
    module_key VARCHAR(48),
    command_name VARCHAR(64),
    callback_action VARCHAR(96),
    workspace_id BIGINT REFERENCES workspaces(id) ON DELETE SET NULL,
    chat_id BIGINT,
    chat_type VARCHAR(24),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS telegram_user_events_user_time_idx
    ON telegram_user_events (user_id, occurred_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS telegram_user_events_type_time_idx
    ON telegram_user_events (event_type, occurred_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS telegram_user_events_module_time_idx
    ON telegram_user_events (module_key, occurred_at DESC, id DESC)
    WHERE module_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS auf_package_prices (
    package_auf INTEGER PRIMARY KEY CHECK (package_auf > 0),
    price_rub NUMERIC(12, 2) NOT NULL CHECK (price_rub > 0),
    version_key VARCHAR(160) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    source TEXT NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

INSERT INTO auf_package_prices (
    package_auf, price_rub, version_key, source
)
VALUES
    (40,   119.00, '2026-07-30:retail-package:40',   'Approved retail package'),
    (100,  269.00, '2026-07-30:retail-package:100',  'Approved retail package'),
    (250,  649.00, '2026-07-30:retail-package:250',  'Approved retail package'),
    (500, 1190.00, '2026-07-30:retail-package:500',  'Approved retail package'),
    (1000,2290.00, '2026-07-30:retail-package:1000', 'Approved retail package'),
    (2500,5490.00, '2026-07-30:retail-package:2500', 'Approved retail package')
ON CONFLICT (package_auf) DO UPDATE
SET price_rub = EXCLUDED.price_rub,
    version_key = EXCLUDED.version_key,
    is_active = TRUE,
    source = EXCLUDED.source,
    effective_from = LEAST(auf_package_prices.effective_from, NOW()),
    effective_to = NULL;

ALTER TABLE auf_price_versions
    ADD COLUMN IF NOT EXISTS retail_units BIGINT;
ALTER TABLE auf_price_versions
    ADD COLUMN IF NOT EXISTS extra_reference_retail_units BIGINT NOT NULL DEFAULT 0;

ALTER TABLE auf_price_versions
    DROP CONSTRAINT IF EXISTS auf_price_versions_retail_units_check;
ALTER TABLE auf_price_versions
    ADD CONSTRAINT auf_price_versions_retail_units_check
    CHECK (retail_units IS NULL OR retail_units > 0);
ALTER TABLE auf_price_versions
    DROP CONSTRAINT IF EXISTS auf_price_versions_extra_reference_retail_units_check;
ALTER TABLE auf_price_versions
    ADD CONSTRAINT auf_price_versions_extra_reference_retail_units_check
    CHECK (extra_reference_retail_units >= 0);

UPDATE auf_price_versions
SET effective_to = GREATEST(NOW(), effective_from + INTERVAL '1 microsecond')
WHERE effective_to IS NULL
  AND version_key NOT LIKE '2026-07-30:retail:%'
  AND model_alias IN (
      'nano_banana_2', 'nano_banana_pro', 'seedream_5_pro',
      'qwen2_image_edit', 'wan_27_image', 'flux_2_pro_image',
      'grok_imagine_video', 'grok_imagine_video_15',
      'seedance_15_pro_video', 'wan_26_image_to_video'
  );

INSERT INTO auf_price_versions (
    version_key, provider, model_alias, resolution, audio,
    pricing_basis, unit_cost_usd, extra_reference_cost_usd,
    retail_units, extra_reference_retail_units, source
)
VALUES
    ('2026-07-30:retail:nano-banana-2:1k', 'grs', 'nano_banana_2', '1K', NULL,
     'fixed', 0.02000000, 0, 40000, 0, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:nano-banana-2:2k', 'grs', 'nano_banana_2', '2K', NULL,
     'fixed', 0.02000000, 0, 50000, 0, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:nano-banana-2:4k', 'grs', 'nano_banana_2', '4K', NULL,
     'fixed', 0.02000000, 0, 80000, 0, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:nano-banana-pro:1k', 'grs', 'nano_banana_pro', '1K', NULL,
     'fixed', 0.03000000, 0, 60000, 0, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:nano-banana-pro:2k', 'grs', 'nano_banana_pro', '2K', NULL,
     'fixed', 0.03000000, 0, 80000, 0, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:nano-banana-pro:4k', 'grs', 'nano_banana_pro', '4K', NULL,
     'fixed', 0.03000000, 0, 110000, 0, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:seedream-5-pro:1k', 'kie', 'seedream_5_pro', '1K', NULL,
     'fixed', 0.07500000, 0.00500000, 50000, 5000, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:seedream-5-pro:2k', 'kie', 'seedream_5_pro', '2K', NULL,
     'fixed', 0.15000000, 0.00500000, 90000, 5000, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:qwen-image-2:2k', 'kie', 'qwen2_image_edit', '2K', NULL,
     'fixed', 0.02000000, 0, 50000, 0, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:wan-2-7-image:1k', 'kie', 'wan_27_image', '1K', NULL,
     'fixed', 0.05000000, 0, 80000, 0, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:wan-2-7-image:2k', 'kie', 'wan_27_image', '2K', NULL,
     'fixed', 0.08000000, 0, 100000, 0, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:flux-2-pro:1k', 'kie', 'flux_2_pro_image', '1K', NULL,
     'fixed', 0.04500000, 0, 50000, 0, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:flux-2-pro:2k', 'kie', 'flux_2_pro_image', '2K', NULL,
     'fixed', 0.07500000, 0, 60000, 0, 'Retail tariff approved from market comparison'),
    ('2026-07-30:retail:grok-v1:480p', 'kie', 'grok_imagine_video', '480p', NULL,
     'fixed', 0.04800000, 0, 50000, 0, 'Fixed six-second retail tariff'),
    ('2026-07-30:retail:grok-v1:720p', 'kie', 'grok_imagine_video', '720p', NULL,
     'fixed', 0.09000000, 0, 80000, 0, 'Fixed six-second retail tariff'),
    ('2026-07-30:retail:grok-1-5:480p', 'kie', 'grok_imagine_video_15', '480p', NULL,
     'per_second', 0.07250000, 0, 40000, 0, 'Retail price per second'),
    ('2026-07-30:retail:grok-1-5:720p', 'kie', 'grok_imagine_video_15', '720p', NULL,
     'per_second', 0.12500000, 0, 70000, 0, 'Retail price per second'),
    ('2026-07-30:retail:seedance:480p:no-audio', 'kie', 'seedance_15_pro_video', '480p', FALSE,
     'per_second', 0.00875000, 0, 7500, 0, 'Retail price per second'),
    ('2026-07-30:retail:seedance:720p:no-audio', 'kie', 'seedance_15_pro_video', '720p', FALSE,
     'per_second', 0.01750000, 0, 12500, 0, 'Retail price per second'),
    ('2026-07-30:retail:seedance:1080p:no-audio', 'kie', 'seedance_15_pro_video', '1080p', FALSE,
     'per_second', 0.03750000, 0, 25000, 0, 'Retail price per second'),
    ('2026-07-30:retail:seedance:480p:audio', 'kie', 'seedance_15_pro_video', '480p', TRUE,
     'per_second', 0.01750000, 0, 12500, 0, 'Retail price per second'),
    ('2026-07-30:retail:seedance:720p:audio', 'kie', 'seedance_15_pro_video', '720p', TRUE,
     'per_second', 0.03500000, 0, 25000, 0, 'Retail price per second'),
    ('2026-07-30:retail:seedance:1080p:audio', 'kie', 'seedance_15_pro_video', '1080p', TRUE,
     'per_second', 0.07500000, 0, 50000, 0, 'Retail price per second'),
    ('2026-07-30:retail:wan-2-7-video:720p', 'kie', 'wan_26_image_to_video', '720p', NULL,
     'per_second', 0.08000000, 0, 50000, 0, 'Retail price per second'),
    ('2026-07-30:retail:wan-2-7-video:1080p', 'kie', 'wan_26_image_to_video', '1080p', NULL,
     'per_second', 0.12000000, 0, 75000, 0, 'Retail price per second')
ON CONFLICT (version_key) DO UPDATE
SET effective_to = NULL,
    retail_units = EXCLUDED.retail_units,
    extra_reference_retail_units = EXCLUDED.extra_reference_retail_units,
    unit_cost_usd = EXCLUDED.unit_cost_usd,
    extra_reference_cost_usd = EXCLUDED.extra_reference_cost_usd,
    source = EXCLUDED.source;
