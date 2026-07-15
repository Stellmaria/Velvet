CREATE TABLE IF NOT EXISTS character_subscriptions (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (character_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_character_subscriptions_user
    ON character_subscriptions(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS character_media_likes (
    character_id BIGINT NOT NULL,
    media_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (character_id, media_id, user_id),
    FOREIGN KEY (character_id, media_id)
        REFERENCES character_media(character_id, media_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_character_media_likes_count
    ON character_media_likes(character_id, media_id);

CREATE TABLE IF NOT EXISTS public_notification_deliveries (
    character_id BIGINT NOT NULL,
    media_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    delivered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (character_id, media_id, user_id),
    FOREIGN KEY (character_id, media_id)
        REFERENCES character_media(character_id, media_id)
        ON DELETE CASCADE,
    FOREIGN KEY (character_id, user_id)
        REFERENCES character_subscriptions(character_id, user_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_public_notification_deliveries_user
    ON public_notification_deliveries(user_id, delivered_at DESC);
