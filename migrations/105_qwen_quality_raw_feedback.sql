CREATE OR REPLACE FUNCTION capture_qwen_quality_feedback()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    predicted_verdict_value VARCHAR(16);
    feedback_outcome VARCHAR(24);
BEGIN
    IF NEW.decision IS NULL OR NEW.decision IS NOT DISTINCT FROM OLD.decision THEN
        RETURN NEW;
    END IF;

    predicted_verdict_value := COALESCE(
        NEW.report -> 'calibration' ->> 'raw_verdict',
        NEW.verdict,
        'review'
    );

    IF predicted_verdict_value NOT IN ('ready', 'review', 'critical') THEN
        predicted_verdict_value := COALESCE(NEW.verdict, 'review');
    END IF;

    feedback_outcome := CASE
        WHEN predicted_verdict_value = 'ready' AND NEW.decision = 'accepted'
            THEN 'correct_clean'
        WHEN predicted_verdict_value = 'critical' AND NEW.decision = 'fix_required'
            THEN 'correct_fix'
        WHEN predicted_verdict_value = 'review' AND NEW.decision = 'fix_required'
            THEN 'useful_warning'
        WHEN predicted_verdict_value IN ('review', 'critical')
             AND NEW.decision = 'accepted'
            THEN 'false_alarm'
        WHEN predicted_verdict_value = 'ready'
             AND NEW.decision = 'fix_required'
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
        predicted_verdict_value,
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
