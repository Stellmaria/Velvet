ALTER TABLE ai_tasks
    DROP CONSTRAINT IF EXISTS ai_tasks_attempts_check;

ALTER TABLE ai_tasks
    ADD CONSTRAINT ai_tasks_attempts_check
    CHECK (attempt_count >= 0 AND max_attempts BETWEEN 1 AND 50);
