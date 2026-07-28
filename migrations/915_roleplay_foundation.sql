CREATE TABLE IF NOT EXISTS rp_characters (
    id BIGSERIAL PRIMARY KEY,
    owner_user_id BIGINT NOT NULL,
    name VARCHAR(120) NOT NULL,
    normalized_name VARCHAR(120) NOT NULL,
    adult_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    age_text VARCHAR(80),
    pronouns VARCHAR(80),
    appearance JSONB NOT NULL DEFAULT '{}'::JSONB,
    personality JSONB NOT NULL DEFAULT '{}'::JSONB,
    speech JSONB NOT NULL DEFAULT '{}'::JSONB,
    biography JSONB NOT NULL DEFAULT '{}'::JSONB,
    behavior_rules JSONB NOT NULL DEFAULT '{}'::JSONB,
    canonical_facts JSONB NOT NULL DEFAULT '[]'::JSONB,
    example_dialogue JSONB NOT NULL DEFAULT '[]'::JSONB,
    system_notes TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_user_id, normalized_name),
    CHECK (jsonb_typeof(appearance) = 'object'),
    CHECK (jsonb_typeof(personality) = 'object'),
    CHECK (jsonb_typeof(speech) = 'object'),
    CHECK (jsonb_typeof(biography) = 'object'),
    CHECK (jsonb_typeof(behavior_rules) = 'object'),
    CHECK (jsonb_typeof(canonical_facts) = 'array'),
    CHECK (jsonb_typeof(example_dialogue) = 'array'),
    CHECK (version >= 1)
);

CREATE INDEX IF NOT EXISTS idx_rp_characters_owner_updated
    ON rp_characters (owner_user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS rp_sessions (
    id BIGSERIAL PRIMARY KEY,
    owner_user_id BIGINT NOT NULL,
    title VARCHAR(240) NOT NULL,
    model VARCHAR(240) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    scenario TEXT NOT NULL DEFAULT '',
    world_lore TEXT NOT NULL DEFAULT '',
    scene_state JSONB NOT NULL DEFAULT '{}'::JSONB,
    summary TEXT NOT NULL DEFAULT '',
    generation_settings JSONB NOT NULL DEFAULT '{}'::JSONB,
    next_sequence INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ,
    CHECK (status IN ('active', 'paused', 'completed', 'archived')),
    CHECK (jsonb_typeof(scene_state) = 'object'),
    CHECK (jsonb_typeof(generation_settings) = 'object'),
    CHECK (next_sequence >= 1)
);

CREATE INDEX IF NOT EXISTS idx_rp_sessions_owner_status_updated
    ON rp_sessions (owner_user_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS rp_session_characters (
    session_id BIGINT NOT NULL REFERENCES rp_sessions(id) ON DELETE CASCADE,
    character_id BIGINT NOT NULL REFERENCES rp_characters(id) ON DELETE RESTRICT,
    role_order INTEGER NOT NULL,
    role_name VARCHAR(120),
    current_state JSONB NOT NULL DEFAULT '{}'::JSONB,
    relationship_state JSONB NOT NULL DEFAULT '{}'::JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (session_id, character_id),
    UNIQUE (session_id, role_order),
    CHECK (role_order >= 1),
    CHECK (jsonb_typeof(current_state) = 'object'),
    CHECK (jsonb_typeof(relationship_state) = 'object')
);

CREATE TABLE IF NOT EXISTS rp_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES rp_sessions(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    role VARCHAR(16) NOT NULL,
    speaker_key VARCHAR(120),
    content TEXT NOT NULL,
    token_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, sequence_no),
    CHECK (role IN ('user', 'assistant', 'system')),
    CHECK (length(btrim(content)) > 0),
    CHECK (token_count IS NULL OR token_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_rp_messages_session_sequence
    ON rp_messages (session_id, sequence_no DESC);

CREATE TABLE IF NOT EXISTS rp_memories (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES rp_sessions(id) ON DELETE CASCADE,
    character_id BIGINT REFERENCES rp_characters(id) ON DELETE RESTRICT,
    kind VARCHAR(24) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    importance SMALLINT NOT NULL DEFAULT 50,
    pinned BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    source_message_id BIGINT REFERENCES rp_messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (kind IN ('canonical', 'episodic', 'relationship', 'scene')),
    CHECK (length(btrim(content)) > 0),
    CHECK (jsonb_typeof(metadata) = 'object'),
    CHECK (importance BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS idx_rp_memories_session_active_priority
    ON rp_memories (
        session_id,
        active,
        pinned DESC,
        importance DESC,
        updated_at DESC
    );
