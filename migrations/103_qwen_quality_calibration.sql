CREATE TABLE IF NOT EXISTS qwen_quality_feedback (
    id BIGSERIAL PRIMARY KEY,
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
    CONSTRAINT qwen_quality_feedback_verdict_check CHECK (
        predicted_verdict IN ('ready', 'review', 'critical')
    ),
    CONSTRAINT qwen_quality_feedback_decision_check CHECK (
        owner_decision IN ('accepted', 'fix_required')
    ),
    CONSTRAINT qwen_quality_feedback_outcome_check CHECK (
        outcome IN (
            'correct_clean',
            'correct_fix',
            'useful_warning',
            'false_alarm',
            'missed_problem',
            'uncertain'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_qwen_quality_feedback_created
    ON qwen_quality_feedback (created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_qwen_quality_feedback_outcome
    ON qwen_quality_feedback (outcome, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_qwen_quality_feedback_model
    ON qwen_quality_feedback (provider, model, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_qwen_quality_feedback_decision_event
    ON qwen_quality_feedback (media_id, decided_at, owner_decision);

INSERT INTO qwen_quality_feedback (
    media_id,
    provider,
    model,
    analysis_version,
    predicted_verdict,
    quality_score,
    confidence,
    owner_decision,
    outcome,
    report,
    decided_by,
    decided_at
)
SELECT
    quality.media_id,
    quality.provider,
    quality.model,
    quality.analysis_version,
    COALESCE(quality.verdict, 'review'),
    COALESCE(quality.quality_score, 0),
    COALESCE(quality.confidence, 0),
    quality.decision,
    CASE
        WHEN quality.verdict = 'ready' AND quality.decision = 'accepted'
            THEN 'correct_clean'
        WHEN quality.verdict = 'critical' AND quality.decision = 'fix_required'
            THEN 'correct_fix'
        WHEN quality.verdict = 'review' AND quality.decision = 'fix_required'
            THEN 'useful_warning'
        WHEN quality.verdict IN ('review', 'critical') AND quality.decision = 'accepted'
            THEN 'false_alarm'
        WHEN quality.verdict = 'ready' AND quality.decision = 'fix_required'
            THEN 'missed_problem'
        ELSE 'uncertain'
    END,
    quality.report,
    quality.decided_by,
    COALESCE(quality.decided_at, quality.updated_at, NOW())
FROM media_ai_quality_checks AS quality
WHERE quality.status = 'ready'
  AND quality.decision IS NOT NULL
  AND quality.verdict IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION capture_qwen_quality_feedback()
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

    INSERT INTO qwen_quality_feedback (
        media_id,
        provider,
        model,
        analysis_version,
        predicted_verdict,
        quality_score,
        confidence,
        owner_decision,
        outcome,
        report,
        decided_by,
        decided_at
    )
    VALUES (
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
    )
    ON CONFLICT DO NOTHING;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_capture_qwen_quality_feedback
    ON media_ai_quality_checks;

CREATE TRIGGER trg_capture_qwen_quality_feedback
AFTER UPDATE OF decision ON media_ai_quality_checks
FOR EACH ROW
EXECUTE FUNCTION capture_qwen_quality_feedback();
