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
  AND NOT EXISTS (
      SELECT 1
      FROM qwen_quality_feedback AS feedback
      WHERE feedback.media_id = quality.media_id
        AND feedback.owner_decision = quality.decision
        AND feedback.decided_at = COALESCE(
            quality.decided_at,
            quality.updated_at,
            feedback.decided_at
        )
  );
