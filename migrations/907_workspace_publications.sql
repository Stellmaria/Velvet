ALTER TABLE publication_inbox_items
    ADD COLUMN workspace_id BIGINT;

ALTER TABLE publication_drafts
    ADD COLUMN workspace_id BIGINT;

ALTER TABLE publication_draft_items
    ADD COLUMN workspace_id BIGINT;

ALTER TABLE publication_events
    ADD COLUMN workspace_id BIGINT;

UPDATE publication_inbox_items
SET workspace_id = 1
WHERE workspace_id IS NULL;

UPDATE publication_drafts
SET workspace_id = 1
WHERE workspace_id IS NULL;

UPDATE publication_draft_items AS item
SET workspace_id = draft.workspace_id
FROM publication_drafts AS draft
WHERE item.draft_id = draft.id
  AND item.workspace_id IS NULL;

UPDATE publication_events AS event
SET workspace_id = draft.workspace_id
FROM publication_drafts AS draft
WHERE event.draft_id = draft.id
  AND event.workspace_id IS NULL;

ALTER TABLE publication_inbox_items
    ALTER COLUMN workspace_id SET DEFAULT 1,
    ALTER COLUMN workspace_id SET NOT NULL;

ALTER TABLE publication_drafts
    ALTER COLUMN workspace_id SET DEFAULT 1,
    ALTER COLUMN workspace_id SET NOT NULL;

ALTER TABLE publication_draft_items
    ALTER COLUMN workspace_id SET DEFAULT 1,
    ALTER COLUMN workspace_id SET NOT NULL;

ALTER TABLE publication_events
    ALTER COLUMN workspace_id SET DEFAULT 1,
    ALTER COLUMN workspace_id SET NOT NULL;

ALTER TABLE publication_inbox_items
    ADD CONSTRAINT publication_inbox_items_workspace_id_fkey
        FOREIGN KEY (workspace_id)
        REFERENCES workspaces(id)
        ON DELETE CASCADE;

ALTER TABLE publication_drafts
    ADD CONSTRAINT publication_drafts_workspace_id_fkey
        FOREIGN KEY (workspace_id)
        REFERENCES workspaces(id)
        ON DELETE CASCADE;

ALTER TABLE publication_draft_items
    ADD CONSTRAINT publication_draft_items_workspace_id_fkey
        FOREIGN KEY (workspace_id)
        REFERENCES workspaces(id)
        ON DELETE CASCADE;

ALTER TABLE publication_events
    ADD CONSTRAINT publication_events_workspace_id_fkey
        FOREIGN KEY (workspace_id)
        REFERENCES workspaces(id)
        ON DELETE CASCADE;

CREATE UNIQUE INDEX uq_publication_drafts_workspace_id_id
    ON publication_drafts (workspace_id, id);

ALTER TABLE publication_draft_items
    DROP CONSTRAINT publication_draft_items_draft_id_fkey;

ALTER TABLE publication_draft_items
    ADD CONSTRAINT publication_draft_items_workspace_draft_fkey
        FOREIGN KEY (workspace_id, draft_id)
        REFERENCES publication_drafts(workspace_id, id)
        ON DELETE CASCADE;

ALTER TABLE publication_events
    DROP CONSTRAINT publication_events_draft_id_fkey;

ALTER TABLE publication_events
    ADD CONSTRAINT publication_events_workspace_draft_fkey
        FOREIGN KEY (workspace_id, draft_id)
        REFERENCES publication_drafts(workspace_id, id)
        ON DELETE CASCADE;

ALTER TABLE publication_inbox_items
    DROP CONSTRAINT publication_inbox_owner_message_unique;

ALTER TABLE publication_inbox_items
    ADD CONSTRAINT publication_inbox_workspace_owner_message_unique
        UNIQUE (workspace_id, owner_id, source_chat_id, source_message_id);

DROP INDEX IF EXISTS idx_publication_inbox_group;
DROP INDEX IF EXISTS idx_publication_drafts_owner_status;
DROP INDEX IF EXISTS idx_publication_drafts_schedule;
DROP INDEX IF EXISTS idx_publication_drafts_hash;
DROP INDEX IF EXISTS idx_publication_events_draft;

CREATE INDEX idx_publication_inbox_group
    ON publication_inbox_items(
        workspace_id,
        owner_id,
        source_chat_id,
        media_group_id,
        received_at
    );

CREATE INDEX idx_publication_drafts_owner_status
    ON publication_drafts(workspace_id, owner_id, status, updated_at DESC);

CREATE INDEX idx_publication_drafts_schedule
    ON publication_drafts(workspace_id, status, scheduled_at)
    WHERE status = 'scheduled';

CREATE INDEX idx_publication_drafts_hash
    ON publication_drafts(workspace_id, target_chat_id, content_hash, created_at DESC);

CREATE INDEX idx_publication_events_draft
    ON publication_events(workspace_id, draft_id, created_at DESC);
