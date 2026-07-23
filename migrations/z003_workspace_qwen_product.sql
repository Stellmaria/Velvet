CREATE TABLE IF NOT EXISTS workspace_qwen_checks (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    media_id BIGINT NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    provider VARCHAR(64),
    model VARCHAR(160),
    analysis_version SMALLINT NOT NULL DEFAULT 1,
    attempt_count SMALLINT NOT NULL DEFAULT 0,
    verdict VARCHAR(16),
    quality_score SMALLINT,
    confidence SMALLINT,
    report JSONB,
    decision VARCHAR(24),
    decided_by BIGINT,
    decided_at TIMESTAMPTZ,
    error_message TEXT,
    analyzed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, media_id),
    CONSTRAINT workspace_qwen_checks_status_check CHECK (
        status IN ('pending', 'processing', 'ready', 'error', 'skipped')
    ),
    CONSTRAINT workspace_qwen_checks_verdict_check CHECK (
        verdict IS NULL OR verdict IN ('ready', 'review', 'critical')
    ),
    CONSTRAINT workspace_qwen_checks_decision_check CHECK (
        decision IS NULL OR decision IN ('accepted', 'fix_required')
    ),
    CONSTRAINT workspace_qwen_checks_score_check CHECK (
        quality_score IS NULL OR quality_score BETWEEN 0 AND 100
    ),
    CONSTRAINT workspace_qwen_checks_confidence_check CHECK (
        confidence IS NULL OR confidence BETWEEN 0 AND 100
    )
);

CREATE INDEX IF NOT EXISTS idx_workspace_qwen_checks_queue
    ON workspace_qwen_checks(workspace_id, status, updated_at, media_id);

CREATE INDEX IF NOT EXISTS idx_workspace_qwen_checks_review
    ON workspace_qwen_checks(workspace_id, decision, verdict, analyzed_at DESC)
    WHERE status = 'ready';

CREATE TABLE IF NOT EXISTS workspace_qwen_feedback (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    media_id BIGINT NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    provider VARCHAR(64),
    model VARCHAR(160),
    analysis_version SMALLINT NOT NULL DEFAULT 1,
    predicted_verdict VARCHAR(16) NOT NULL,
    quality_score SMALLINT NOT NULL CHECK (quality_score BETWEEN 0 AND 100),
    confidence SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    owner_decision VARCHAR(24) NOT NULL,
    outcome VARCHAR(24) NOT NULL,
    report JSONB,
    decided_by BIGINT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workspace_qwen_feedback_verdict_check CHECK (
        predicted_verdict IN ('ready', 'review', 'critical')
    ),
    CONSTRAINT workspace_qwen_feedback_decision_check CHECK (
        owner_decision IN ('accepted', 'fix_required')
    ),
    CONSTRAINT workspace_qwen_feedback_outcome_check CHECK (
        outcome IN (
            'correct_clean', 'correct_fix', 'useful_warning',
            'false_alarm', 'missed_problem', 'uncertain'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_workspace_qwen_feedback_profile
    ON workspace_qwen_feedback(workspace_id, provider, model, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS workspace_qwen_jobs (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind VARCHAR(48) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    stage VARCHAR(32) NOT NULL DEFAULT 'queued',
    title VARCHAR(240) NOT NULL,
    provider VARCHAR(64),
    model VARCHAR(160),
    media_id BIGINT REFERENCES media_files(id) ON DELETE SET NULL,
    request_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    result_payload JSONB,
    result_text TEXT,
    error_message TEXT,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workspace_qwen_jobs_status_check CHECK (
        status IN ('pending', 'processing', 'ready', 'error')
    ),
    CONSTRAINT workspace_qwen_jobs_kind_check CHECK (
        kind IN (
            'quality_image', 'reference_comparison',
            'prompt_result', 'palette_composition', 'archive_audit'
        )
    ),
    CONSTRAINT workspace_qwen_jobs_title_not_empty CHECK (BTRIM(title) <> '')
);

CREATE INDEX IF NOT EXISTS idx_workspace_qwen_jobs_history
    ON workspace_qwen_jobs(workspace_id, created_at DESC, id DESC);

CREATE OR REPLACE FUNCTION capture_workspace_qwen_feedback()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    feedback_outcome VARCHAR(24);
BEGIN
    IF NEW.decision IS NULL OR NEW.decision IS NOT DISTINCT FROM OLD.decision THEN
        RETURN NEW;
    END IF;

    feedback_outcome := CASE
        WHEN NEW.verdict = 'ready' AND NEW.decision = 'accepted'
            THEN 'correct_clean'
        WHEN NEW.verdict = 'critical' AND NEW.decision = 'fix_required'
            THEN 'correct_fix'
        WHEN NEW.verdict = 'review' AND NEW.decision = 'fix_required'
            THEN 'useful_warning'
        WHEN NEW.verdict IN ('review', 'critical') AND NEW.decision = 'accepted'
            THEN 'false_alarm'
        WHEN NEW.verdict = 'ready' AND NEW.decision = 'fix_required'
            THEN 'missed_problem'
        ELSE 'uncertain'
    END;

    INSERT INTO workspace_qwen_feedback (
        workspace_id, media_id, provider, model, analysis_version,
        predicted_verdict, quality_score, confidence, owner_decision,
        outcome, report, decided_by, decided_at
    )
    VALUES (
        NEW.workspace_id,
        NEW.media_id,
        NEW.provider,
        NEW.model,
        NEW.analysis_version,
        COALESCE(NEW.verdict, 'review'),
        COALESCE(NEW.quality_score, 0),
        COALESCE(NEW.confidence, 0),
        NEW.decision,
        feedback_outcome,
        NEW.report,
        NEW.decided_by,
        COALESCE(NEW.decided_at, NOW())
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_capture_workspace_qwen_feedback
    ON workspace_qwen_checks;

CREATE TRIGGER trg_capture_workspace_qwen_feedback
AFTER UPDATE OF decision ON workspace_qwen_checks
FOR EACH ROW
EXECUTE FUNCTION capture_workspace_qwen_feedback();
