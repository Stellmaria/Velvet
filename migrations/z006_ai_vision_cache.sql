CREATE TABLE IF NOT EXISTS ai_vision_cache (
    id BIGSERIAL PRIMARY KEY,
    content_hash CHAR(64) NOT NULL,
    analysis_type VARCHAR(80) NOT NULL,
    prompt_version INTEGER NOT NULL,
    route VARCHAR(20) NOT NULL,
    provider VARCHAR(80) NOT NULL,
    model VARCHAR(160) NOT NULL,
    result JSONB NOT NULL,
    confidence SMALLINT NOT NULL DEFAULT 0,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    actual_cost_rub NUMERIC(14, 4) NOT NULL DEFAULT 0,
    hit_count BIGINT NOT NULL DEFAULT 0,
    last_hit_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ai_vision_cache_hash_check
        CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ai_vision_cache_type_check
        CHECK (LENGTH(BTRIM(analysis_type)) > 0),
    CONSTRAINT ai_vision_cache_route_check
        CHECK (route IN ('flash', 'pro', 'sensitive')),
    CONSTRAINT ai_vision_cache_provider_check
        CHECK (LENGTH(BTRIM(provider)) > 0),
    CONSTRAINT ai_vision_cache_model_check
        CHECK (LENGTH(BTRIM(model)) > 0),
    CONSTRAINT ai_vision_cache_confidence_check
        CHECK (confidence BETWEEN 0 AND 100),
    CONSTRAINT ai_vision_cache_usage_check
        CHECK (input_tokens >= 0 AND output_tokens >= 0 AND actual_cost_rub >= 0),
    CONSTRAINT ai_vision_cache_unique
        UNIQUE (content_hash, analysis_type, model, prompt_version)
);

CREATE INDEX IF NOT EXISTS idx_ai_vision_cache_lookup
    ON ai_vision_cache(content_hash, analysis_type, prompt_version, model);

CREATE INDEX IF NOT EXISTS idx_ai_vision_cache_recent
    ON ai_vision_cache(updated_at DESC);
