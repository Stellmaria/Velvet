ALTER TABLE character_references
    ADD COLUMN IF NOT EXISTS workspace_id BIGINT;

UPDATE character_references AS reference
SET workspace_id = character.workspace_id
FROM characters AS character
WHERE character.id = reference.character_id
  AND reference.workspace_id IS NULL;

ALTER TABLE character_references
    ALTER COLUMN workspace_id SET DEFAULT 1,
    ALTER COLUMN workspace_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'character_references_workspace_id_fkey'
          AND conrelid = 'character_references'::regclass
    ) THEN
        ALTER TABLE character_references
            ADD CONSTRAINT character_references_workspace_id_fkey
            FOREIGN KEY (workspace_id)
            REFERENCES workspaces(id)
            ON DELETE CASCADE;
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_characters_workspace_id_id
    ON characters (workspace_id, id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_character_references_workspace_id_id
    ON character_references (workspace_id, id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'character_references_workspace_character_fkey'
          AND conrelid = 'character_references'::regclass
    ) THEN
        ALTER TABLE character_references
            ADD CONSTRAINT character_references_workspace_character_fkey
            FOREIGN KEY (workspace_id, character_id)
            REFERENCES characters(workspace_id, id)
            ON DELETE CASCADE;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_character_references_workspace_character
    ON character_references (workspace_id, character_id, created_at, id);

ALTER TABLE reference_comparison_reports
    ADD COLUMN IF NOT EXISTS workspace_id BIGINT;

UPDATE reference_comparison_reports AS comparison
SET workspace_id = character.workspace_id
FROM characters AS character
WHERE character.id = comparison.character_id
  AND comparison.workspace_id IS NULL;

ALTER TABLE reference_comparison_reports
    ALTER COLUMN workspace_id SET DEFAULT 1,
    ALTER COLUMN workspace_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'reference_comparison_reports_workspace_id_fkey'
          AND conrelid = 'reference_comparison_reports'::regclass
    ) THEN
        ALTER TABLE reference_comparison_reports
            ADD CONSTRAINT reference_comparison_reports_workspace_id_fkey
            FOREIGN KEY (workspace_id)
            REFERENCES workspaces(id)
            ON DELETE CASCADE;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'reference_comparison_reports_workspace_character_fkey'
          AND conrelid = 'reference_comparison_reports'::regclass
    ) THEN
        ALTER TABLE reference_comparison_reports
            ADD CONSTRAINT reference_comparison_reports_workspace_character_fkey
            FOREIGN KEY (workspace_id, character_id)
            REFERENCES characters(workspace_id, id)
            ON DELETE CASCADE;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'reference_comparison_reports_workspace_reference_fkey'
          AND conrelid = 'reference_comparison_reports'::regclass
    ) THEN
        ALTER TABLE reference_comparison_reports
            ADD CONSTRAINT reference_comparison_reports_workspace_reference_fkey
            FOREIGN KEY (workspace_id, reference_id)
            REFERENCES character_references(workspace_id, id)
            ON DELETE CASCADE;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_reference_comparison_workspace_character_created
    ON reference_comparison_reports (workspace_id, character_id, created_at DESC);
