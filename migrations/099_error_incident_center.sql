CREATE TABLE IF NOT EXISTS error_incidents (
    id BIGSERIAL PRIMARY KEY,
    fingerprint CHAR(64) NOT NULL UNIQUE,
    severity VARCHAR(16) NOT NULL,
    logger_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    details TEXT,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by BIGINT,
    log_chat_message_id BIGINT,
    CONSTRAINT error_incidents_severity_check
        CHECK (severity IN ('WARNING', 'ERROR', 'CRITICAL')),
    CONSTRAINT error_incidents_occurrence_count_check
        CHECK (occurrence_count >= 1)
);

CREATE INDEX IF NOT EXISTS idx_error_incidents_unacknowledged
    ON error_incidents(last_seen_at DESC, id DESC)
    WHERE acknowledged_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_error_incidents_severity_unacknowledged
    ON error_incidents(severity, last_seen_at DESC)
    WHERE acknowledged_at IS NULL;

CREATE TABLE IF NOT EXISTS error_alert_state (
    id SMALLINT PRIMARY KEY DEFAULT 1,
    last_owner_digest_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT error_alert_state_singleton_check CHECK (id = 1)
);

INSERT INTO error_alert_state (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;
